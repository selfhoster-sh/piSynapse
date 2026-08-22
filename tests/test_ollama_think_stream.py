"""Ollama think-mode reasoning must reach the frontend.

Ollama >=0.9 streams thinking as ``message.thinking`` (NDJSON); the older
``reasoning_content`` alias is accepted for compatibility. Regression: the
parser only looked for reasoning_content, so the frontend never showed the
think flow on the ollama backend.
"""

import asyncio

import pytest

import config as _cfg
import llm.chat as llm_chat
import llm.stream as llm_stream


@pytest.fixture(autouse=True)
def _no_email_db(monkeypatch):
    # Chat paths read the per-session email cache from SQLite; keep these
    # unit tests off the real DB (CI has no schema initialized).
    async def _empty(_session_id):
        return []

    monkeypatch.setattr("prompt.get_email_context", _empty)


class _NdjsonResp:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aiter_bytes(self):
        async for line in self.aiter_lines():
            yield line.encode("utf-8") + b"\n"


class _NdjsonClient:
    def __init__(self, rounds):
        self._rounds = list(rounds)

    def stream(self, method, url, json=None):
        return _NdjsonResp(self._rounds.pop(0))

    async def post(self, url, json=None):  # think-retry probe (unused here)
        class _R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "", "tool_calls": []}}]}

        return _R()


def _chunk(content="", thinking="", done=False, reason=None):
    import json
    msg = {"content": content}
    if thinking:
        msg["thinking"] = thinking
    payload = {"message": msg, "done": done}
    if reason:
        payload["done_reason"] = reason
    return json.dumps(payload)


def test_ollama_thinking_streams_to_frontend(monkeypatch):
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _NdjsonClient([[
        _chunk(thinking="Önce düşünüyorum. "),
        _chunk(content="Merhaba!"),
        _chunk(done=True, reason="stop"),
    ]]))

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "selam"}],
            memories=[], think=True, summary="", user_id="t",
            session_id="s", intent="question", tool_group=None,
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    events = asyncio.run(drain())
    reasoning = "".join(ev["reasoning"] for ev in events if "reasoning" in ev)
    tokens = "".join(ev["token"] for ev in events if "token" in ev)
    assert "Önce düşünüyorum." in reasoning
    assert "Merhaba!" in tokens
    assert any(ev.get("done") for ev in events)


def test_ollama_nonstream_thinking_field(monkeypatch):

    async def fake_llm_request(msgs, **kwargs):
        message = {"content": "Cevap.", "thinking": "Kısa içses."}
        return ({"done_reason": "stop"}, message, None)

    monkeypatch.setattr(_cfg, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)

    result = asyncio.run(llm_chat.chat_with_ollama(
        [{"role": "user", "content": "selam"}],
        memories=[], think=True, summary="", user_id="t",
        session_id="s", intent="question", tool_group=None,
        reasoning_effort="",
    ))
    assert "Kısa içses." in result["thinking"]
    assert result["reply"] == "Cevap."
