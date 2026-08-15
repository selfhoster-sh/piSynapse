"""Tests for LLM payload construction and thinking-tag cleanup."""

import asyncio
import json
import logging

import config
from llm.chat import _llm_request
from llm.payload import _build_full_messages, _build_payload
from llm.utils import _THINKING_STRIP_RE


def test_litert_payload_thinking_off():
    payload = _build_payload([{"role": "user", "content": "hi"}], think=False, use_tools=False, backend="litert")
    assert payload["reasoning_effort"] == "none"


def test_litert_payload_includes_sampling_params():
    payload = _build_payload([{"role": "user", "content": "hi"}], think=False, use_tools=False, backend="litert")
    assert payload["top_p"] == config.LLM_TOP_P
    assert payload["top_k"] == config.LLM_TOP_K
    assert payload["temperature"] == config.LLM_TEMPERATURE


def test_litert_payload_thinking_on(monkeypatch):
    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "high")
    payload = _build_payload([{"role": "user", "content": "hi"}], think=True, use_tools=False, backend="litert")
    assert payload["reasoning_effort"] == "high"


def test_litert_payload_invalid_effort_falls_back(monkeypatch):
    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "bogus")
    payload = _build_payload([{"role": "user", "content": "hi"}], think=True, use_tools=False, backend="litert")
    assert payload["reasoning_effort"] == "medium"


def test_ollama_payload_unaffected_by_thinking():
    payload = _build_payload([{"role": "user", "content": "hi"}], think=True, use_tools=False, backend="ollama")
    assert payload["think"] is True
    assert "reasoning_effort" not in payload


def test_build_full_messages_has_no_qwen3_remnants():
    messages = _build_full_messages([{"role": "user", "content": "hi"}], [], "", "")
    assert messages[0]["role"] == "system"
    assert "/no_think" not in messages[0]["content"]
    assert "reason step by step" not in messages[0]["content"]


def test_thinking_strip_re_qwen():
    assert _THINKING_STRIP_RE.sub("", "before <think>secret</think> after") == "before  after"


def test_thinking_strip_re_gemma_channel():
    text = "answer\n<|channel>thought\ninternal reasoning text<channel|>"
    assert "<channel|>" not in _THINKING_STRIP_RE.sub("", text)


class _FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self._content}, "finish_reason": "stop"}]}


class _FakeClient:
    def __init__(self):
        self.last_payload = None

    async def post(self, url, json):
        self.last_payload = json
        return _FakeResponse("ok")


def _capture_llm_request_payload(think):
    fake = _FakeClient()
    llm_chat = __import__("llm.chat", fromlist=["_get_client"])
    orig = llm_chat._get_client
    llm_chat._get_client = lambda: fake
    try:
        asyncio.run(_llm_request([{"role": "user", "content": "hi"}], use_think=think, use_tools=False))
    finally:
        llm_chat._get_client = orig
    return fake.last_payload


def test_llm_request_forwards_think_to_litert():
    payload = _capture_llm_request_payload(True)
    assert payload["reasoning_effort"] == "medium"


def test_llm_request_forwards_no_think_to_litert():
    payload = _capture_llm_request_payload(False)
    assert payload["reasoning_effort"] == "none"


def test_litert_payload_request_effort_beats_config(monkeypatch):
    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "medium")
    payload = _build_payload(
        [{"role": "user", "content": "hi"}], think=True, use_tools=False,
        backend="litert", reasoning_effort="high",
    )
    assert payload["reasoning_effort"] == "high"


def test_litert_payload_invalid_request_effort_falls_back(monkeypatch):
    monkeypatch.setattr(config, "LLM_REASONING_EFFORT", "low")
    payload = _build_payload(
        [{"role": "user", "content": "hi"}], think=True, use_tools=False,
        backend="litert", reasoning_effort="ultra",
    )
    assert payload["reasoning_effort"] == "medium"


def test_litert_payload_request_effort_off_disables():
    payload = _build_payload(
        [{"role": "user", "content": "hi"}], think=True, use_tools=False,
        backend="litert", reasoning_effort="none",
    )
    assert payload["reasoning_effort"] == "none"


def test_clean_reasoning_strips_wrappers():
    from llm.utils import clean_reasoning
    raw = "<|channel>thought\nkullanıcı aslında hava durumunu soruyor.\n<channel|>cevap\n\n\n\n"
    cleaned = clean_reasoning(raw)
    assert "channel" not in cleaned
    assert "kullanıcı" in cleaned
    assert "\n\n\n" not in cleaned


