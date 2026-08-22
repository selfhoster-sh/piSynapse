"""Tests for LLM payload construction and thinking-tag cleanup."""

import asyncio
import json
import logging

import config
from llm.chat import _llm_request
from llm.intent import contextual_email_followup
from llm.payload import _build_full_messages, _build_payload, trim_messages_for_context
from llm.stream import _is_context_overflow, _shrink_tool_responses
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


async def test_build_full_messages_has_no_qwen3_remnants():
    messages = await _build_full_messages([{"role": "user", "content": "hi"}], [], "", "")
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


class _LeakThenRetryClient(_FakeTextStreamClient):
    """Streams leak-text; captures think-retry POSTs and answers them with a
    real tool_calls object in the backend's non-stream format."""

    def __init__(self, text):
        super().__init__(text)
        self.posts = []

    async def post(self, url, json=None):
        self.posts.append((url, json))

        class _R:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [{
                        "message": {
                            "content": "",
                            "tool_calls": [{
                                "id": "c1",
                                "type": "function",
                                "function": {"name": "get_datetime", "arguments": "{}"},
                            }],
                        },
                    }],
                }

        return _R()


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

    import config as _cfg
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
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

    import config as _cfg
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
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


def test_parse_leaked_tool_call_recovers_call_text():
    from llm.utils import parse_leaked_tool_call

    call = parse_leaked_tool_call("<|tool_call|>call:read_email{id:5}<tool_call|>")
    assert call is not None
    assert call["function"]["name"] == "read_email"
    args = json.loads(call["function"]["arguments"])
    assert args == {"id": 5}

    call2 = parse_leaked_tool_call('Bazı açıklama metni <|tool_call|>call:read_email{"message_id":"3"}<tool_call|> sonrası')
    assert call2 is not None
    assert json.loads(call2["function"]["arguments"]) == {"message_id": "3"}

    assert parse_leaked_tool_call("Tamamen normal bir mesaj") is None
    assert parse_leaked_tool_call("") is None
    assert parse_leaked_tool_call(None) is None


def test_strip_tool_leaks_removes_fragments():
    from llm.utils import strip_tool_leaks

    assert strip_tool_leaks("<|tool_call|>call:read_email{id:5}<tool_call|>") == ""
    assert strip_tool_leaks("Merhaba <|tool_call|>call:read_email{id:5}<tool_call|> gibi") == "Merhaba gibi"
    assert strip_tool_leaks("") == ""
    assert strip_tool_leaks(None) is None


def test_stream_catches_tool_call_tag_leak_without_firing_tool(monkeypatch, caplog):
    import llm.stream as llm_stream

    calls = []

    async def fake_run_tool(name, params, context=None):
        calls.append(name)

    import config as _cfg
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
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

    import config as _cfg
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)
    monkeypatch.setattr(llm_chat, "run_tool", fake_run_tool)

    with caplog.at_level(logging.INFO, logger="piSynapse"):
        result = asyncio.run(
            llm_chat.chat_with_ollama([{"role": "user", "content": "email gönder"}], intent="action")
        )

    assert calls == []
    assert result["reply"].startswith("<|tool_call|>")
    assert any("tool leak" in r.message for r in caplog.records)


def test_chat_think_retry_preserves_reasoning_effort(monkeypatch):
    """Unified retry design: the non-stream retry fires on leak-text and must
    forward reasoning_effort so litert keeps its thinking budget."""
    import llm.chat as llm_chat

    seen = {}

    async def fake_llm_request(msgs, *, use_think=False, use_tools=True, tool_list=None, reasoning_effort=None):
        seen["use_think"] = use_think
        seen["effort"] = reasoning_effort
        content = '<|tool_call|>send_email {"to": "a@b.c"}'
        return ({"choices": [{"message": {"content": content}}]}, {"content": content}, None)

    monkeypatch.setattr(config, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)
    asyncio.run(
        llm_chat.chat_with_ollama(
            [{"role": "user", "content": "email gönder"}],
            intent="action", reasoning_effort="high",
        )
    )
    assert seen["use_think"] is True
    assert seen["effort"] == "high"


def test_chat_no_retry_on_plain_answer_without_leak(monkeypatch):
    """A legitimate plain first answer (no leak) must not pay for an extra
    think-mode LLM call."""
    import llm.chat as llm_chat

    calls = []

    async def fake_llm_request(msgs, *, use_think=False, **kwargs):
        calls.append(use_think)
        return {"done_reason": "stop"}, {"content": "Merhaba!", "tool_calls": []}, None

    monkeypatch.setattr(config, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)
    result = asyncio.run(llm_chat.chat_with_ollama([{"role": "user", "content": "selam"}], intent="action"))
    assert calls == [False]
    assert result["reply"] == "Merhaba!"


