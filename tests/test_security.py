"""Tests for main.py security middleware and routers/config.py hardening.

Covers the FAZ 1 fixes: /debug beacon token auth + rate limit + body cap,
TRUSTED_HOSTS safe default, and newline rejection in settings writes.
"""

import asyncio
import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import main as mainmod


@pytest.fixture
def sec_app():
    app = FastAPI()
    app.middleware("http")(mainmod.trusted_host_middleware)
    app.middleware("http")(mainmod.security_middleware)

    @app.post("/debug")
    async def debug():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.post("/api/thing")
    async def api_thing():
        return {"ok": True}

    return app


@pytest.fixture
def client(sec_app, monkeypatch):
    monkeypatch.setattr(mainmod, "API_KEY", "secret-key")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", set())
    return TestClient(sec_app, base_url="http://localhost")


def test_local_trusted_hosts_contains_loopback():
    allowed = mainmod._LOCAL_TRUSTED_HOSTS
    assert "localhost" in allowed
    assert "127.0.0.1" in allowed
    assert "::1" in allowed


def test_health_is_exempt(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_protected_path_requires_api_key(client):
    r = client.post("/api/thing")
    assert r.status_code == 401


def test_protected_path_accepts_valid_api_key(client):
    r = client.post("/api/thing", headers={"x-api-key": "secret-key"})
    assert r.status_code == 200


def test_debug_requires_query_token(client):
    r = client.post("/debug")
    assert r.status_code == 401
    r = client.post("/debug?k=wrong")
    assert r.status_code == 401


def test_debug_accepts_valid_query_token(client):
    r = client.post("/debug?k=secret-key")
    assert r.status_code == 200


def test_debug_is_rate_limited(client, monkeypatch):
    monkeypatch.setattr(mainmod, "_rate_limiter", mainmod._RateLimiter(rpm=2))
    assert client.post("/debug?k=secret-key").status_code == 200
    assert client.post("/debug?k=secret-key").status_code == 200
    assert client.post("/debug?k=secret-key").status_code == 429


def test_debug_body_capped_at_8kb(client):
    big = "x" * (8 * 1024 + 10)
    r = client.post("/debug?k=secret-key", content=big)
    assert r.status_code == 413


def test_trusted_host_auto_default_allows_local_and_rejects_foreign(client):
    assert client.get("/health", headers={"host": "localhost"}).status_code == 200
    assert client.get("/health", headers={"host": "evil.example.com"}).status_code == 403


def test_trusted_host_explicit_set(sec_app, monkeypatch):
    monkeypatch.setattr(mainmod, "API_KEY", "secret-key")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", {"myhost.local"})
    c = TestClient(sec_app)
    assert c.get("/health", headers={"host": "myhost.local"}).status_code == 200
    assert c.get("/health", headers={"host": "other.local"}).status_code == 403


def test_trusted_host_star_always_allows(sec_app, monkeypatch):
    monkeypatch.setattr(mainmod, "API_KEY", "secret-key")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", {"*"})
    c = TestClient(sec_app)
    assert c.get("/health", headers={"host": "anything.example.com"}).status_code == 200


# -- routers/config.py: newline injection guard --

def test_update_settings_rejects_newline_in_value(tmp_path, monkeypatch):
    import routers.config as rc
    from routers.config import SettingsUpdate

    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / "env_test")
    (tmp_path / "env_test").write_text("ASSISTANT_USER=old\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(rc.update_settings(SettingsUpdate(values={"ASSISTANT_USER": "bob\nAPI_KEY=evil"})))
    assert exc.value.status_code == 400
    assert "newlines" in exc.value.detail


def test_update_settings_is_atomic_on_multi_key_failure(tmp_path, monkeypatch):
    """If any key in a multi-key PATCH fails, NO key may be applied to
    os.environ (previously earlier keys were mutated before the failure,
    leaving os.environ out of sync with .env and the module attributes).
    """
    import routers.config as rc
    from routers.config import SettingsUpdate

    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / "env_test")
    (tmp_path / "env_test").write_text("LLM_TEMPERATURE=0.6\n", encoding="utf-8")

    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)
    monkeypatch.delenv("LLM_MAX_OUTPUT_TOKENS", raising=False)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(rc.update_settings(SettingsUpdate(values={
            "LLM_TEMPERATURE": "0.9",          # valid
            "LLM_MAX_OUTPUT_TOKENS": "99999",  # exceeds schema max → 400
        })))
    assert exc.value.status_code == 400

    assert os.environ.get("LLM_TEMPERATURE") is None
    assert os.environ.get("LLM_MAX_OUTPUT_TOKENS") is None
    assert (tmp_path / "env_test").read_text(encoding="utf-8") == "LLM_TEMPERATURE=0.6\n"


def test_update_settings_applies_all_keys_on_success(tmp_path, monkeypatch):
    import routers.config as rc
    from routers.config import SettingsUpdate

    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / "env_test")
    (tmp_path / "env_test").write_text("LLM_TEMPERATURE=0.6\n", encoding="utf-8")

    monkeypatch.delenv("LLM_TEMPERATURE", raising=False)

    resp = asyncio.run(rc.update_settings(SettingsUpdate(values={"LLM_TEMPERATURE": "0.9"})))
    assert resp["ok"] is True
    assert os.environ.get("LLM_TEMPERATURE") == "0.9"
    assert "LLM_TEMPERATURE=0.9" in (tmp_path / "env_test").read_text(encoding="utf-8")


def test_fail_closed_returns_503_without_configured_key(monkeypatch):
    """Fail-closed auth: no API_KEY configured → protected routes are 503,
    never left open (regression guard for the open-by-default behavior).
    """
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)

    @app.post("/api/thing")
    async def api_thing():
        return {"ok": True}

    monkeypatch.setattr(mainmod, "API_KEY", "")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", set())
    c = TestClient(app, base_url="http://localhost")
    assert c.post("/api/thing").status_code == 503
    assert c.post("/api/thing", headers={"x-api-key": "anything"}).status_code == 503


def test_debug_disabled_without_configured_key(monkeypatch):
    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)

    @app.post("/debug")
    async def debug():
        return {"ok": True}

    monkeypatch.setattr(mainmod, "API_KEY", "")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", set())
    c = TestClient(app, base_url="http://localhost")
    assert c.post("/debug").status_code == 403


def test_hardening_headers_present():
    app = FastAPI()
    app.middleware("http")(mainmod.hardening_headers_middleware)

    @app.get("/")
    async def root():
        return {"ok": True}

    r = TestClient(app).get("/")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "geolocation=()" in r.headers["permissions-policy"]
    assert "strict-transport-security" not in r.headers  # plaintext HTTP
