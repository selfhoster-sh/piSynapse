"""Week-2 client cache hygiene.

- /static behavioral files (html/js/css/json) revalidate on every load:
  an updated ui.js reaches browsers immediately (no-cache + ETag 304s),
  instead of riding a stale max-age.
- Fonts/icons get a 7-day cache (big, rarely change).
- sw.js CACHE_NAME bumped to v56 so the new fetch handler (the /users
  never-cache exclusion) actually reaches already-registered clients —
  the activate step deletes every cache that is not the current name.
"""
import os
import re

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

import main as mainmod

ROOT = os.path.join(os.path.dirname(__file__), "..")


@pytest.fixture
def static_client():
    app = FastAPI()
    app.middleware("http")(mainmod.static_cache_control_middleware)
    app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static"), html=True), name="static")

    @app.get("/plain")
    async def plain():
        return JSONResponse({"ok": True})

    return TestClient(app, base_url="http://localhost")


def test_behavioral_files_revalidate(static_client):
    r = static_client.get("/static/manifest.json")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_fonts_get_long_cache(static_client):
    r = static_client.get("/static/fonts/dm-sans-latin.woff2")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=604800"


def test_icons_get_long_cache(static_client):
    r = static_client.get("/static/icons/icon-192.png")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "public, max-age=604800"


def test_extensionless_paths_revalidate(static_client):
    # Directory index (html=True) and dotless files must not be long-cached.
    r = static_client.get("/static/")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_non_static_paths_untouched(static_client):
    r = static_client.get("/plain")
    assert r.status_code == 200
    assert "cache-control" not in r.headers  # this middleware only owns /static


def test_sw_cache_name_bumped_and_wellformed():
    sw = open(os.path.join(ROOT, "static/sw.js"), encoding="utf-8").read()
    m = re.search(r"const CACHE_NAME = 'pisynapse-v(\d+)'", sw)
    assert m, "CACHE_NAME literal not found / malformed"
    assert int(m.group(1)) >= 57, (
        "sw.js behavior changed without a CACHE_NAME bump — already-registered "
        "clients keep the old fetch handler until the version moves"
    )
