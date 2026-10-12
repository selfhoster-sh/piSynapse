"""main.py health checks + tiny endpoints (test_health patches the checkers,
so their bodies were never exercised).

_check_db / _check_llm / _check_nextcloud against mocked httpx and a tmp DB;
favicon/sw.js FileResponses; /debug beacon ingest (valid + bad payload).
"""
import asyncio

import pytest

import db as dbmod
import main as mainmod
from fastapi.responses import FileResponse


@pytest.fixture
def own_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "h.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


class _Resp:
    def __init__(self, code):
        self.status_code = code


def _fake_client_class(*, code=200, boom=None):
    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **k):
            if boom:
                raise boom
            return _Resp(code)

        async def post(self, url, **k):
            if boom:
                raise boom
            return _Resp(code)

    return _Client


# ── _check_db ──────────────────────────────────────────────────────────────

def test_check_db_ok(own_db):
    assert asyncio.run(mainmod._check_db()) == "ok"


def test_check_db_error(monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(mainmod, "get_db", boom)
    assert asyncio.run(mainmod._check_db()) == "error"


# ── _check_llm ─────────────────────────────────────────────────────────────

def test_check_llm_litert_ok(monkeypatch):
    import httpx

    monkeypatch.setattr(mainmod, "LLM_BACKEND", "litert")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(code=200))
    assert asyncio.run(mainmod._check_llm()) == "ok"


def test_check_llm_ollama_server_error(monkeypatch):
    import httpx

    monkeypatch.setattr(mainmod, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(code=503))
    assert asyncio.run(mainmod._check_llm()) == "error"


def test_check_llm_unreachable(monkeypatch):
    import httpx

    monkeypatch.setattr(mainmod, "LLM_BACKEND", "litert")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(boom=ConnectionError("no route")))
    assert asyncio.run(mainmod._check_llm()) == "error"


# ── _check_nextcloud ───────────────────────────────────────────────────────

def test_check_nextcloud_disabled_when_unconfigured(monkeypatch):
    import config

    monkeypatch.setattr(config, "NEXTCLOUD_URL", "")
    assert asyncio.run(mainmod._check_nextcloud()) == "disabled"


def test_check_nextcloud_ok(monkeypatch):
    import config
    import httpx

    monkeypatch.setattr(config, "NEXTCLOUD_URL", "https://cloud.example")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(code=200))
    assert asyncio.run(mainmod._check_nextcloud()) == "ok"


def test_check_nextcloud_error(monkeypatch):
    import config
    import httpx

    monkeypatch.setattr(config, "NEXTCLOUD_URL", "https://cloud.example")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(code=500))
    assert asyncio.run(mainmod._check_nextcloud()) == "error"


def test_check_nextcloud_unreachable(monkeypatch):
    import config
    import httpx

    monkeypatch.setattr(config, "NEXTCLOUD_URL", "https://cloud.example")
    monkeypatch.setattr(httpx, "AsyncClient", _fake_client_class(boom=TimeoutError("slow")))
    assert asyncio.run(mainmod._check_nextcloud()) == "error"


# ── tiny endpoints ─────────────────────────────────────────────────────────

def test_favicon_and_service_worker_are_fileresponses():
    fav = asyncio.run(mainmod.favicon())
    assert isinstance(fav, FileResponse)
    assert fav.media_type == "image/x-icon"

    sw = asyncio.run(mainmod.service_worker())
    assert isinstance(sw, FileResponse)
    assert sw.headers.get("cache-control") == "no-cache"


class _Req:
    def __init__(self, body, fail=False):
        self._body = body
        self._fail = fail

    async def json(self):
        if self._fail:
            raise ValueError("bad payload")
        return self._body


def test_debug_beacon_valid_payload():
    # _k is dropped; the endpoint must never raise on a good beacon.
    out = asyncio.run(mainmod.debug_ingest(_Req({"_k": "secret", "event": "init"})))
    assert out == {"ok": True}


def test_debug_beacon_bad_payload_is_swallowed():
    out = asyncio.run(mainmod.debug_ingest(_Req({}, fail=True)))
    assert out == {"ok": True}
