"""Browser sessions: cookie auth with keys kept server-side."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db as dbmod
import main as mainmod


@pytest.fixture
def sess_api(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "sess.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)
    from routers.users import router as users_router

    app.include_router(users_router)
    client = TestClient(app, base_url="http://localhost")
    yield client
    asyncio.run(dbmod.close_db())


def _register(client, name="anna", password="secret123"):
    r = client.post("/users/register", json={"name": name, "password": password})
    assert r.status_code == 201
    return r


def test_register_sets_session_cookie(sess_api):
    r = _register(sess_api)
    assert "ps_session=" in r.headers.get("set-cookie", "")
    assert "HttpOnly" in r.headers.get("set-cookie", "")
    assert r.json()["api_key"]  # ceremony still receives the key once


def test_session_login_no_key_material(sess_api):
    _register(sess_api)
    c2 = TestClient(sess_api.app, base_url="http://localhost")
    r = c2.post("/users/session", json={"name": "anna", "password": "secret123"})
    assert r.status_code == 200
    assert "api_key" not in r.json()
    assert "ps_session=" in r.headers.get("set-cookie", "")
    # Cookie alone authenticates (no X-API-Key sent).
    me = c2.get("/users/me")
    assert me.status_code == 200
    assert me.json()["user"]["name"] == "anna"


def test_session_login_rejects_wrong_credentials(sess_api):
    _register(sess_api)
    assert sess_api.post("/users/session", json={"name": "anna", "password": "nope"}).status_code == 401
    assert sess_api.post("/users/session", json={"name": "ghost", "password": "secret123"}).status_code == 401
    assert "ps_session" not in sess_api.post(
        "/users/session", json={"name": "anna", "password": "nope"}).headers.get("set-cookie", "")


def test_logout_revokes(sess_api):
    _register(sess_api)
    c2 = TestClient(sess_api.app, base_url="http://localhost")
    c2.post("/users/session", json={"name": "anna", "password": "secret123"})
    assert c2.get("/users/me").status_code == 200
    assert c2.post("/users/logout").status_code == 200
    assert c2.get("/users/me").status_code == 401


def test_expired_session_rejected_and_cleaned(sess_api):
    _register(sess_api)
    c2 = TestClient(sess_api.app, base_url="http://localhost")
    c2.post("/users/session", json={"name": "anna", "password": "secret123"})

    async def _expire():
        db = await dbmod.get_db()
        await db.execute("UPDATE user_sessions SET expires_at = datetime('now', '-1 day')")
        await db.commit()

    async def _ids():
        db = await dbmod.get_db()
        cur = await db.execute("SELECT id FROM user_sessions ORDER BY created_at")
        return [r[0] for r in await cur.fetchall()]

    before = asyncio.run(_ids())
    assert len(before) == 2  # register session + login session
    asyncio.run(_expire())
    assert c2.get("/users/me").status_code == 401
    # The presented (expired) session is lazily cleaned; untouched rows stay.
    assert asyncio.run(_ids()) == before[:1]


def test_two_logins_distinct_tokens(sess_api):
    _register(sess_api)
    c1 = TestClient(sess_api.app, base_url="http://localhost")
    c2 = TestClient(sess_api.app, base_url="http://localhost")
    t1 = c1.post("/users/session", json={"name": "anna", "password": "secret123"}).headers["set-cookie"]
    t2 = c2.post("/users/session", json={"name": "anna", "password": "secret123"}).headers["set-cookie"]
    assert t1 != t2
    assert c1.get("/users/me").status_code == 200
    assert c2.get("/users/me").status_code == 200


def test_password_change_revokes_other_sessions(sess_api):
    _register(sess_api)
    c1 = TestClient(sess_api.app, base_url="http://localhost")
    c2 = TestClient(sess_api.app, base_url="http://localhost")
    c1.post("/users/session", json={"name": "anna", "password": "secret123"})
    c2.post("/users/session", json={"name": "anna", "password": "secret123"})
    r = c1.post("/users/password", json={"current": "secret123", "new": "newsecret456"})
    assert r.status_code == 200
    assert c1.get("/users/me").status_code == 200
    assert c2.get("/users/me").status_code == 401
