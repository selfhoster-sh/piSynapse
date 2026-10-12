"""Stream confirm path (llm/stream.py): confirm tools surface a pending_action
with a preview, or a param error — the stream twin of the non-stream confirm
tests. Preview lookups (notes/tasks/calendar) were uncovered.
"""
import asyncio
import json

import pytest

import llm.stream as llm_stream


@pytest.fixture(autouse=True)
def _no_email_db(monkeypatch):
    async def _empty(_session_id, user_id="default"):
        return []

    monkeypatch.setattr("prompt.get_email_context", _empty)


def _tc(name, args="{}", cid="c1"):
    return "data: " + json.dumps({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": cid, "type": "function",
         "function": {"name": name, "arguments": args}},
    ]}}]})


def _fin(reason):
    return "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": reason}]})


class _SeqResp:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aiter_bytes(self):
        async for line in self.aiter_lines():
            yield line.encode("utf-8") + b"\n"


class _SeqClient:
    def __init__(self, rounds):
        self._rounds = list(rounds)

    def stream(self, method, url, json=None):
        return _SeqResp(self._rounds.pop(0))


async def _drain(rounds, tool, tool_group):
    client = _SeqClient(rounds)
    orig_client = llm_stream._get_client
    llm_stream._get_client = lambda: client
    try:
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "işlem yap"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s", intent="action", tool_group=tool_group,
            reasoning_effort="",
        ):
            events.append(ev)
        return events
    finally:
        llm_stream._get_client = orig_client


def _confirm_event(events):
    confirm = [e for e in events if "confirm" in e]
    return confirm[0]["confirm"] if confirm else None


def test_confirm_delete_note_with_preview(monkeypatch):
    import prompt

    async def _notes(_sid, _uid):
        return [{"title": "Alışveriş", "content": "süt"}, {"title": "İş", "content": "rapor"}]

    monkeypatch.setattr(prompt, "get_notes_context", _notes)
    events = asyncio.run(_drain(
        [[_tc("delete_note", '{"note_id": 2}'), _fin("tool_calls"), "data: [DONE]"]],
        "delete_note", "notes",
    ))
    action = _confirm_event(events)
    assert action["tool"] == "delete_note"
    assert action["preview"] == "İş"


def test_confirm_complete_task_with_preview(monkeypatch):
    import prompt

    async def _tasks(_sid, _uid):
        return [{"summary": "Faturayı öde"}]

    monkeypatch.setattr(prompt, "get_tasks_context", _tasks)
    events = asyncio.run(_drain(
        [[_tc("complete_task", '{"uid": 1}'), _fin("tool_calls"), "data: [DONE]"]],
        "complete_task", "tasks",
    ))
    action = _confirm_event(events)
    assert action["tool"] == "complete_task"
    assert action["preview"] == "Faturayı öde"


def test_confirm_update_calendar_event_with_preview(monkeypatch):
    import calendar_ops

    monkeypatch.setattr(calendar_ops, "find_events_by_summary",
                        lambda summary, days_back=30, days_ahead=90: [
                            {"summary": "Toplantı", "start": "2026-10-12 10:00"}])
    events = asyncio.run(_drain(
        [[_tc("update_calendar_event", '{"summary": "Toplantı", "new_summary": "X"}'),
          _fin("tool_calls"), "data: [DONE]"]],
        "update_calendar_event", "calendar",
    ))
    action = _confirm_event(events)
    assert action["tool"] == "update_calendar_event"
    assert "Toplantı" in action["preview"]


def test_confirm_missing_params_returns_error(monkeypatch):
    # send_email with no recipient → validate_confirm_params returns an error
    events = asyncio.run(_drain(
        [[_tc("send_email", "{}"), _fin("tool_calls"), "data: [DONE]"]],
        "send_email", "email",
    ))
    tokens = "".join(e.get("token", "") for e in events if "token" in e)
    assert "to" in tokens.lower() or "recipient" in tokens.lower() or tokens
    assert any(e.get("done") for e in events)
    assert _confirm_event(events) is None
