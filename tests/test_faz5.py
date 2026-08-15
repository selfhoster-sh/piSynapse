"""FAZ 5 coverage: rate limiter, embedding cosine, widgets, and the llm/chat
tool loop (including the confirmation path).
"""

import asyncio
import json
import time

import numpy as np
import pytest

import main as mainmod
from embedding import cosine_similarity
from llm import chat as lc

# -- Rate limiter --

def test_rate_limiter_allows_burst_then_blocks():
    rl = mainmod._RateLimiter(rpm=3)
    assert all(rl.allow("1.2.3.4") for _ in range(3))
    assert not rl.allow("1.2.3.4")
    assert rl.allow("5.6.7.8")  # different IP unaffected


def test_rate_limiter_expires_old_requests():
    rl = mainmod._RateLimiter(rpm=2)
    assert rl.allow("ip") and rl.allow("ip")
    assert not rl.allow("ip")
    rl._buckets["ip"] = [time.time() - 61.0]  # falls out of the 60s window
    assert rl.allow("ip")


def test_rate_limiter_rejects_new_ip_when_bucket_table_full():
    rl = mainmod._RateLimiter(rpm=5, max_buckets=2)
    assert rl.allow("a") and rl.allow("a")
    assert rl.allow("b") and rl.allow("b")
    assert not rl.allow("c")  # table full and new IP → rejected
    assert rl.allow("a")  # existing IP still passes


def test_rate_limiter_cleanup_drops_stale_buckets():
    rl = mainmod._RateLimiter(rpm=1)
    rl.allow("stale")
    rl._buckets["stale"] = [time.time() - 200.0]
    rl._last_cleanup = time.time() - 61.0
    rl.allow("fresh")
    rl._cleanup(time.time())
    assert "stale" not in rl._buckets
    assert "fresh" in rl._buckets


# -- Embedding cosine --

def test_cosine_identical_vectors_is_one():
    v = np.array([0.5, -1.0, 2.0], dtype="float32")
    assert cosine_similarity(v.tobytes(), v.tobytes()) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    a = np.array([1.0, 0.0], dtype="float32")
    b = np.array([0.0, 1.0], dtype="float32")
    assert cosine_similarity(a.tobytes(), b.tobytes()) == pytest.approx(0.0)


def test_cosine_empty_blob_is_zero():
    assert cosine_similarity(b"", b"\x00\x00\x00\x00") == 0.0


def test_cosine_zero_vector_is_zero():
    z = np.zeros(4, dtype="float32")
    v = np.ones(4, dtype="float32")
    assert cosine_similarity(z.tobytes(), v.tobytes()) == 0.0


# -- Widgets --

def test_widget_weather_missing_city(monkeypatch):
    import config
    from routers import widgets

    monkeypatch.setattr(config, "DEFAULT_CITY", "")
    result = asyncio.run(widgets.widget_weather())
    assert result["error"]
    assert result["summary"] == ""


def test_widget_calendar_returns_events(monkeypatch):
    import calendar_ops
    from routers import widgets

    monkeypatch.setattr(
        calendar_ops, "list_events_today",
        lambda: [{"time": "09:00", "title": "Standup", "uid": "u1"}],
    )
    result = asyncio.run(widgets.widget_calendar())
    assert result["events"] == [{"time": "09:00", "title": "Standup", "uid": "u1"}]


def test_widget_calendar_error_returns_empty(monkeypatch):
    import calendar_ops
    from routers import widgets

    def boom():
        raise RuntimeError("down")

    monkeypatch.setattr(calendar_ops, "list_events_today", boom)
    result = asyncio.run(widgets.widget_calendar())
    assert result["events"] == []


# -- llm/chat tool loop --

async def _noop_verification(*args, **kwargs):
    return None


def test_chat_returns_reply_when_no_tool_calls(monkeypatch):
    async def fake_llm(msgs, **kw):
        return {"done_reason": "stop"}, {"content": "Direct answer", "tool_calls": []}, None

    monkeypatch.setattr(lc, "_llm_request", fake_llm)
    result = asyncio.run(lc.chat_with_ollama([{"role": "user", "content": "hi"}], intent="question"))
    assert result["reply"] == "Direct answer"
    assert result["pending_action"] is None
    assert result["thinking"] == ""


def test_chat_confirm_path_returns_pending_action_and_thinking(monkeypatch):
    confirm_call = {"id": "c1", "function": {"name": "send_email", "arguments": json.dumps({"to": "a@b.com", "subject": "s", "body": "b"})}}

    async def fake_llm(msgs, **kw):
        msg = {"content": "", "reasoning_content": "reasoning text", "tool_calls": [confirm_call]}
        return {"done_reason": "stop"}, msg, None

    monkeypatch.setattr(lc, "_llm_request", fake_llm)
    result = asyncio.run(lc.chat_with_ollama([{"role": "user", "content": "send mail"}]))
    assert result["pending_action"]["tool"] == "send_email"
    assert result["pending_action"]["params"]["to"] == "a@b.com"
    assert result["thinking"] == "reasoning text"


def test_chat_confirm_missing_params_returns_error(monkeypatch):
    confirm_call = {"id": "c1", "function": {"name": "send_email", "arguments": json.dumps({"to": ""})}}

    async def fake_llm(msgs, **kw):
        msg = {"content": "", "tool_calls": [confirm_call]}
        return {"done_reason": "stop"}, msg, None

    monkeypatch.setattr(lc, "_llm_request", fake_llm)
    result = asyncio.run(lc.chat_with_ollama([{"role": "user", "content": "send mail"}]))
    assert result["pending_action"] is None
    assert "requires" in result["reply"]


def test_chat_executes_tool_then_returns_final(monkeypatch):
    calls = []
    tool_results = []

    async def fake_llm(msgs, **kw):
        calls.append(msgs)
        if len(calls) == 1:
            msg = {"content": "", "tool_calls": [{"id": "c1", "function": {"name": "get_weather", "arguments": {}}}]}
            return {"done_reason": "stop"}, msg, None
        return {"done_reason": "stop"}, {"content": "final answer", "tool_calls": []}, None

    async def fake_run_tool(name, args, context):
        tool_results.append((name, args))
        return "OK sunny"

    monkeypatch.setattr(lc, "_llm_request", fake_llm)
    monkeypatch.setattr(lc, "run_tool", fake_run_tool)
    monkeypatch.setattr(lc, "run_verification", _noop_verification)
    result = asyncio.run(lc.chat_with_ollama([{"role": "user", "content": "weather?"}]))
    assert result["reply"] == "final answer"
    assert len(calls) == 2  # tool result fed back for a second model call
    assert tool_results == [("get_weather", {})]
