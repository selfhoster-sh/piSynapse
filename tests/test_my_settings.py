"""Personal settings endpoints + PATCH admin gate (M3b)."""

import asyncio

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

    app.include_router(config_router)
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
