"""Non-stream loop anti-repeat guards (mirror of test_stream_loop_guards.py).

Fix 3: a repeated tool-call round with NO accumulated text must trigger one
text-only finalize round instead of returning an empty reply; if that still
produces nothing, a friendly fallback message is returned.
Fix 4: the exact same tool signature is never executed more than
MAX_IDENTICAL_EXECUTIONS times per request (side-effect safety).
"""

import logging

import pytest

import config as _cfg
import llm.chat as llm_chat


@pytest.fixture(autouse=True)
def _no_email_db(monkeypatch):
    # Chat paths read the per-session email cache from SQLite; keep these
    # unit tests off the real DB (CI has no schema initialized).
    async def _empty(_session_id):
        return []

    monkeypatch.setattr("prompt.get_email_context", _empty)


def _tc(name, args="{}", cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}


def _resp(content="", tool_calls=None):
    message = {"content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return ({"done_reason": "stop"}, message, None)


def _run(monkeypatch, responses):
    """Feed canned _llm_request responses; record per-call use_tools flag."""
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
    executed = []
    calls = []

    async def fake_llm_request(msgs, *, use_think=False, use_tools=True,
                               tool_list=None, reasoning_effort=None):
        calls.append(use_tools)
        return responses[len([c for c in calls]) - 1]

    async def fake_run_tool(name, params, context=None):
        executed.append(name)
        return f"OK {name} sonucu", None

    async def fake_verify(*a, **k):
        return (None, None)

    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)
    monkeypatch.setattr(llm_chat, "run_tool", fake_run_tool)
    monkeypatch.setattr(llm_chat, "run_verification", fake_verify)

    import asyncio
    result = asyncio.run(llm_chat.chat_with_ollama(
        [{"role": "user", "content": "notlarımı listele"}],
        memories=[], think=False, summary="", user_id="t",
        session_id="s", intent="action", tool_group="notes",
        reasoning_effort="",
    ))
    return result, executed, calls


def test_dedup_empty_text_triggers_one_textonly_round(monkeypatch, caplog):
    tc = _tc("list_notes")
    responses = [
        _resp(tool_calls=[tc]),
        # Same call AGAIN with no text produced -> dedup fires -> nudge.
        _resp(tool_calls=[tc]),
        # Finalize round: tools are disabled, model answers in plain text.
        _resp("İşte notların özeti."),
    ]
    with caplog.at_level(logging.INFO, logger="piSynapse"):
        result, executed, calls = _run(monkeypatch, responses)

    assert executed == ["list_notes"]  # repeated call never re-executed
    assert any("nudging a text-only final answer" in r.message for r in caplog.records)
    assert "İşte notların özeti." in result["reply"]
    assert result["pending_action"] is None
    assert calls[2] is False  # nudge round runs without tools


def test_dedup_after_nudge_still_empty_yields_fallback(monkeypatch, caplog):
    tc = _tc("list_notes")
    responses = [
        _resp(tool_calls=[tc]),
        # Nudge round ignored by the fake model — same call again -> nudge used.
        _resp(tool_calls=[tc]),
        # Still nothing but the same leaked call -> friendly fallback.
        _resp(tool_calls=[tc]),
    ]
    with caplog.at_level(logging.INFO, logger="piSynapse"):
        result, executed, _calls = _run(monkeypatch, responses)

    assert executed == ["list_notes"]  # never re-executed
    assert result["reply"] == llm_chat._EMPTY_ANSWER_FALLBACK
    assert result["pending_action"] is None


def test_identical_signature_executed_at_most_twice(monkeypatch, caplog):
    responses = [
        _resp(tool_calls=[
            _tc("get_datetime", cid="c1"),
            _tc("list_notes", cid="c2"),
        ]),
        _resp(tool_calls=[
            # get_datetime 2nd execution is still allowed + a NEW distinct tool.
            _tc("get_datetime", cid="c3"),
            _tc("read_note", '{"note_id":"5"}', cid="c4"),
        ]),
        _resp(tool_calls=[
            # 3rd identical get_datetime must be REFUSED; new tool unaffected.
            _tc("get_datetime", cid="c5"),
            _tc("search_notes", '{"q":"x"}', cid="c6"),
        ]),
        _resp("bitti."),
    ]
    with caplog.at_level(logging.WARNING, logger="piSynapse"):
        result, executed, _calls = _run(monkeypatch, responses)

    assert executed == [
        "get_datetime", "list_notes", "get_datetime", "read_note", "search_notes",
    ], executed
    assert any("refusing re-execution" in r.message for r in caplog.records)
    assert "bitti." in result["reply"]
