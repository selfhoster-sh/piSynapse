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
    # second request must carry tools; keyword heuristics on "notu oku"
    # narrow the escalation to the NOTES group instead of all 22
    assert len(client.payloads) == 3
    assert not client.payloads[0].get("tools")
    esc_tools = client.payloads[1].get("tools") or []
    assert 0 < len(esc_tools) <= 7


def test_leak_syntax_escalates_too(monkeypatch):
    rounds = [
        [_tok("<|tool_call|>call:list_notes{}<|tool_call|>"), _fin("stop"), _DONE_LINE],
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        [_tok("alındı."), _fin("stop"), _DONE_LINE],
    ]
    events, client = asyncio.run(_drain(monkeypatch, rounds)())
    reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert reasons == ["tools_escalated"]
    # leaked tool name list_notes -> NOTES group (7), not the full set
    assert len(client.payloads[1].get("tools") or []) == 7


def test_marker_without_hints_falls_back_to_combined(monkeypatch):
    import llm.intent as li
    monkeypatch.setattr(li, "_keyword_group", lambda m: None)
    rounds = [
        [_tok("TOOL_NEEDED"), _fin("stop"), _DONE_LINE],
        [_tc("get_weather"), _fin("tool_calls"), _DONE_LINE],
        [_tok("güneşli."), _fin("stop"), _DONE_LINE],
    ]
    events, client = asyncio.run(_drain(monkeypatch, rounds)())
    reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert reasons == ["tools_escalated"]
    # no name, no keywords -> combined fallback
    assert len(client.payloads[1].get("tools") or []) > 7


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


class _CountingResp:
    """_SeqResp that remembers how many SSE lines the loop consumed."""

    def __init__(self, lines):
        self._lines = lines
        self.consumed = 0

    def raise_for_status(self):
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def aiter_bytes(self):
        # SSE lines are newline-terminated — _iter_sse_lines splits on b"\n".
        for line in self._lines:
            self.consumed += 1
            yield line.encode("utf-8") + b"\n"


def test_marker_aborts_round_before_it_finishes(monkeypatch):
    # Round 1: marker arrives in chunk 2, then the model rambles on for
    # several more chunks. The hatch must cut the stream immediately —
    # most of the round is never read.
    trailing = [_tok(f" gereksiz cümle {i}") for i in range(6)]
    lines = [_tok("TOOL_NEEDED")] + trailing + [_fin("stop"), _DONE_LINE]
    resp = _CountingResp(lines)

    client = _CaptureClient([])
    client.stream = lambda method, url, json=None: resp

    async def fake_verify(*a, **k):
        pass

    monkeypatch.setattr(llm_stream, "_get_client", lambda: client)
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)

    from tests.test_stream_loop_guards import _SeqResp as _SR  # noqa: F401

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "bunu halleder misin"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s-abort", intent="question", tool_group=None,
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    # serve escalation + recovery rounds after the aborted one
    client._rounds = [
        [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
        [_tok("tamam."), _fin("stop"), _DONE_LINE],
    ]
    def multi_stream(method, url, json=None):
        nonlocal resp
        if resp.consumed and client._rounds:
            return _SeqResp(client._rounds.pop(0))
        return resp

    client.stream = multi_stream
    events = asyncio.run(drain())

    reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert reasons == ["tools_escalated"]
    assert any(ev.get("done") for ev in events)
    # marker chunk (line 1) + a couple of chunks at most were read; the six
    # trailing rambling chunks were abandoned mid-stream
    assert resp.consumed <= 4, f"consumed {resp.consumed}/{len(lines)} lines"
