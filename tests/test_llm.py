"""Tests for LLM payload construction and thinking-tag cleanup."""

import asyncio

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
