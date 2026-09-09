"""End-to-end onboarding chain (web): register → ceremony key → city → mail → nc.

Proves the exact call sequence the rebuilt onboarding UI performs, with the
browser holding NO API key at any point (session cookie only).
"""
import asyncio

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db as dbmod
import main as mainmod


@pytest.fixture
def obapp(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "ob.db"))
    monkeypatch.setenv("MAIL_CREDS_KEY", Fernet.generate_key().decode())
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)
    from routers.config import router as config_router
    from routers.users import router as users_router

    app.include_router(users_router)
    app.include_router(config_router)
    client = TestClient(app, base_url="http://localhost")
    yield client
    asyncio.run(dbmod.close_db())


def test_register_chain_without_browser_key(obapp):
    # 1. Register with password: session cookie + once-only key, nothing stored.
    r = obapp.post("/users/register", json={"name": "fresh", "password": "secret123"})
    assert r.status_code == 201
    key = r.json()["api_key"]
    assert key and len(key) >= 32
    assert obapp.cookies.get("ps_session")

    # 2. Display name sync (s3/regform save) over the session cookie.
    s = obapp.put("/config/my-settings", json={"values": {"ASSISTANT_USER": "fresh"}})
    assert s.status_code == 200

    # 3. City step.
    s = obapp.put("/config/my-settings", json={"values": {"DEFAULT_CITY": "Istanbul"}})
    assert s.status_code == 200

    # 4. Mail step.
    m = obapp.post("/users/me/credentials",
                   json={"provider": "gmail", "account": "f@x.com", "secret": "appw"})
    assert m.status_code == 200

    # 5. Nextcloud step.
    n = obapp.post("/users/me/credentials",
                   json={"provider": "nextcloud", "account": "f", "secret": "pw",
                         "url": "https://cloud.example.com"})
    assert n.status_code == 200

    # 6. Effective values resolve per user; the ceremony key is a working key.
    me = obapp.get("/config/my-settings").json()
    assert me["settings"]["DEFAULT_CITY"]["value"] == "Istanbul"
    creds = obapp.get("/users/me/credentials").json()["credentials"]
    assert {c["provider"] for c in creds} == {"gmail", "nextcloud"}
    assert "appw" not in str(creds)

    fresh = TestClient(obapp.app, base_url="http://localhost")
    assert fresh.get("/users/me", headers={"x-api-key": key}).status_code == 200


def test_login_chain_skips_to_app(obapp):
    obapp.post("/users/register", json={"name": "old", "password": "secret123"})
    # Fresh browser, no cookies, no key: password login → straight in.
    c2 = TestClient(obapp.app, base_url="http://localhost")
    r = c2.post("/users/session", json={"name": "old", "password": "secret123"})
    assert r.status_code == 200
    assert "api_key" not in r.json()
    assert c2.get("/users/me").status_code == 200
    # Wrong password: error, session untouched.
    c3 = TestClient(obapp.app, base_url="http://localhost")
    assert c3.post("/users/session", json={"name": "old", "password": "wrongpass"}).status_code == 401
    assert c3.get("/users/me").status_code == 401