class _FakeStreamResp:
    """Fake httpx streaming response for the tool-call loop.

    First call (no tool result yet) streams a get_datetime tool call;
    once a tool result is present it streams a plain final answer.
    """

    def __init__(self, payload):
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        has_tool_result = any(m.get("role") == "tool" for m in self._payload.get("messages", []))
        if has_tool_result:
            lines = [
                'data: {"choices":[{"delta":{"content":"Done."},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ]
        else:
            lines = [
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1","type":"function","function":{"name":"get_datetime","arguments":""}}]},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}',
                "data: [DONE]",
            ]
        for line in lines:
            yield line

    async def aiter_bytes(self):
        async for line in self.aiter_lines():
            yield line.encode("utf-8") + b"\n"


class _FakeStreamClient:
    def stream(self, method, url, json=None):
        return _FakeStreamResp(json or {})


class _FakeTextStreamResp:
    """Fake streaming response that emits only plain text, never tool calls."""

    def __init__(self, text):
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        lines = [
            f'data: {{"choices":[{{"delta":{{"content":{json.dumps(self._text)}}},"finish_reason":null}}]}}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
            "data: [DONE]",
        ]
        for line in lines:
            yield line

    async def aiter_bytes(self):
        async for line in self.aiter_lines():
            yield line.encode("utf-8") + b"\n"


class _FakeTextStreamClient:
    def __init__(self, text):
        self._text = text

    def stream(self, method, url, json=None):
        return _FakeTextStreamResp(self._text)


def _collect_stream_events(messages, **kwargs):
    llm_stream = __import__("llm.stream", fromlist=["chat_with_ollama_stream"])
    return asyncio.run(
        _drain_stream(llm_stream, messages, kwargs)
    )


async def _drain_stream(llm_stream, messages, kwargs):
    events = []
    async for ev in llm_stream.chat_with_ollama_stream(messages, **kwargs):
        events.append(ev)
    return events


def test_verification_hook_fires_after_successful_tool_call(monkeypatch):
    import llm.stream as llm_stream
    calls = []

    async def fake_verify(name, params, result, success, **kwargs):
        calls.append((name, params, result, success, kwargs))

    monkeypatch.setattr(llm_stream, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _FakeStreamClient())
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)

    _collect_stream_events([{"role": "user", "content": "what time is it?"}], intent="action")

    assert calls, "verification hook was not invoked"
    name, params, result, success, kwargs = calls[0]
    assert name == "get_datetime"
    assert params == {}
    assert result.startswith("Current:")
    assert success is True
    assert kwargs["duration_ms"] >= 0
    assert kwargs["error"] is None


def test_verification_hook_reports_failure_when_tool_raises(monkeypatch):
    import llm.stream as llm_stream
    calls = []

    async def fake_verify(name, params, result, success, **kwargs):
        calls.append((name, params, result, success, kwargs))

    async def failing_tool(name, params, context=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(llm_stream, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _FakeStreamClient())
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)
    monkeypatch.setattr(llm_stream, "run_tool", failing_tool)

    _collect_stream_events([{"role": "user", "content": "what time is it?"}], intent="action")

    assert calls, "verification hook was not invoked"
    name, params, result, success, kwargs = calls[0]
    assert name == "get_datetime"
    assert success is False
    assert result.startswith("ERROR")
    assert kwargs["duration_ms"] >= 0
    assert kwargs["error"].startswith("ERROR")


def test_verification_module_pass_through(monkeypatch):
    import asyncio

    import tool_verification

    calls = []

    async def fake_log(tool_name, params, success, duration_ms=None, error=None):
        calls.append((tool_name, params, success))

    monkeypatch.setattr(tool_verification, "log_tool_call", fake_log)

    asyncio.run(tool_verification.run_verification("get_datetime", {}, "Current: 15 August 2026, 12:00", True))
    asyncio.run(tool_verification.run_verification("list_notes", {}, "ERROR: tool failed", False, duration_ms=5.0, error="ERROR: tool failed"))

    assert len(calls) == 2
    assert calls[0] == ("get_datetime", {}, True)
    assert calls[1][0] == "list_notes"
    assert calls[1][2] is False


def test_check_tool_leak_detects_historical_tag_and_json_echo():
    from llm.utils import _check_tool_leak

    assert _check_tool_leak("<|tool_call|>get_current_time")
    assert _check_tool_leak("<tool_call>get_current_time</tool_call>")
    assert _check_tool_leak('{"tool_calls": [{"function": {"name": "send_email"}}]}')
    assert _check_tool_leak('get_datetime {"timezone": "UTC"}')
    assert not _check_tool_leak("Merhaba, bugün hava güzel.")
    assert not _check_tool_leak("")


def test_stream_catches_tool_call_tag_leak_without_firing_tool(monkeypatch, caplog):
    import llm.stream as llm_stream

    calls = []

    async def fake_run_tool(name, params, context=None):
        calls.append(name)

    monkeypatch.setattr(llm_stream, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _FakeTextStreamClient("<|tool_call|>get_current_time"))
    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)

    with caplog.at_level(logging.INFO, logger="piSynapse"):
        events = _collect_stream_events([{"role": "user", "content": "saat kaç"}], intent="action")

    assert calls == []
    assert any("Tool call pattern detected mid-stream" in r.message for r in caplog.records)
    assert any("No tool call found after suppression" in r.message for r in caplog.records)
    assert any(ev.get("done") for ev in events)


def test_chat_plain_text_cannot_fire_tool(monkeypatch, caplog):
    import llm.chat as llm_chat

    calls = []

    async def fake_run_tool(name, params, context=None):
        calls.append(name)

    async def fake_llm_request(msgs, *, use_think=False, use_tools=True, tool_list=None, reasoning_effort=None):
        content = '<|tool_call|>send_email {"to": "a@b.c"}'
        return ({"choices": [{"message": {"content": content}}]}, {"content": content}, None)

    monkeypatch.setattr(llm_chat, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)
    monkeypatch.setattr(llm_chat, "run_tool", fake_run_tool)

    with caplog.at_level(logging.INFO, logger="piSynapse"):
        result = asyncio.run(
            llm_chat.chat_with_ollama([{"role": "user", "content": "email gönder"}], intent="action")
        )

    assert calls == []
    assert result["reply"].startswith("<|tool_call|>")
    assert any("tool leak" in r.message for r in caplog.records)
