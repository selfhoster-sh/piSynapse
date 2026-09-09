"""Personal settings endpoints + PATCH admin gate (M3b)."""

import asyncio
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config as config_module
import db as dbmod
import main as mainmod


@pytest.fixture
def settings_api(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "sett.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setattr(config_module, "DEFAULT_CITY", "")
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)
    from routers.config import router as config_router
    from routers.users import router as users_router

    app.include_router(config_router)
    app.include_router(users_router)
    yield TestClient(app, base_url="http://localhost")
    asyncio.run(dbmod.close_db())


def _keys(settings_api):
    admin, admin_key = asyncio.run(dbmod.create_user("root", is_admin=True))
    user, user_key = asyncio.run(dbmod.create_user("bob"))
    return admin_key, user_key


def test_my_settings_roundtrip_and_isolation(settings_api, monkeypatch):
    monkeypatch.setattr(config_module, "DEFAULT_CITY", "Ankara")
    client = settings_api
    admin_key, user_key = _keys(settings_api)

    got = client.get("/config/my-settings", headers={"x-api-key": user_key})
    assert got.status_code == 200
    assert got.json()["settings"]["DEFAULT_CITY"]["value"] == "Ankara"

    put = client.put("/config/my-settings", json={"values": {"DEFAULT_CITY": "İzmir"}},
                     headers={"x-api-key": user_key})
    assert put.status_code == 200
    assert put.json()["updated"] == ["DEFAULT_CITY"]
    assert client.get("/config/my-settings", headers={"x-api-key": user_key}
                      ).json()["settings"]["DEFAULT_CITY"]["value"] == "İzmir"
    # Admin (no row) still sees the global.
    assert client.get("/config/my-settings", headers={"x-api-key": admin_key}
                      ).json()["settings"]["DEFAULT_CITY"]["value"] == "Ankara"


def test_my_settings_rejects_non_personal_and_bad_option(settings_api):
    client = settings_api
    _, user_key = _keys(settings_api)
    h = {"x-api-key": user_key}
    assert client.put("/config/my-settings", json={"values": {"LLM_BACKEND": "ollama"}},
                      headers=h).status_code == 400
    assert client.put("/config/my-settings", json={"values": {"STT_ENGINE": "nope"}},
                      headers=h).status_code == 400
    assert client.put("/config/my-settings", json={"values": {"UI_LANGUAGE": "tr"}},
                      headers=h).status_code == 200


def test_patch_settings_requires_admin(settings_api, tmp_path, monkeypatch):
    import routers.config as rc

    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("HISTORY_LIMIT=12\n", encoding="utf-8")
    client = settings_api
    admin_key, user_key = _keys(settings_api)
    body = {"values": {"HISTORY_LIMIT": "20"}}
    assert client.patch("/config/settings", json=body, headers={"x-api-key": user_key}
                        ).status_code == 403
    r = client.patch("/config/settings", json=body, headers={"x-api-key": admin_key})
    assert r.status_code == 200
    assert r.json()["updated"] == ["HISTORY_LIMIT"]
    assert "HISTORY_LIMIT=20" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert client.get("/config/my-settings").status_code == 401


