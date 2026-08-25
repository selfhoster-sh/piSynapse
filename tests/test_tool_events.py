"""SSE tool-status events (2026-08-23 indicator feature).

The stream generator must emit structured tool events so the frontend can
show what the model is doing WITHOUT parsing streamed text:

- {"tool": {"name", "phase": "start"|"end"|"refused", "attempt", "max"}}
  around every run_tool() execution, attempt = prior identical executions + 1.
- {"gen_retry": {"reason": "overflow"|"empty"|"tool_leak"}} whenever a
  generation round has to be retried inside the tool loop.
"""

import asyncio
import logging

import config as _cfg
import llm.stream as llm_stream
from tests.test_stream_loop_guards import (  # noqa: F401  (fixtures import too)
    _DONE_LINE,
    _fin,
    _no_email_db,
    _run,
    _SeqResp,
    _tc,
    _tok,
)


def _tool_events(events):
    return [ev["tool"] for ev in events if "tool" in ev]


def test_tool_start_end_events_emitted(monkeypatch):
    rounds = [
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        [_tok("İşte notların."), _fin("stop"), _DONE_LINE],
    ]
    events, executed, _client = _run(monkeypatch, rounds)

    assert executed == ["list_notes"]
    tev = _tool_events(events)
    assert tev[0] == {"name": "list_notes", "phase": "start", "attempt": 1, "max": 2}
    assert tev[1] == {"name": "list_notes", "phase": "end", "ok": True}
    kinds = [e["phase"] for e in tev]
    assert kinds.index("start") < kinds.index("end")
    assert any(ev.get("done") for ev in events)


def test_refused_event_carries_attempt_counts(monkeypatch, caplog):
    # Pair the repeated call with a fresh tool each round so the
    # already-executed dedup doesn't end the loop before the cap does.
    rounds = [
        [_tc("get_datetime", cid="c1", idx=0), _fin("tool_calls"), _DONE_LINE],
        [_tc("get_datetime", cid="c2", idx=0),
         _tc("read_note", '{"note_id":"5"}', cid="c3", idx=1), _fin("tool_calls"), _DONE_LINE],
        [_tc("get_datetime", cid="c4", idx=0),
         _tc("search_notes", '{"q":"x"}', cid="c5", idx=1), _fin("tool_calls"), _DONE_LINE],
        [_tok("bitti."), _fin("stop"), _DONE_LINE],
    ]
    with caplog.at_level(logging.WARNING, logger="piSynapse"):
        events, executed, _client = _run(monkeypatch, rounds)

    # Refused call never reaches run_tool — executed holds only real runs.
    assert executed == [
        "get_datetime", "get_datetime", "read_note", "search_notes",
    ]
    phases = [e["phase"] for e in _tool_events(events)]
    # 4 real executions (gd×2, read_note, search_notes); refused emits only its own event.
    assert phases.count("start") == 4 and phases.count("end") == 4
    refused = [e for e in _tool_events(events) if e["phase"] == "refused"]
    assert refused == [{"name": "get_datetime", "phase": "refused", "attempt": 3, "max": 2}]


_OVERFLOW = object()


class _OverflowResp:
    """Streaming call that explodes with a context-overflow signature."""

    async def __aenter__(self):
        raise RuntimeError("model maximum context length exceeded")

    async def __aexit__(self, *args):
        return False


class _SeqRoundClient:
    """Pops one scripted round per streaming HTTP call.

    A round is either _OVERFLOW (raises inside __aenter__) or a list of SSE lines.
    """

    def __init__(self, rounds):
        self._rounds = list(rounds)

    def stream(self, method, url, json=None):
        rnd = self._rounds.pop(0)
        if rnd is _OVERFLOW:
            return _OverflowResp()
        return _SeqResp(rnd)

    async def post(self, url, json=None):
        raise AssertionError("think-retry not expected in this test")


def test_gen_retry_event_on_context_overflow(monkeypatch):
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")

    async def fake_verify(*a, **k):
        pass

    client = _SeqRoundClient([
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],   # bloats current_msgs
        _OVERFLOW,                                             # -> gen_retry event
        [_tok("kurtardım."), _fin("stop"), _DONE_LINE],        # recovery text
    ])
    monkeypatch.setattr(llm_stream, "_get_client", lambda: client)
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)

    executed: list[str] = []
    async def fake_run_tool(name, params, context=None):
        executed.append(name)
        return f"OK {name}"

    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "selam"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s", intent="action", tool_group="notes",
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    events = asyncio.run(drain())
    retries = [ev for ev in events if "gen_retry" in ev]
    assert retries == [{"gen_retry": {"reason": "overflow"}}]
    tokens = "".join(ev["token"] for ev in events if "token" in ev)
    assert "kurtardım." in tokens
    assert any(ev.get("done") for ev in events)
