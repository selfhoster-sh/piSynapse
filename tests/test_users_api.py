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
    assert client.get("/users/me", headers={"x-api-key": bob_key}).status_code == 401
    assert client.get("/users/me", headers={"x-api-key": new_key}).status_code == 200


def test_unauthenticated_users_endpoints_reject(users_api):
    client, _ = users_api
    assert client.get("/users/me").status_code == 401
    assert client.post("/users/key/rotate").status_code == 401
    assert client.get("/users").status_code == 401
