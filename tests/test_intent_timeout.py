"""Analysis A2: intent/classification LLM calls carry a hard timeout.

`_llm_classify_call` is shared by the intent fallback and the
evidence-verified follow-up resolver, for BOTH backends — a 20-token
classification must never ride the shared client's 600s LLM_TIMEOUT: a
stalled engine would freeze the setup phase of every chat for minutes.
The wait_for wraps the shared post, so the guard is engine-agnostic;
on timeout the existing except-path degrades to question/None.
"""
import asyncio
import time

import pytest

import llm.intent as intent_mod


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _SlowClient:
    """A stalled engine: the post never answers."""

    async def post(self, url, json=None):
        await asyncio.sleep(30)
        raise AssertionError("unreachable")


class _FastClient:
    def __init__(self, payload):
        self._payload = payload
        self.payloads = []

    async def post(self, url, json=None):
        self.payloads.append(json)
        return _FakeResp(self._payload)


class _ErrResp:
    def raise_for_status(self):
        raise RuntimeError("engine 500")

    def json(self):
        return {}


class _ErrClient:
    async def post(self, url, json=None):
        return _ErrResp()


def _patch(monkeypatch, client, backend):
    monkeypatch.setattr(intent_mod, "_get_client", lambda: client)
    real_get = intent_mod.get

    def _get(key, default=None):
        if key == "LLM_BACKEND":
            return backend
        if key == "INTENT_LLM_TIMEOUT":
            return 0.3
        return real_get(key, default)

    monkeypatch.setattr(intent_mod, "get", _get)


@pytest.mark.parametrize("backend", ["litert", "ollama"])
def test_stalled_engine_times_out_to_none(monkeypatch, backend):
    _patch(monkeypatch, _SlowClient(), backend)
    t0 = time.monotonic()
    result = asyncio.run(intent_mod._llm_classify_call("sys", "user"))
    elapsed = time.monotonic() - t0
    assert result is None  # degrades, never raises
    assert elapsed < 5  # the 0.3s budget fired, not the 600s client timeout


@pytest.mark.parametrize("backend", ["litert", "ollama"])
def test_fast_response_parsed_normalized(monkeypatch, backend):
    payload = (
        {"choices": [{"message": {"content": "  Calendar  "}}]}
        if backend == "litert"
        else {"message": {"content": "  Notes  "}}
    )
    client = _FastClient(payload)
    _patch(monkeypatch, client, backend)
    result = asyncio.run(intent_mod._llm_classify_call("sys", "user"))
    assert result == ("calendar" if backend == "litert" else "notes")
    # Ollama path must keep think=False so the tiny budget is not burned
    # on hidden reasoning.
    if backend == "ollama":
        assert client.payloads[0]["think"] is False


def test_http_error_degrades_to_none(monkeypatch):
    _patch(monkeypatch, _ErrClient(), "litert")
    assert asyncio.run(intent_mod._llm_classify_call("sys", "user")) is None
