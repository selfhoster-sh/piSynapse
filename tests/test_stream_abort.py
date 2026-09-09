"""Abort propagation (Faz 5d, audit Y20).

"Durdur" must stop tool execution, not just the router's SSE loop: the
stream itself terminates with a terminal aborted event and never runs
another tool.
"""

import asyncio
import json

import pytest

import llm.stream as llm_stream


@pytest.fixture(autouse=True)
def _no_email_db(monkeypatch):
    async def _empty(_session_id):
        return []

    monkeypatch.setattr("prompt.get_email_context", _empty)


def _tc(name, args="{}", cid="c1"):
    return "data: " + json.dumps({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": cid, "type": "function",
         "function": {"name": name, "arguments": args}},
    ]}}]})


def _fin(reason):
    return "data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": reason}]})


_DONE_LINE = "data: [DONE]"


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
    def __init__(self, rounds):
        self._rounds = list(rounds)
        self.payloads = []

    def stream(self, method, url, json=None):
        self.payloads.append(json)
        return _SeqResp(self._rounds.pop(0))


async def _drain(rounds, abort_event=None, run_tool=None):
    client = _SeqClient(rounds)
    orig = llm_stream._get_client
    llm_stream._get_client = lambda: client
    executed = []

    async def _default_run_tool(name, params, context=None):
        executed.append(name)
        return "OK", None

    orig_run = llm_stream.run_tool
    llm_stream.run_tool = run_tool or _default_run_tool
    orig_verify = llm_stream.run_verification

    async def fake_verify(*a, **k):
        return (None, None)

    llm_stream.run_verification = fake_verify
    try:
        events = []
        async for ev in llm_stream.chat_with_ollama_stream(
            [{"role": "user", "content": "notlarımı listele"}],
            memories=[], think=False, summary="", user_id="t",
            session_id="s", intent="action", tool_group="notes",
            reasoning_effort="", abort_event=abort_event,
        ):
            events.append(ev)
        return events, executed, client
    finally:
        llm_stream._get_client = orig
        llm_stream.run_tool = orig_run
        llm_stream.run_verification = orig_verify


def test_preset_abort_terminates_before_any_llm_round():
    abort = asyncio.Event()
    abort.set()
    events, executed, client = asyncio.run(_drain([], abort_event=abort))
    assert client.payloads == []
    assert executed == []
    assert events == [
        {"done": True, "aborted": True, "session_id": "s", "memories_saved": 0}
    ]


def test_abort_mid_round_stops_remaining_tools():
    abort = asyncio.Event()
    rounds = [[
        "data: " + json.dumps({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c1", "type": "function",
             "function": {"name": "list_notes", "arguments": "{}"}},
            {"index": 1, "id": "c2", "type": "function",
             "function": {"name": "read_note", "arguments": '{"note_id": 1}'}},
        ]}}]}),
        _fin("tool_calls"),
        _DONE_LINE,
    ]]

    orig_run = llm_stream.run_tool
    executed = []

    async def fake_run_tool_abort(name, params, context=None):
        executed.append(name)
        abort.set()  # user hits Durdur while the first tool runs
        return "OK", None

    events, _, _ = asyncio.run(
        _drain(rounds, abort_event=abort, run_tool=fake_run_tool_abort)
    )
    assert executed == ["list_notes"]
    assert {"done": True, "aborted": True, "session_id": "s",
            "memories_saved": 0} in events
