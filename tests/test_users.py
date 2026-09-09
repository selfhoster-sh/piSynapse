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