def test_stream_litert_leak_retry_recovers_tool_calls(monkeypatch):
    """Parity fix: LiteRT streams get the same think-mode retry as Ollama —
    the retry POST goes to the litert URL with think/effort preserved and the
    recovered tool call is actually executed."""
    import llm.stream as llm_stream

    fake = _LeakThenRetryClient("<|tool_call|>get_current_time")
    executed = []

    async def fake_run_tool(name, params, context=None):
        executed.append(name)
        return "OK Current time"

    async def noop_verification(*args, **kwargs):
        return None

    monkeypatch.setattr(config, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_stream, "_get_client", lambda: fake)
    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)
    monkeypatch.setattr(llm_stream, "run_verification", noop_verification)

    events = _collect_stream_events([{"role": "user", "content": "saat kaç"}], intent="action")

    assert fake.posts, "think-retry POST never fired for litert"
    retry_url, retry_payload = fake.posts[0]
    assert retry_url.endswith("/v1/chat/completions")
    assert "think" not in retry_payload  # litert format: effort, not think flag
    assert retry_payload["reasoning_effort"] == "medium"
    assert executed == ["get_datetime"]
    assert any(ev.get("done") for ev in events)


def test_build_payload_reads_live_sampling_config(monkeypatch):
    monkeypatch.setattr(config, "LLM_TEMPERATURE", 1.2)
    monkeypatch.setattr(config, "LLM_TOP_P", 0.9)
    monkeypatch.setattr(config, "LLM_TOP_K", 80)
    monkeypatch.setattr(config, "LLM_MODEL", "gemma4-e4b")
    payload = _build_payload([{"role": "user", "content": "hi"}], backend="litert", use_tools=False)
    assert payload["temperature"] == 1.2
    assert payload["top_p"] == 0.9
    assert payload["top_k"] == 80
    assert payload["model"] == "gemma4-e4b"


def test_build_payload_reads_live_max_output(monkeypatch):
    monkeypatch.setattr(config, "LLM_MAX_OUTPUT_TOKENS", 4096)
    payload = _build_payload([{"role": "user", "content": "hi"}], backend="litert", use_tools=False)
    assert payload["max_tokens"] == 4096
    assert payload["max_completion_tokens"] == 4096


def test_ollama_payload_includes_num_predict(monkeypatch):
    """Parity fix: MAX_OUTPUT_TOKENS must reach Ollama as options.num_predict,
    not be silently ignored on the main chat path."""
    monkeypatch.setattr(config, "LLM_MAX_OUTPUT_TOKENS", 777)
    payload = _build_payload([{"role": "user", "content": "hi"}], backend="ollama", use_tools=False)
    assert payload["options"]["num_predict"] == 777


def test_litert_payload_includes_max_completion_tokens(monkeypatch):
    """Parity counterpart: the same setting reaches LiteRT via max_completion_tokens."""
    monkeypatch.setattr(config, "LLM_MAX_OUTPUT_TOKENS", 512)
    payload = _build_payload([{"role": "user", "content": "hi"}], backend="litert", use_tools=False)
    assert payload["max_tokens"] == 512
    assert payload["max_completion_tokens"] == 512


def test_contextual_email_followup_positive():
    history = [
        {"role": "assistant", "content": "İşte son e-postalar:\n1. Gönderen: Ollama — Konu: DeepSeek — Özet: ..."},
        {"role": "user", "content": "başka şey sordum"},
    ]
    assert contextual_email_followup("Ollama'dan geleni detaylı anlat", history)
    assert contextual_email_followup("o epostanın içeriğini oku bana", history)


def test_contextual_email_followup_negative():
    history = [{"role": "assistant", "content": "Bugün hava 24 derece olacak."}]
    assert not contextual_email_followup("Ollama'dan geleni detaylı anlat", history)
    assert not contextual_email_followup("Python'da dict nasıl birleştirilir?", history)


def test_is_context_overflow():
    assert _is_context_overflow(RuntimeError("INVALID_ARGUMENT: Input token ids are too long. Exceeding the maximum number of tokens allowed: 5056 >= 6144"))
    assert _is_context_overflow(RuntimeError("context length exceeded"))
    assert not _is_context_overflow(RuntimeError("connection refused"))


def test_shrink_tool_responses_truncates():
    msgs = [{"role": "tool", "tool_name": "read_email", "content": "x" * 2000}]
    _shrink_tool_responses(msgs)
    assert len(msgs[0]["content"]) <= 650
    assert "[content truncated]" in msgs[0]["content"]

    short = [{"role": "tool", "tool_name": "list_emails", "content": "short"}]
    _shrink_tool_responses(short)
    assert short[0]["content"] == "short"