def _prefs_db(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "prefs.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    dbmod.invalidate_user_cache()
    return dbmod


def test_system_prompt_uses_user_city(tmp_path, monkeypatch):
    import config as config_module
    import db as dbmod
    from llm.payload import _build_full_messages

    _prefs_db(tmp_path, monkeypatch)
    monkeypatch.setattr(config_module, "DEFAULT_CITY", "Ankara")
    uid = asyncio.run(dbmod.create_user("city-user"))[0]["id"]
    asyncio.run(dbmod.set_user_setting(uid, "DEFAULT_CITY", "İzmir"))

    async def _go():
        msgs = await _build_full_messages(
            [{"role": "user", "content": "hi"}], [], "", "sx",
            tool_group=None, user_id=uid,
        )
        return msgs[0]["content"]

    system = asyncio.run(_go())
    assert "İzmir" in system
    assert "Ankara" not in system


def test_request_language_scoping(tmp_path, monkeypatch):
    import config as config_module
    import db as dbmod
    from llm.payload import _build_full_messages
    from messages import _MESSAGES, get_message, set_request_language

    _prefs_db(tmp_path, monkeypatch)
    uid = asyncio.run(dbmod.create_user("lang-user"))[0]["id"]
    asyncio.run(dbmod.set_user_setting(uid, "UI_LANGUAGE", "tr"))

    async def _go():
        await _build_full_messages(
            [{"role": "user", "content": "hi"}], [], "", "sx",
            tool_group=None, user_id=uid,
        )
        return get_message("llm_unreachable")

    assert asyncio.run(_go()).startswith("Motorla")
    # Outside the request context the live global applies again (whatever
    # this environment resolves — repo .env included).
    set_request_language(None)
    glob = str(config_module.get("UI_LANGUAGE", "en") or "en").strip().lower()
    assert get_message("llm_unreachable") == _MESSAGES["llm_unreachable"].get(glob)


def test_seed_admin_settings_migrates_env_once(tmp_path, monkeypatch):
    import config as config_module
    import db as dbmod

    _prefs_db(tmp_path, monkeypatch)
    monkeypatch.setenv("DEFAULT_CITY", "Akşehir")
    monkeypatch.setenv("UI_LANGUAGE", "tr")
    n1 = asyncio.run(dbmod.seed_admin_settings())
    assert n1 >= 2  # at least the two keys above (env may provide more)
    stored = asyncio.run(dbmod.get_user_settings("default"))
    assert stored["DEFAULT_CITY"] == "Akşehir"
    assert stored["UI_LANGUAGE"] == "tr"
    assert asyncio.run(dbmod.seed_admin_settings()) == 0
    # Never overwrites a deliberate choice.
    asyncio.run(dbmod.set_user_setting("default", "DEFAULT_CITY", "Bodrum"))
    monkeypatch.setenv("DEFAULT_CITY", "Datça")
    assert asyncio.run(dbmod.seed_admin_settings()) == 0
    assert asyncio.run(dbmod.get_user_settings("default"))["DEFAULT_CITY"] == "Bodrum"
    _ = config_module


def test_admin_deletes_user_with_full_wipe(settings_api):
    client = settings_api
    admin_key = client.post("/users/register", json={"name": "root"}).json()["api_key"]
    bob = client.post("/users/register", json={"name": "bob"}).json()
    bob_key, bob_id = bob["api_key"], bob["user"]["id"]
    ah, bh = {"x-api-key": admin_key}, {"x-api-key": bob_key}

    async def _seed():
        import db as dbmod

        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO sessions (id, user_id, name) VALUES ('sx', ?, 'T')", (bob_id,))
        await db.execute(
            "INSERT INTO conversations (session_id, role, content, user_id) "
            "VALUES ('sx', 'user', 'hi', ?)", (bob_id,))
        await db.execute(
            "INSERT INTO memories (user_id, content) VALUES (?, 'fact')", (bob_id,))
        await db.execute(
            "INSERT INTO user_settings (user_id, key, value) VALUES (?, 'DEFAULT_CITY', 'X')",
            (bob_id,))
        await db.commit()

    asyncio.run(_seed())
    # Guards: non-admin cannot delete; nobody deletes themselves or the last admin.
    assert client.delete(f"/users/{bob_id}", headers=bh).status_code == 403
    assert client.delete(f"/users/{bob_id}", headers=ah).status_code == 200
    assert client.delete(f"/users/{bob_id}", headers=ah).status_code == 404
    root_id = client.get("/users/me", headers=ah).json()["user"]["id"]
    assert client.delete(f"/users/{root_id}", headers=ah).status_code == 400

    async def _left():
        import db as dbmod

        db = await dbmod.get_db()
        out = {}
        for tbl, col in (("conversations", "user_id"), ("sessions", "user_id"),
                         ("memories", "user_id"), ("user_settings", "user_id"),
                         ("user_api_keys", "user_id"), ("users", "id")):
            cur = await db.execute(
                f"SELECT COUNT(*) FROM {tbl} WHERE {col} = ?", (bob_id,))
            out[tbl] = (await cur.fetchone())[0]
        return out

    left = asyncio.run(_left())
    assert all(v == 0 for v in left.values()), left
    assert client.get("/users/me", headers=bh).status_code == 401


def test_last_admin_protected(settings_api):
    client = settings_api
    admin_key = client.post("/users/register", json={"name": "solo"}).json()["api_key"]
    ah = {"x-api-key": admin_key}
    solo_id = client.get("/users/me", headers=ah).json()["user"]["id"]
    assert client.delete(f"/users/{solo_id}", headers=ah).status_code in (400, 409)


def test_settings_visibility_split(settings_api, tmp_path, monkeypatch):
    import routers.config as rc

    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("", encoding="utf-8")
    client = settings_api
    admin_key = client.post("/users/register", json={"name": "root"}).json()["api_key"]
    user_key = client.post("/users/register", json={"name": "pleb"}).json()["api_key"]
    ah, uh = {"x-api-key": admin_key}, {"x-api-key": user_key}

    full = client.get("/config/settings", headers=ah).json()
    assert "LLM_BACKEND" in full and "UI_LANGUAGE" in full
    narrow = client.get("/config/settings", headers=uh).json()
    assert "LLM_BACKEND" not in narrow and "NEXTCLOUD_URL" not in narrow
    assert set(narrow) <= set(__import__("config").PERSONAL_KEYS)


def test_registration_toggle_live(settings_api, tmp_path, monkeypatch):
    client = settings_api
    admin_key = client.post("/users/register", json={"name": "root"}).json()["api_key"]
    ah = {"x-api-key": admin_key}
    import routers.config as rc

    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("REGISTRATION_OPEN=on\n", encoding="utf-8")
    assert client.post("/users/register", json={"name": "x1"}).status_code == 201
    # Admin flips the toggle through the normal validated PATCH path.
    r = client.patch("/config/settings", json={"values": {"REGISTRATION_OPEN": "off"}}, headers=ah)
    assert r.status_code == 200
    assert client.post("/users/register", json={"name": "x2"}).status_code == 403
    # PATCH mutates os.environ + module attrs process-wide: restore both so
    # later tests see the default again (monkeypatch only reverts its own sets).
    import config as config_module

    if "REGISTRATION_OPEN" in os.environ:
        del os.environ["REGISTRATION_OPEN"]
    config_module.REGISTRATION_OPEN = "on"
