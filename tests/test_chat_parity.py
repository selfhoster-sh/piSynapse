"""Stream / non-stream parity (Faz 5b, audit K2).

The pure-chat hatch (hint arming + escalation) and the chip fast-path must
behave identically on both paths. The non-stream path silently dropped
tool-needing questions; both now share llm/utils.py helpers.
"""

import asyncio

import config as _cfg
import llm.chat as llm_chat
from llm.utils import _TOOL_ASK_HINT


def _run_parity(monkeypatch, responses, message, intent="question", tool_group=None,
                origin="", think=False):
    """Drive chat_with_ollama with canned rounds; record msgs + tool flags."""
    monkeypatch.setattr(_cfg, "LLM_BACKEND", "litert")
    sent = []
    calls = []

    async def fake_llm_request(msgs, *, use_think=False, use_tools=True,
                               tool_list=None, reasoning_effort=None):
        sent.append(list(msgs))
        calls.append((use_tools, len(tool_list) if tool_list else 0))
        return responses[len(calls) - 1]

    async def fake_run_tool(name, params, context=None):
        return f"OK {name} sonucu", None

    async def fake_verify(*a, **k):
        return (None, None)

    monkeypatch.setattr(llm_chat, "_llm_request", fake_llm_request)
    monkeypatch.setattr(llm_chat, "run_tool", fake_run_tool)
    monkeypatch.setattr(llm_chat, "run_verification", fake_verify)

    result = asyncio.run(llm_chat.chat_with_ollama(
        [{"role": "user", "content": message}],
        memories=[], think=think, summary="", user_id="t",
        session_id="s", intent=intent, tool_group=tool_group,
        reasoning_effort="", origin=origin,
    ))
    return result, sent, calls


def _resp(content="", tool_calls=None):
    message = {"content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return ({"done_reason": "stop"}, message, None)


def _has_hint(msgs):
    return any(m.get("content") == _TOOL_ASK_HINT for m in msgs)


def test_hint_armed_on_tool_domain(monkeypatch):
    result, sent, _ = _run_parity(
        monkeypatch, [_resp("Ankara'da bugün güneşli.")], "Ankara'da hava nasıl?"
    )
    assert _has_hint(sent[0])
    assert "güneşli" in result["reply"]


def test_hint_absent_on_pure_chat(monkeypatch):
    result, sent, calls = _run_parity(
        monkeypatch, [_resp("Geçmiş olsun, bir bitki çayı iyi gider.")],
        "uykum var ama uyuyamıyorum",
    )
    assert not _has_hint(sent[0])
    assert calls[0][0] is False
    assert "çayı" in result["reply"]


def test_marker_escalates_to_tools(monkeypatch):
    result, sent, calls = _run_parity(
        monkeypatch,
        [_resp("TOOL_NEEDED"), _resp("Notlarını listeledim.")],
        "notlarıma bakabilir misin?",
    )
    assert calls[0] == (False, 0)  # pure-chat round first
    assert calls[1][0] is True and calls[1][1] > 0  # escalated redo w/ tools
    assert not _has_hint(sent[1])  # stale hint stripped on escalate
    assert "listeledim" in result["reply"]


def test_chip_fast_path_skips_llm(monkeypatch):
    result, sent, calls = _run_parity(
        monkeypatch, [], "not oluştur", intent="action",
        tool_group="notes", origin="chip",
    )
    assert calls == [] and sent == []
    assert "Notun içeriği" in result["reply"]
