"""Week-2: the calendar widget must read the CALLER's Nextcloud.

`/widget/calendar` never bound the NC context: the credential gate
answered "deny" for every widget call and the widget was permanently
empty — the second caller to forget the binder (dispatcher was the
first), which is why the binder now lives in ONE place
(`utils.bind_nc_context`) and both paths share it.
"""
import asyncio
import os
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main as mainmod

ROOT = os.path.join(os.path.dirname(__file__), "..")

ALICE_CREDS = {"url": "https://cloud-a.example", "user": "alice", "password": "s3cret"}


@pytest.fixture
def widget_app(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "w.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    alice, alice_key = asyncio.run(dbmod.create_user("alice"))
    admin, admin_key = asyncio.run(dbmod.create_user("patron", is_admin=True))
    carol, carol_key = asyncio.run(dbmod.create_user("carol"))

    import utils

    captured = {}

    def _fake_list_events_today():
        # Runs inside to_thread: the copied context carries the bound vars.
        captured["creds"] = utils.NC_CREDS.get()
        captured["shared_ok"] = utils.NC_SHARED_OK.get()
        captured["key"] = utils.nc_cache_key()
        return [{"title": "captured"}]

    import calendar_ops

    monkeypatch.setattr(calendar_ops, "list_events_today", _fake_list_events_today)

    async def _creds(uid, provider):
        return dict(ALICE_CREDS) if uid == alice["id"] else None

    async def _get_user(uid):
        return {"id": uid, "name": "x", "is_admin": uid == admin["id"]}

    monkeypatch.setattr(dbmod, "get_credential", _creds)
    monkeypatch.setattr(dbmod, "get_user", _get_user)

    app = FastAPI()
    app.middleware("http")(mainmod.trusted_host_middleware)
    app.middleware("http")(mainmod.security_middleware)
    from routers.widgets import router as widgets_router

    app.include_router(widgets_router)

    client = TestClient(app, base_url="http://localhost")
    yield {"client": client, "keys": {"alice": alice_key, "admin": admin_key, "carol": carol_key},
           "captured": captured, "ids": {"alice": alice["id"], "admin": admin["id"]}}
    asyncio.run(dbmod.close_db())


def test_widget_binds_caller_personal_creds(widget_app):
    r = widget_app["client"].get("/widget/calendar", headers={"x-api-key": widget_app["keys"]["alice"]})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    cap = widget_app["captured"]
    assert cap["creds"] == ALICE_CREDS
    assert cap["shared_ok"] is False
    assert cap["key"].startswith("u|https://cloud-a.example|alice")


def test_widget_admin_without_creds_gets_shared_ok(widget_app):
    r = widget_app["client"].get("/widget/calendar", headers={"x-api-key": widget_app["keys"]["admin"]})
    assert r.status_code == 200
    cap = widget_app["captured"]
    assert cap["creds"] is None
    assert cap["shared_ok"] is True  # admin → shared account allowed
    assert cap["key"].startswith("s|")


def test_widget_non_admin_without_creds_denied(widget_app):
    r = widget_app["client"].get("/widget/calendar", headers={"x-api-key": widget_app["keys"]["carol"]})
    assert r.status_code == 200
    cap = widget_app["captured"]
    assert cap["creds"] is None
    assert cap["shared_ok"] is False  # non-admin: never the shared account
    assert cap["key"] == "deny"


def test_widget_requires_auth(widget_app):
    r = widget_app["client"].get("/widget/calendar")
    assert r.status_code == 401


def test_dispatcher_uses_shared_binder_no_inline_drift():
    """The binder must stay in ONE place — no re-inlined copies."""
    src = open(os.path.join(ROOT, "tools/dispatcher.py"), encoding="utf-8").read()
    assert "bind_nc_context" in src
    # The old inline pattern must not come back next to the helper.
    assert not re.search(r"NC_CREDS\.set\(", src), "dispatcher must not set NC_CREDS inline — use bind_nc_context"
    assert not re.search(r"NC_SHARED_OK\.set\(", src)

    widgets_src = open(os.path.join(ROOT, "routers/widgets.py"), encoding="utf-8").read()
    assert "bind_nc_context" in widgets_src


def test_bind_nc_context_unit(monkeypatch):
    import db as dbmod
    import utils

    async def _creds(uid, provider):
        return {"url": "https://u.example", "user": uid, "password": "p"} if uid == "u1" else None

    async def _get_user(uid):
        return {"id": uid, "is_admin": uid == "u9"} if uid else None

    monkeypatch.setattr(dbmod, "get_credential", _creds)
    monkeypatch.setattr(dbmod, "get_user", _get_user)

    async def _scenario():
        # ContextVar sets live in the TASK's context copy — assertions must
        # read from inside the same task (the docstring contract).
        await utils.bind_nc_context("u1")
        r1 = (utils.NC_CREDS.get(), utils.NC_SHARED_OK.get())
        await utils.bind_nc_context("u9")
        r2 = (utils.NC_CREDS.get(), utils.NC_SHARED_OK.get())
        await utils.bind_nc_context(None)
        r3 = (utils.NC_CREDS.get(), utils.NC_SHARED_OK.get())
        return r1, r2, r3

    r1, r2, r3 = asyncio.run(_scenario())
    assert r1[0]["user"] == "u1" and r1[1] is False      # own creds, no shared
    assert r2[0] is None and r2[1] is True               # admin → shared ok
    assert r3[0] is None and r3[1] is False              # anonymous → deny
