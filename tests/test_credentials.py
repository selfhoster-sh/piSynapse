"""Per-user encrypted credentials + per-user service wiring."""
import asyncio

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db as dbmod
import main as mainmod


@pytest.fixture
def cdb(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "c.db"))
    monkeypatch.setenv("MAIL_CREDS_KEY", Fernet.generate_key().decode())
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def cuser(cdb):
    user, key = asyncio.run(cdb.create_user("carol"))
    return cdb, user["id"], key


def test_roundtrip_encrypted(cuser):
    dbmod, uid, _ = cuser
    assert asyncio.run(dbmod.save_credential(uid, "gmail", {"address": "c@x.com", "app_password": "s3cret"})) is True
    got = asyncio.run(dbmod.get_credential(uid, "gmail"))
    assert got == {"address": "c@x.com", "app_password": "s3cret"}
    # Stored blob is opaque.
    rows = asyncio.run(_rows(dbmod, "SELECT enc_blob FROM user_credentials"))
    assert rows and "s3cret" not in rows[0][0] and "c@x.com" not in rows[0][0]
    # Listing exposes the label, never the secret.
    listed = asyncio.run(dbmod.list_credentials(uid))
    assert listed[0]["provider"] == "gmail" and listed[0]["account"] == "c@x.com"
    assert "s3cret" not in str(listed)
    assert asyncio.run(dbmod.delete_credential(uid, "gmail")) is True
    assert asyncio.run(dbmod.get_credential(uid, "gmail")) is None


def test_validation_rejects(cuser):
    dbmod, uid, _ = cuser
    assert asyncio.run(dbmod.save_credential(uid, "nope", {"a": "b"})) is False
    assert asyncio.run(dbmod.save_credential(uid, "gmail", {"address": "c@x.com"})) is False
    assert asyncio.run(dbmod.save_credential(uid, "nextcloud", {"url": "https://x", "user": "u"})) is False


def test_wrong_key_unreadable(cuser, monkeypatch):
    dbmod, uid, _ = cuser
    asyncio.run(dbmod.save_credential(uid, "gmail", {"address": "c@x.com", "app_password": "s3cret"}))
    monkeypatch.setenv("MAIL_CREDS_KEY", Fernet.generate_key().decode())
    assert asyncio.run(dbmod.get_credential(uid, "gmail")) is None


def test_mail_factory_per_user(cuser):
    import asyncio as _aio

    import mail as mailmod

    dbmod, uid, _ = cuser
    assert _aio.run(mailmod.get_mail_client_for_user(uid)) is None
    assert _aio.run(mailmod.get_mail_client_for_user(None)) is None
    asyncio.run(dbmod.save_credential(uid, "gmail", {"address": "c@x.com", "app_password": "pw"}))
    mc = _aio.run(mailmod.get_mail_client_for_user(uid))
    assert isinstance(mc, mailmod.GmailClient) and mc._user == "c@x.com"


def test_nc_factories_prefer_context_creds():
    import nextcloud_notes as nn
    from utils import NC_CREDS

    creds = {"url": "https://me.example.com", "user": "me", "password": "pw"}
    tok = NC_CREDS.set(creds)
    try:
        assert nn._get_client()._base == "https://me.example.com"
        assert nn._get_client()._user == "me"
    finally:
        NC_CREDS.reset(tok)
    assert NC_CREDS.get() is None


def test_credential_endpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "ce.db"))
    monkeypatch.setenv("MAIL_CREDS_KEY", Fernet.generate_key().decode())
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    try:
        app = FastAPI()
        app.middleware("http")(mainmod.security_middleware)
        from routers.users import router as users_router

        app.include_router(users_router)
        client = TestClient(app, base_url="http://localhost")
        key = client.post("/users/register", json={"name": "dave"}).json()["api_key"]
        h = {"x-api-key": key}
        r = client.post("/users/me/credentials", headers=h,
                        json={"provider": "gmail", "account": "d@x.com", "secret": "pw"})
        assert r.status_code == 200
        listed = client.get("/users/me/credentials", headers=h).json()["credentials"]
        assert listed[0]["provider"] == "gmail" and listed[0]["account"] == "d@x.com"
        assert "pw" not in r.text and "pw" not in str(listed)
        assert client.post("/users/me/credentials", headers=h,
                           json={"provider": "nope", "account": "x", "secret": "y"}).status_code == 400
        assert client.delete("/users/me/credentials/gmail", headers=h).status_code == 200
        assert client.delete("/users/me/credentials/gmail", headers=h).status_code == 404
    finally:
        asyncio.run(dbmod.close_db())


async def _rows(dbmod, sql):
    db = await dbmod.get_db()
    cur = await db.execute(sql)
    return await cur.fetchall()
