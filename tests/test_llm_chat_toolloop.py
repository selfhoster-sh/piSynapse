"""Non-stream tool-execution loop (llm/chat.py) — was ~70% (the busy part).

The non-stream twin of the stream loop: run real tool_calls, audit via
run_verification, count save_memory, refuse duplicate side-effect calls,
reject hallucinated tools, and build the confirm (pending_action) path with
its previews. Also covers the parity fix: allowed_names is an EMPTY set (not
None) when no tools are offered, so a hallucinated call in a pure-chat round
is refused instead of executed.
"""
import asyncio

import pytest

import config
import llm.chat as llm_chat


def _tc(name, args="{}", cid="c1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}


def _text_round(content):
    return ({"choices": [{"message": {"content": content}}]},
            {"content": content, "tool_calls": []}, None)


def _tool_round(*calls):
    return ({"choices": [{"message": {"content": "", "tool_calls": list(calls)}}]},
            {"content": "", "tool_calls": list(calls)}, None)


def _run(monkeypatch, responses, *, intent="action", tool_group="notes",
         run_tool=None, validate=None, message="notlarımı listele"):
    seq = list(responses)
    calls = []

    async def fake_req(msgs, **kwargs):
        return seq.pop(0)

    async def fake_tool(name, params, context=None):
        calls.append((name, params))
        if run_tool is not None:
            return run_tool(name, params)
        return "OK", None

    async def fake_verify(*a, **k):
        return (None, "verified")

    monkeypatch.setattr(config, "LLM_BACKEND", "litert")
    monkeypatch.setattr(llm_chat, "_llm_request", fake_req)
    monkeypatch.setattr(llm_chat, "run_tool", fake_tool)
    monkeypatch.setattr(llm_chat, "run_verification", fake_verify)
    if validate is not None:
        monkeypatch.setattr(llm_chat, "validate_confirm_params", validate)

    result = asyncio.run(llm_chat.chat_with_ollama(
        [{"role": "user", "content": message}],
        intent=intent, tool_group=tool_group,
    ))
    return result, calls


def test_tool_executes_then_final_answer(monkeypatch):
    result, calls = _run(monkeypatch, [
        _tool_round(_tc("list_notes")),
        _text_round("İşte notların."),
    ])
    assert calls == [("list_notes", {})]
    assert result["reply"] == "İşte notların."
    assert result["pending_action"] is None


def test_save_memory_is_counted(monkeypatch):
    result, calls = _run(monkeypatch, [
        _tool_round(_tc("save_memory", '{"content": "x"}')),
        _text_round("kaydettim"),
    ], tool_group="memory")
    assert calls == [("save_memory", {"content": "x"})]
    assert result["memories_saved"] == 1


def test_tool_exception_recorded_and_loop_continues(monkeypatch):
    def boom(_name, _params):
        raise RuntimeError("tool down")

    result, calls = _run(monkeypatch, [
        _tool_round(_tc("list_notes")),
        _text_round("toparlandım"),
    ], run_tool=boom)
    assert calls  # it tried
    assert result["reply"] == "toparlandım"


def test_duplicate_side_effect_call_refused(monkeypatch):
    # create_note has max_exec=1: a repeat of the same signature is refused.
    result, calls = _run(monkeypatch, [
        _tool_round(_tc("create_note", '{"title": "A"}')),
        _tool_round(_tc("create_note", '{"title": "A"}')),
        _text_round("bitti"),
    ])
    assert calls == [("create_note", {"title": "A"})]  # executed exactly once
    assert result["reply"] == "bitti"


def test_pure_chat_hallucinated_call_is_refused(monkeypatch):
    # tool_group=None + intent=question → use_tools=False → allowed_names=set():
    # a hallucinated non-confirm call must be refused, never executed (parity).
    result, calls = _run(monkeypatch, [
        _tool_round(_tc("list_notes")),
        _text_round("düz cevap"),
    ], intent="question", tool_group=None)
    assert calls == []
    assert result["reply"] == "düz cevap"


def test_pure_chat_hallucinated_confirm_is_refused(monkeypatch):
    result, calls = _run(monkeypatch, [
        _tool_round(_tc("send_email", '{"to": "a@b.c"}')),
    ], intent="question", tool_group=None)
    assert calls == []
    assert result["reply"].startswith("[Rejected:")


def test_confirm_tool_returns_pending_action(monkeypatch):
    result, calls = _run(monkeypatch, [
        _tool_round(_tc("send_email", '{"to": "a@b.c"}')),
    ], tool_group="email", validate=lambda tool, params: None)
    assert result["pending_action"]["tool"] == "send_email"
    assert calls == []  # confirm tools never auto-execute


def test_confirm_invalid_params_returns_error(monkeypatch):
    result, _calls = _run(monkeypatch, [
        _tool_round(_tc("send_email", "{}")),
    ], tool_group="email", validate=lambda tool, params: "missing recipient")
    assert result["reply"] == "missing recipient"
    assert result["pending_action"] is None


def test_confirm_preview_for_update_calendar_event(monkeypatch):
    import calendar_ops

    async def _noop(*a, **k):
        return []

    monkeypatch.setattr(calendar_ops, "find_events_by_summary",
                        lambda summary, days_back=30, days_ahead=90: [
                            {"summary": "Toplantı", "start": "2026-10-12 10:00"}])

    result, _calls = _run(monkeypatch, [
        _tool_round(_tc("update_calendar_event", '{"summary": "Toplantı", "new_summary": "X"}')),
    ], tool_group="calendar", validate=lambda tool, params: None)
    assert result["pending_action"]["tool"] == "update_calendar_event"
    assert "Toplantı" in result["pending_action"].get("preview", "")
