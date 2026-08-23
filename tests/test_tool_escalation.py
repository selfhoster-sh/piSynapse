"""Tool-escalation escape hatch (2026-08-23).

Pure-chat requests run without tools; a small intent classifier decided that.
When the model signals it needs a tool anyway — via leaked FC syntax or the
literal TOOL_NEEDED marker from the injected system hint — the stream loop
must escalate ONCE to the full toolset and redo the round.
"""

import asyncio

import llm.stream as llm_stream
from tests.test_stream_loop_guards import _DONE_LINE, _fin, _SeqResp, _tc, _tok


class _CaptureClient:
    """Scripted rounds + records every request payload."""

    def __init__(self, rounds):
        self._rounds = list(rounds)
        self.payloads = []

    def stream(self, method, url, json=None):
        self.payloads.append(json or {})
        return _SeqResp(self._rounds.pop(0))

    async def post(self, url, json=None):
        raise AssertionError("non-stream retry not expected")


def _drain(monkeypatch, rounds):
    async def fake_verify(*a, **k):
        pass

    client = _CaptureClient(rounds)
    monkeypatch.setattr(llm_stream, "_get_client", lambda: client)
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "1. notu oku"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s-esc", intent="question", tool_group=None,
            reasoning_effort="",
        ):
            events.append(ev)
        return events, client

    return drain


def test_marker_escalates_to_full_toolset(monkeypatch):
    rounds = [
        [_tok("TOOL_NEEDED"), _fin("stop"), _DONE_LINE],
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        [_tok("işte notların."), _fin("stop"), _DONE_LINE],
    ]
    events, client = asyncio.run(_drain(monkeypatch, rounds)())

    retries = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert retries == ["tools_escalated"]
    executed = [ev["tool"]["name"] for ev in events
                if "tool" in ev and ev["tool"]["phase"] == "end"]
    assert executed == ["list_notes"]
    tokens = "".join(ev["token"] for ev in events if "token" in ev)
    assert "işte notların." in tokens
    # second request must carry the FULL toolset
    assert len(client.payloads) == 3
    assert not client.payloads[0].get("tools")
    assert len(client.payloads[1].get("tools") or []) > 7


def test_leak_syntax_escalates_too(monkeypatch):
    rounds = [
        [_tok("<|tool_call|>call:list_notes{}<|tool_call|>"), _fin("stop"), _DONE_LINE],
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        [_tok("alındı."), _fin("stop"), _DONE_LINE],
    ]
    events, _client = asyncio.run(_drain(monkeypatch, rounds)())
    reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert reasons == ["tools_escalated"]


def test_normal_pure_chat_never_escalates(monkeypatch):
    rounds = [
        [_tok("Selam! Harikayım, teşekkürler."), _fin("stop"), _DONE_LINE],
    ]
    events, _client = asyncio.run(_drain(monkeypatch, rounds)())
    assert not any("gen_retry" in ev for ev in events)
    assert any(ev.get("done") for ev in events)


def test_escalation_happens_once(monkeypatch):
    # Even if the escalated round leaks again, the hatch must not re-arm;
    # the existing think-leak path owns post-escalation recovery.
    rounds = [
        [_tok("TOOL_NEEDED"), _fin("stop"), _DONE_LINE],
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        [_tok("bitti."), _fin("stop"), _DONE_LINE],
    ]
    events, _client = asyncio.run(_drain(monkeypatch, rounds)())
    reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert reasons.count("tools_escalated") == 1
