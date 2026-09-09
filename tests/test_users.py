"""Multi-user identity (M1a): users table + key lifecycle."""

import asyncio

import pytest

import db as dbmod


@pytest.fixture
def users_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "users.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_create_returns_key_once_and_stores_hash(users_db):
    user, raw_key = asyncio.run(dbmod.create_user("alice"))
    assert user["id"] and user["name"] == "alice" and user["is_admin"] is False
    assert raw_key and len(raw_key) >= 32

    async def _stored():
        db = await dbmod.get_db()
        cur = await db.execute("SELECT key_hash FROM users WHERE id = ?", (user["id"],))
        return (await cur.fetchone())[0]

    stored = asyncio.run(_stored())
    assert stored != raw_key
    assert stored == dbmod.hash_api_key(raw_key)
    assert asyncio.run(dbmod.get_user_by_key_hash(stored))["id"] == user["id"]


def test_duplicate_user_id_rejected(users_db):
    import sqlite3

    asyncio.run(dbmod.create_user("x", user_id="u1"))
    with pytest.raises(sqlite3.IntegrityError):
        asyncio.run(dbmod.create_user("y", user_id="u1"))


def test_rotate_replaces_key(users_db):
    user, old_key = asyncio.run(dbmod.create_user("bob"))
    old_hash = dbmod.hash_api_key(old_key)
    new_key = asyncio.run(dbmod.rotate_user_key(user["id"]))
    assert new_key and new_key != old_key
    assert asyncio.run(dbmod.get_user_by_key_hash(old_hash)) is None
    assert asyncio.run(dbmod.get_user_by_key_hash(dbmod.hash_api_key(new_key)))["id"] == user["id"]
    assert asyncio.run(dbmod.rotate_user_key("ghost")) is None


def test_ensure_default_admin_binds_env_key(users_db, monkeypatch):
    monkeypatch.setenv("API_KEY", "owner-key")
    admin = asyncio.run(dbmod.ensure_default_admin())
    assert admin and admin["id"] == "default" and admin["is_admin"] is True
    assert asyncio.run(dbmod.get_user_by_key_hash(dbmod.hash_api_key("owner-key")))["id"] == "default"
    # Idempotent: second call is a no-op.
    assert asyncio.run(dbmod.ensure_default_admin()) is None
    assert asyncio.run(dbmod.count_users()) == 1


def test_ensure_default_admin_without_key_waits(users_db, monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    assert asyncio.run(dbmod.ensure_default_admin()) is None
    assert asyncio.run(dbmod.count_users()) == 0


def test_unknown_key_and_user_miss(users_db):
    assert asyncio.run(dbmod.get_user_by_key_hash("nope")) is None
    assert asyncio.run(dbmod.get_user("ghost")) is None


# -- Middleware resolution (M1b) --

def _mw_app():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    import main as mainmod

    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)

    @app.post("/api/thing")
    async def thing(request: Request):
        from fastapi.responses import JSONResponse

        return JSONResponse({
            "ok": True,
            "user_id": getattr(request.state, "user_id", None),
            "is_admin": bool(getattr(request.state, "is_admin", False)),
        })

    return TestClient(app, base_url="http://localhost"), mainmod


def _use_tmp_db(monkeypatch, tmp_path, name="mw.db"):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / name))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()


def test_env_key_maps_to_default_admin(monkeypatch, tmp_path):
    _use_tmp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("API_KEY", "owner-key")
    client, _ = _mw_app()
    r = client.post("/api/thing", headers={"x-api-key": "owner-key"})
    assert r.status_code == 200, r.text
    assert r.json()["user_id"] == "default"


def test_db_key_maps_to_its_user_and_admin_flag(monkeypatch, tmp_path):
    _use_tmp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("API_KEY", "")
    user, raw = asyncio.run(dbmod.create_user("carol"))
    admin, admin_raw = asyncio.run(dbmod.create_user("root", is_admin=True))
    client, _ = _mw_app()
    r = client.post("/api/thing", headers={"x-api-key": raw})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "user_id": user["id"], "is_admin": False}
    r = client.post("/api/thing", headers={"x-api-key": admin_raw})
    assert r.json()["is_admin"] is True


def test_unknown_key_is_401_when_configured(monkeypatch, tmp_path):
    _use_tmp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("API_KEY", "owner-key")
    client, _ = _mw_app()
    assert client.post("/api/thing", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post("/api/thing").status_code == 401


def test_nothing_configured_is_503(monkeypatch, tmp_path):
    import main as mainmod

    _use_tmp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setattr(mainmod, "API_KEY", "")
    client, _ = _mw_app()
    assert client.post("/api/thing").status_code == 503
    assert client.post("/api/thing", headers={"x-api-key": "anything"}).status_code == 503


def test_rotation_invalidates_cached_resolution(monkeypatch, tmp_path):
    _use_tmp_db(monkeypatch, tmp_path)
    monkeypatch.setenv("API_KEY", "")
    user, old_raw = asyncio.run(dbmod.create_user("dave"))
    client, _ = _mw_app()
    assert client.post("/api/thing", headers={"x-api-key": old_raw}).status_code == 200
    new_raw = asyncio.run(dbmod.rotate_user_key(user["id"]))
    assert client.post("/api/thing", headers={"x-api-key": old_raw}).status_code == 401
    r = client.post("/api/thing", headers={"x-api-key": new_raw})
    assert r.status_code == 200 and r.json()["user_id"] == user["id"]
