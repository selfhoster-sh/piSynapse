"""Static serving: clean entry, app shells resolve, no directory listing."""
from fastapi.testclient import TestClient

import main as mainmod

client = TestClient(mainmod.app, base_url="http://localhost")


def test_root_redirects_to_static():
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307)
    assert r.headers["location"].rstrip("/").endswith("/static")


def test_directory_index_serves_loader():
    r = client.get("/static/")
    assert r.status_code == 200
    assert "PiSynapse" in r.text


def test_app_shells_resolve():
    for path in ("/static/web.html", "/static/app.html", "/static/index.html",
                 "/static/ui.js", "/static/ui.css"):
        assert client.get(path).status_code == 200, path


def test_no_directory_listing_anywhere():
    # Subdirectories without an index must 404, never list contents.
    # (/../ normalizes client-side to an unknown route → 401 from auth, also
    # safe: no file bytes are ever served.)
    for path in ("/static/fonts/", "/static/fonts", "/static/icons/",
                 "/static/vendor/", "/static/vendor", "/static/nope.js",
                 "/static/../main.py", "/static/%2e%2e/main.py"):
        r = client.get(path)
        assert r.status_code in (400, 401, 404), (path, r.status_code)
        assert "Index of" not in getattr(r, "text", "")
