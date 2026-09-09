"""User endpoints: register / rotate / me / list (M1c)."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config as config_module
import db as dbmod
import main as mainmod


@pytest.fixture
def users_api(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "api.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    monkeypatch.setattr(config_module, "REGISTRATION_OPEN", "on")
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)
    from routers.users import router as users_router

    app.include_router(users_router)
    yield TestClient(app, base_url="http://localhost"), mainmod
    asyncio.run(dbmod.close_db())


def test_register_first_user_is_admin(users_api):
    client, _ = users_api
    r = client.post("/users/register", json={"name": " Ada "})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["name"] == "Ada"
    assert body["user"]["is_admin"] is True
    assert body["api_key"] and len(body["api_key"]) >= 32
    assert "key_hash" not in body["user"]
    assert "api_key" not in body["user"]


def test_register_second_user_is_not_admin(users_api):
    client, _ = users_api
    client.post("/users/register", json={"name": "admin"})
    r = client.post("/users/register", json={"name": "bob"})
    assert r.status_code == 201
    assert r.json()["user"]["is_admin"] is False


def test_register_closed_is_403(users_api, monkeypatch):
    monkeypatch.setattr(config_module, "REGISTRATION_OPEN", "off")
    client, _ = users_api
    r = client.post("/users/register", json={"name": "mallory"})
    assert r.status_code == 403
    assert asyncio.run(dbmod.count_users()) == 0


def test_register_validates_name(users_api):
    client, _ = users_api
    assert client.post("/users/register", json={"name": ""}).status_code == 422
    assert client.post("/users/register", json={}).status_code == 422


def test_me_rotate_list_flow(users_api):
    client, _ = users_api
    admin_key = client.post("/users/register", json={"name": "root"}).json()["api_key"]
    bob_key = client.post("/users/register", json={"name": "bob"}).json()["api_key"]

    me = client.get("/users/me", headers={"x-api-key": bob_key})
    assert me.status_code == 200
    assert me.json()["user"]["name"] == "bob"
    assert "key_hash" not in me.text and "api_key" not in me.json()["user"]

    # Non-admin cannot list.
    assert client.get("/users", headers={"x-api-key": bob_key}).status_code == 403
    # Admin can.
    lst = client.get("/users", headers={"x-api-key": admin_key})
    assert lst.status_code == 200
    assert lst.json()["count"] == 2
    assert {u["name"] for u in lst.json()["users"]} == {"root", "bob"}

    # Rotate: new key works, old dies, and it is shown exactly once.
    new_key = client.post("/users/key/rotate", headers={"x-api-key": bob_key}).json()["api_key"]
    assert new_key != bob_key
    # Key-only assertions below: drop the register-issued session cookies so
    # the ambient browser session doesn't authenticate in place of the key.
    client.cookies.clear()
    assert client.get("/users/me", headers={"x-api-key": bob_key}).status_code == 401
    assert client.get("/users/me", headers={"x-api-key": new_key}).status_code == 200


def test_unauthenticated_users_endpoints_reject(users_api):
    client, _ = users_api
    assert client.get("/users/me").status_code == 401
    assert client.post("/users/key/rotate").status_code == 401
    assert client.get("/users").status_code == 401


def test_me_legacy_env_key_without_row_returns_owner(users_api):
    # No users rows at all (pre-bootstrap): the server owner's .env key
    # (conftest API_KEY=test-key) must still validate as the owner instead
    # of 401ing in the login UI.
    import os

    client, _ = users_api
    r = client.get("/users/me", headers={"x-api-key": os.environ["API_KEY"]})
    assert r.status_code == 200
    user = r.json()["user"]
    assert user["id"] == "default" and user["is_admin"] is True
    assert "key_hash" not in r.text


def test_login_issues_device_key(users_api):
    client, _ = users_api
    reg = client.post("/users/register", json={"name": "eve", "password": "s3cret!!"})
    assert reg.status_code == 201
    # Wrong password and unknown name are indistinguishable.
    assert client.post("/users/login", json={"name": "eve", "password": "nope"}).status_code == 401
    assert client.post("/users/login", json={"name": "ghost", "password": "s3cret!!"}).status_code == 401
    ok = client.post("/users/login", json={"name": "EVE", "password": "s3cret!!", "device": "laptop"})
    assert ok.status_code == 200
    body = ok.json()
    assert body["user"]["name"] == "eve"
    # Device key authenticates like a primary key.
    me = client.get("/users/me", headers={"x-api-key": body["api_key"]})
    assert me.status_code == 200 and me.json()["user"]["id"] == body["user"]["id"]
    keys = client.get("/users/me/keys", headers={"x-api-key": body["api_key"]}).json()["keys"]
    assert [k["name"] for k in keys] == ["laptop"]
    assert all("hash" not in k and "api_key" not in k for k in keys)


def test_password_set_change_and_revoke(users_api):
    client, _ = users_api
    key = client.post("/users/register", json={"name": "fred"}).json()["api_key"]
    h = {"x-api-key": key}
    # First set needs no current password.
    assert client.post("/users/password", json={"new": "first-pass"}, headers=h).status_code == 200
    # Change requires the current one.
    assert client.post("/users/password", json={"current": "wrong", "new": "second-pass"},
                       headers=h).status_code == 401
    assert client.post("/users/password", json={"current": "first-pass", "new": "second-pass"},
                       headers=h).status_code == 200
    assert client.post("/users/login", json={"name": "fred", "password": "first-pass"}).status_code == 401
    second = client.post("/users/login", json={"name": "fred", "password": "second-pass"})
    assert second.status_code == 200
    # Revoke the device key; primary key keeps working. Key-only view below:
    # clear the register/login session cookies first (see rotate test).
    kid = second.json()["key_id"]
    assert client.delete(f"/users/me/keys/{kid}", headers=h).status_code == 404 - 404 + 200
    client.cookies.clear()
    assert client.get("/users/me", headers={"x-api-key": second.json()["api_key"]}).status_code == 401
    assert client.get("/users/me", headers=h).status_code == 200
    assert client.delete("/users/me/keys/nope", headers=h).status_code == 404


def test_duplicate_and_short_password_rejected(users_api):
    client, _ = users_api
    assert client.post("/users/register", json={"name": "Gail"}).status_code == 201
    assert client.post("/users/register", json={"name": "gail"}).status_code == 409
    assert client.post("/users/register", json={"name": "Hank", "password": "short"}).status_code == 422
