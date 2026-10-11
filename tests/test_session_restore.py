"""Week-2: post-refresh login bug — a valid session cookie must count as logged in.

Root cause (analysis + 2026-10-05 verification): the ui.js boot gate checked
getApiKey() only, but password logins keep NO key in the browser (the
HttpOnly session cookie IS the credential by design) — so every refresh
re-asked for login even with a perfectly valid cookie.

Fixes under test:
- ui.js boot gate awaits GET /users/me (cookie-authed) before showLogin()
- sw.js never caches /users* (auth-dependent responses must not go stale)
- the session cookie's Secure flag derives from the request scheme, with
  SESSION_COOKIE_SECURE as the TLS-terminating-proxy override — never
  secure-only over plain HTTP (the browser would drop it silently)
"""
import asyncio
import os
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import main as mainmod

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


# ── Source contracts (files that cannot be imported) ─────────────────────────

def test_ui_boot_gate_verifies_session_before_showing_login():
    ui = _read("static/ui.js")
    m = re.search(
        r"if\(!_NATIVE && localStorage\.getItem\('ps_onboarded'\) && !getApiKey\(\)\)\{(.*?)\n  \}",
        ui, re.S,
    )
    assert m, "keyless boot gate block not found in ui.js"
    block = m.group(1)
    assert "/users/me" in block, "boot gate must verify the session cookie via /users/me"
    assert "cache: 'no-store'" in block
    # Login is offered only when the session check actually failed.
    assert re.search(r"if\(!authed\) showLogin\(\);", block)


def test_sw_never_caches_users_paths():
    sw = _read("static/sw.js")
    m = re.search(
        r"request\.method !== 'GET' \|(.*?)\{\s*return;\s*\}", sw, re.S,
    )
    assert m, "never-cache condition not found in sw.js"
    assert "'/users'" in m.group(1), "sw.js must exclude /users from caching"


# ── Behavioral: the cookie really authenticates ───────────────────────────────

@pytest.fixture
def users_app(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "sess.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    user, _ = asyncio.run(dbmod.create_user("alice"))
    asyncio.run(dbmod.set_password(user["id"], "parola1234"))

    app = FastAPI()
    app.middleware("http")(mainmod.trusted_host_middleware)
    app.middleware("http")(mainmod.security_middleware)
    from routers.users import router as users_router

    app.include_router(users_router)
    yield app
    asyncio.run(dbmod.close_db())


def _client(app, base="http://localhost"):
    return TestClient(app, base_url=base)


def test_me_with_valid_session_cookie_200(users_app):
    import db as dbmod

    alice = asyncio.run(dbmod.get_user_by_name("alice"))
    _, raw = asyncio.run(dbmod.create_session(alice["id"], "browser-test"))

    c = _client(users_app)
    r = c.get("/users/me", cookies={dbmod.SESSION_COOKIE_NAME: raw})
    assert r.status_code == 200
    assert r.json()["user"]["name"] == "alice"


def test_me_without_cookie_401(users_app):
    c = _client(users_app)
    assert c.get("/users/me").status_code == 401


def test_password_login_sets_cookie_and_returns_no_key(users_app):
    import db as dbmod

    c = _client(users_app)
    r = c.post("/users/session", json={"name": "alice", "password": "parola1234"})
    assert r.status_code == 200
    assert "api_key" not in r.json()  # cookie auth: no key material to the browser
    set_cookie = r.headers.get("set-cookie", "")
    assert dbmod.SESSION_COOKIE_NAME in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "secure" not in set_cookie.lower()  # http scheme → no Secure flag
    # The freshly set cookie authenticates /users/me immediately.
    r2 = c.get("/users/me")
    assert r2.status_code == 200
    assert r2.json()["user"]["name"] == "alice"


def test_logout_revokes_session(users_app):
    c = _client(users_app)
    c.post("/users/session", json={"name": "alice", "password": "parola1234"})
    assert c.get("/users/me").status_code == 200
    assert c.post("/users/logout").status_code == 200
    assert c.get("/users/me").status_code == 401  # cookie no longer valid


def test_secure_flag_from_env_override(users_app, monkeypatch):
    import config

    monkeypatch.setattr(config, "SESSION_COOKIE_SECURE", True)
    c = _client(users_app)
    r = c.post("/users/session", json={"name": "alice", "password": "parola1234"})
    set_cookie = r.headers.get("set-cookie", "")
    assert "secure" in set_cookie.lower()


def test_secure_flag_derived_from_https_scheme(users_app):
    c = _client(users_app, base="https://localhost")
    r = c.post("/users/session", json={"name": "alice", "password": "parola1234"})
    set_cookie = r.headers.get("set-cookie", "")
    assert "secure" in set_cookie.lower()
