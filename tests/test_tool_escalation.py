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
    # the stale "you have NO tools" hint must NOT survive into the
    # escalated round — it would make the model re-emit the marker
    from llm.stream import _TOOL_ASK_HINT as HINT
    assert any(m.get("content") == HINT for m in client.payloads[0]["messages"])
    assert all(m.get("content") != HINT for m in client.payloads[1]["messages"])


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


def test_marker_escalation_synced_on_both_backends(monkeypatch):
    """Hatch must behave identically on litert SSE and ollama NDJSON."""
    import json as _json

    import config as _cfg
    from tests.test_ollama_think_stream import _chunk

    def _o_tool(name):
        return _json.dumps({"message": {"content": "", "tool_calls": [
            {"function": {"name": name, "arguments": {}}}]}, "done": False})

    def _o_done():
        return _json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop"})

    def run(backend, marker_round, tool_round, text_round):
        async def fake_verify(*a, **k):
            pass

        executed: list[str] = []

        async def fake_run_tool(name, params, context=None):
            executed.append(name)
            return "OK"

        rounds = [marker_round, tool_round, text_round]
        holder = {"rounds": list(rounds), "payloads": []}

        class C:
            def stream(self, method, url, json=None):
                holder["payloads"].append(json or {})
                return _SeqResp(holder["rounds"].pop(0))

            async def post(self, url, json=None):
                raise AssertionError("non-stream retry not expected")

        monkeypatch.setattr(_cfg, "LLM_BACKEND", backend)
        monkeypatch.setattr(llm_stream, "_get_client", lambda: C())
        monkeypatch.setattr(llm_stream, "run_verification", fake_verify)
        monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)

        async def drain():
            events = []
            async for ev in llm_stream.chat_with_ollama_stream(
                [{"role": "user", "content": "1. notu oku"}],
                memories=[], think=False, summary="", user_id="t",
                session_id=f"s-{backend}", intent="question", tool_group=None,
                reasoning_effort="",
            ):
                events.append(ev)
            return events

        return asyncio.run(drain()), holder["payloads"], executed

    scenarios = {
        "litert": (
            [_tok("TOOL_NEEDED"), _fin("stop"), _DONE_LINE],
            [_tc("list_notes"), _fin("tool_calls"), _DONE_LINE],
            [_tok("tamam."), _fin("stop"), _DONE_LINE],
        ),
        "ollama": (
            [_chunk(content="TOOL_NEEDED"), _chunk(done=True, reason="stop")],
            [_o_tool("list_notes"), _o_done()],
            [_chunk(content="tamam."), _chunk(done=True, reason="stop")],
        ),
    }
    from llm.stream import _TOOL_ASK_HINT as HINT

    for backend, (mr, tr, xr) in scenarios.items():
        events, payloads, executed = run(backend, mr, tr, xr)
        reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
        assert reasons == ["tools_escalated"], backend
        assert executed == ["list_notes"], backend
        # the frontend pill's data source: tool start/end SSE events must
        # flow identically regardless of backend wire format
        phases = [ev["tool"]["phase"] for ev in events if "tool" in ev]
        assert phases == ["start", "end"], backend
        assert any(ev.get("done") for ev in events), backend
        # hint injected pre-escalation, gone after; tools attached after
        assert not payloads[0].get("tools"), backend
        assert any(m.get("content") == HINT for m in payloads[0]["messages"]), backend
        assert len(payloads[1].get("tools") or []) > 0, backend
        assert all(m.get("content") != HINT for m in payloads[1]["messages"]), backend


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


def test_hallucinated_tool_rejected_when_not_offered(monkeypatch):
    # Laptop field case: during a CALENDAR turn the model hallucinated
    # create_task (a notes/tasks tool it wasn't offered) and the dispatcher
    # executed it — junk tasks in the wrong domain. The stream must reject
    # non-offered tools with a guidance result instead of running them.
    executed: list[str] = []

    async def fake_verify(*a, **k):
        pass

    async def fake_run_tool(name, params, context=None):
        executed.append(name)
        return "OK"

    rounds = [
        [_tc("create_task", '{"summary": "toplantı-test"}'), _fin("tool_calls"), _DONE_LINE],
        [_tok("anladım, takvime ekleyemem."), _fin("stop"), _DONE_LINE],
    ]
    holder = {"rounds": list(rounds), "payloads": []}

    class C:
        def stream(self, method, url, json=None):
            holder["payloads"].append(json or {})
            return _SeqResp(holder["rounds"].pop(0))

        async def post(self, url, json=None):
            raise AssertionError("non-stream retry not expected")

    monkeypatch.setattr(llm_stream, "_get_client", lambda: C())
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)
    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "toplantı-test etkinliğini sil"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s-halluc", intent="action", tool_group="calendar",
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    events = asyncio.run(drain())

    assert executed == []  # never reached the dispatcher
    reasons = [ev["gen_retry"]["reason"] for ev in events if "gen_retry" in ev]
    assert reasons == []
    # second round must carry ONLY calendar-group tools
    second_tools = {t["function"]["name"] for t in (holder["payloads"][1].get("tools") or [])}
    assert "create_task" not in second_tools
    assert any(ev.get("done") for ev in events)


def test_litert_server_parse_failure_recovered_via_leak(monkeypatch):
    # LiteRT server rejects doubled-brace native calls BEFORE we see text:
    # the call arrives embedded in the error message. It must be extracted
    # and executed instead of failing the turn (field case, 2026-08-24).
    class ExplodingResp:
        def raise_for_status(self): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def aiter_bytes(self):
            yield b"data: " + b'{"error": {"message": "litert stream error: INVALID_ARGUMENT: '
            yield b'Failed to parse tool calls from code block: call:create_task{{\\"summary\\": \\"x\\"}}"}}\n\n'

    executed: list[str] = []

    async def fake_verify(*a, **k):
        pass

    async def fake_run_tool(name, params, context=None):
        executed.append((name, params))
        return "OK"

    rounds = [
        [_tok("tamam, oluşturdum."), _fin("stop"), _DONE_LINE],
    ]
    state = {"n": 0}

    class C:
        def stream(self, method, url, json=None):
            if state["n"] == 0:
                state["n"] += 1
                return ExplodingResp()
            return _SeqResp(rounds.pop(0))

    monkeypatch.setattr(llm_stream, "_get_client", lambda: C())
    monkeypatch.setattr(llm_stream, "run_verification", fake_verify)
    monkeypatch.setattr(llm_stream, "run_tool", fake_run_tool)

    async def drain():
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "görev oluştur"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s-litert", intent="action", tool_group="tasks",
            reasoning_effort="",
        ):
            events.append(ev)
        return events

    events = asyncio.run(drain())
    assert executed and executed[0][0] == "create_task"
    assert executed[0][1].get("summary") == "x"
    assert any(ev.get("done") for ev in events)
    assert not any("error" in ev for ev in events)
