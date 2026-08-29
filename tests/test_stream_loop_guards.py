"""Stream-loop anti-repeat guards (2026-08-22 notes tool-call loop incident).

Fix 3: a repeated tool-call round with NO accumulated text must trigger one
text-only finalize round instead of yielding an empty reply; if that still
produces nothing, a friendly fallback message is emitted.
Fix 4: the exact same tool signature is never executed more than
_MAX_IDENTICAL_EXECUTIONS times per request (side-effect safety).
"""

import asyncio
import json
import logging

import pytest

import config as _cfg
import llm.stream as llm_stream


@pytest.fixture(autouse=True)
def _no_email_db(monkeypatch):
    # Chat paths read the per-session email cache from SQLite; keep these
    # unit tests off the real DB (CI has no schema initialized).
    async def _empty(_session_id):
        return []

    monkeypatch.setattr("prompt.get_email_context", _empty)


class _SeqResp:
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


class _SeqClient:
    """Returns one canned SSE round per streaming HTTP call."""

    def __init__(self, rounds):
        self._rounds = list(rounds)
        self.payloads = []

    def stream(self, method, url, json=None):
        self.payloads.append(json)
        return _SeqResp(self._rounds.pop(0))

    async def post(self, url, json=None):
        # Think-mode retry probe: answer with NO tool calls so the caller
        # falls through to plain-text leak recovery.
        class _R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": "", "tool_calls": []}}]}

        return _R()


def _tc(name, args="{}", cid="c1", idx=0):
    return "data: " + json.dumps({"choices": [{"delta": {"tool_calls": [
        {"index": idx, "id": cid, "type": "function",
         "function": {"name": name, "arguments": args}},
    ]}}]})


def _tok(text):
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]})


def _fin(reason):
    return "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": reason}]})


_DONE_LINE = "data: [DONE]"


def _run(monkeypatch, rounds):
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
    executed = []

    async def fake_run_tool(name, params, context=None):
        executed.append(name)
        return f"OK {name} sonucu", None

    async def fake_verify(*a, **k):
        pass

    client = _SeqClient(rounds)
    monkeypatch.setattr(llm_stream, "_get_client", lambda: client)
    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "notlarımı listele"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s", intent="action", tool_group="notes",
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    events = asyncio.run(drain())
    return events, executed, client


def _run_with_text(monkeypatch, rounds, user_text, group="notes"):
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
    executed = []

    async def fake_run_tool(name, params, context=None):
        executed.append(name)
        return f"OK {name} sonucu", None

    async def fake_verify(*a, **k):
        pass

    client = _SeqClient(rounds)
    monkeypatch.setattr(llm_stream, "_get_client", lambda: client)
    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": user_text}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s", intent="action", tool_group=group,
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    events = asyncio.run(drain())
    return events, executed, client


def test_lookup_then_action_request_injects_continuation_note(monkeypatch):
    rounds = [
        [_tc("list_notes", cid="c1", idx=0), _fin("tool_calls"), _DONE_LINE],
        # Model completes the asked deletion in the 2nd round.
        [_tc("delete_note", '{"note_id":"2"}', cid="c2", idx=0), _fin("tool_calls"), _DONE_LINE],
        [_tok("Silindi."), _fin("stop"), _DONE_LINE],
    ]
    _events, executed, client = _run_with_text(
        monkeypatch, rounds, "az önce listelediğin ikinci notu sil")

    # Delete is confirm-gated: it never executes in-loop; the important part
    # is that the SECOND round's prompt carried the continuation nudge.
    assert executed == ["list_notes"]
    joined = "".join(
        json.dumps(m, ensure_ascii=False)
        for msg in client.payloads[1]["messages"]
        for m in ([msg] if isinstance(msg, dict) else msg)
    )
    assert "Continuation required" in joined
    assert "delete" in joined


def test_lookup_only_request_gets_no_continuation_note(monkeypatch):
    rounds = [
        [_tc("list_notes", cid="c1", idx=0), _fin("tool_calls"), _DONE_LINE],
        [_tok("İşte notların."), _fin("stop"), _DONE_LINE],
    ]
    _events, executed, client = _run_with_text(
        monkeypatch, rounds, "notlarımı listele")

    assert executed == ["list_notes"]
    joined = "".join(
        json.dumps(m, ensure_ascii=False)
        for msg in client.payloads[1]["messages"]
        for m in ([msg] if isinstance(msg, dict) else msg)
    )
    assert "Continuation required" not in joined


def test_dedup_empty_text_triggers_one_textonly_round(monkeypatch, caplog):
    rounds = [
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        # Same call AGAIN with no text produced -> dedup fires -> nudge.
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        # Finalize round: tools are disabled, model answers in plain text.
        [_tok("İşte notların özeti."), _fin("stop"), _DONE_LINE],
    ]
    with caplog.at_level(logging.INFO, logger="piSynapse"):
        events, executed, client = _run(monkeypatch, rounds)

    assert executed == ["list_notes"]  # repeated call never re-executed
    assert any("nudging a text-only final answer" in r.message for r in caplog.records)
    tokens = "".join(ev["token"] for ev in events if "token" in ev)
    assert "İşte notların özeti." in tokens
    assert any(ev.get("done") for ev in events)
    assert not client.payloads[2].get("tools")


def test_dedup_after_nudge_still_empty_yields_fallback(monkeypatch, caplog):
    leak_line = _tok("<|tool_call>call:list_notes{{}}<tool_call|>")
    bare_leak_line = _tok("call:list_notes{{}}")
    rounds = [
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        # Nudge round ignored by the fake model — it leaks the same call as
        # tagged text; recovered and deduped -> nudge consumed.
        [leak_line, _fin("stop"), _DONE_LINE],
        # Still nothing but the same leaked call -> friendly fallback.
        [bare_leak_line, _fin("stop"), _DONE_LINE],
    ]
    with caplog.at_level(logging.INFO, logger="piSynapse"):
        events, executed, _client = _run(monkeypatch, rounds)

    assert executed == ["list_notes"]  # never re-executed
    tokens = [ev["token"] for ev in events if "token" in ev]
    assert llm_stream._EMPTY_ANSWER_FALLBACK in tokens
    assert any(ev.get("done") for ev in events)


def test_identical_signature_executed_at_most_twice(monkeypatch, caplog):
    rounds = [
        [
            _tc("get_datetime", cid="c1", idx=0),
            _tc("list_notes", cid="c2", idx=1),
            _fin("tool_calls"), _DONE_LINE,
        ],
        [
            # get_datetime 2nd execution is still allowed + a NEW distinct tool.
            _tc("get_datetime", cid="c3", idx=0),
            _tc("read_note", '{"note_id":"5"}', cid="c4", idx=1),
            _fin("tool_calls"), _DONE_LINE,
        ],
        [
            # 3rd identical get_datetime must be REFUSED; new tool unaffected.
            _tc("get_datetime", cid="c5", idx=0),
            _tc("search_notes", '{"q":"x"}', cid="c6", idx=1),
            _fin("tool_calls"), _DONE_LINE,
        ],
        [_tok("bitti."), _fin("stop"), _DONE_LINE],
    ]
    with caplog.at_level(logging.WARNING, logger="piSynapse"):
        events, executed, _client = _run(monkeypatch, rounds)

    assert executed == [
        "get_datetime", "list_notes", "get_datetime", "read_note", "search_notes",
    ], executed
    assert any("refusing re-execution" in r.message for r in caplog.records)
    tokens = "".join(ev["token"] for ev in events if "token" in ev)
    assert "bitti." in tokens
    assert any(ev.get("done") for ev in events)