def test_trim_fits_context_by_dropping_oldest():
    sys_msg = {"role": "system", "content": "system " * 200}           # ~200 tokens
    history = [{"role": "user", "content": f"u{i} " * 100} for i in range(6)]
    messages = [sys_msg] + history

    trimmed = trim_messages_for_context(messages, context_window=512, reserved_output=64)
    assert trimmed[0] is sys_msg
    assert trimmed[-1] == history[-1]
    assert len(trimmed) < len(messages)


def test_trim_keeps_current_user_message_when_tight():
    sys_msg = {"role": "system", "content": "sys " * 500}              # ~500 tokens
    user = {"role": "user", "content": "current request " * 20}
    history = [{"role": "user", "content": "old " * 200}, {"role": "assistant", "content": "old reply " * 200}]
    messages = [sys_msg] + history + [user]

    trimmed = trim_messages_for_context(messages, context_window=1024, reserved_output=128)
    assert trimmed[-1] == user
    assert trimmed[0] is sys_msg


def test_trim_drops_orphaned_tool_messages_at_boundary():
    sys_msg = {"role": "system", "content": "sys " * 100}
    # A tool result whose assistant caller is older and dropped
    messages = [
        sys_msg,
        {"role": "user", "content": "a " * 300},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x", "arguments": "{}"}, "id": "c1"}]},
        {"role": "tool", "content": "tool result " * 50, "tool_call_id": "c1"},
        {"role": "user", "content": "b " * 300},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "y", "arguments": "{}"}, "id": "c2"}]},
        {"role": "tool", "content": "tool result " * 50, "tool_call_id": "c2"},
    ]
    trimmed = trim_messages_for_context(messages, context_window=700, reserved_output=64)
    assert trimmed[0] is sys_msg
    assert not trimmed[1].get("role") == "tool" or trimmed[1].get("tool_call_id", "") not in ("c1",)


def test_trim_keeps_chain_intact_when_fits():
    sys_msg = {"role": "system", "content": "sys " * 50}
    messages = [
        sys_msg,
        {"role": "user", "content": "ok"},
        {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "x", "arguments": "{}"}, "id": "c1"}]},
        {"role": "tool", "content": "result", "tool_call_id": "c1"},
    ]
    trimmed = trim_messages_for_context(messages, context_window=2048, reserved_output=128)
    assert trimmed == messages


def test_stream_forwards_tool_group_to_build_full_messages(monkeypatch):
    """chat_with_ollama_stream must forward tool_group into
    _build_full_messages so the group-specific system prompt (e.g. the
    email list-number convention) is used — not just the tool filter.
    """
    import llm.stream as llm_stream

    captured = {}

    async def fake_build(messages, memories, summary, session_id, tool_group=None):
        captured["tool_group"] = tool_group
        return [{"role": "user", "content": "hi"}]

    monkeypatch.setattr(llm_stream, "_build_full_messages", fake_build)
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _FakeStreamClient())
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(llm_stream, "run_verification", _noop)

    _collect_stream_events([{"role": "user", "content": "hi"}], intent="action", tool_group="email")

    assert captured.get("tool_group") == "email"


def test_stream_defaults_tool_group_to_none(monkeypatch):
    """Without an explicit tool_group, _build_full_messages must be called
    with tool_group=None (full default system prompt).
    """
    import llm.stream as llm_stream

    captured = {}

    async def fake_build(messages, memories, summary, session_id, tool_group=None):
        captured["tool_group"] = tool_group
        return [{"role": "user", "content": "hi"}]

    monkeypatch.setattr(llm_stream, "_build_full_messages", fake_build)
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _FakeStreamClient())
    async def _noop(*a, **k):
        return None
    monkeypatch.setattr(llm_stream, "run_verification", _noop)

    _collect_stream_events([{"role": "user", "content": "hi"}], intent="action")

    assert captured.get("tool_group") is None


def test_stream_ollama_error_line_surfaces_as_error_event(monkeypatch):
    """Parity fix: Ollama mid-stream {"error": ...} NDJSON lines must surface
    as an error event instead of being silently ignored."""
    import llm.stream as llm_stream

    class _ErrResp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def raise_for_status(self):
            return None

        async def aiter_lines(self):
            yield '{"message":{"content":"par"},"done":false}'
            yield '{"error":"model runner has unexpectedly stopped"}'

    class _Client:
        def stream(self, method, url, json=None):
            return _ErrResp()

    monkeypatch.setattr(config, "LLM_BACKEND", "ollama")
    monkeypatch.setattr(llm_stream, "_get_client", lambda: _Client())

    events = _collect_stream_events([{"role": "user", "content": "selam"}], intent="action")

    assert any("error" in ev for ev in events)
