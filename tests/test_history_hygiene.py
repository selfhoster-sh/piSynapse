"""History-hygiene regression tests (2026-08-22 self-poisoning incident).

Leaked tool-call text must never reach the conversations table as an
assistant reply — the model imitates its own leaked syntax from history.

Layers covered:
1. Unit: every leak variant observed in the wild sanitizes correctly.
2. Integration: the REAL /chat/stream endpoint persists sanitized text
   (and skips persistence entirely for pure leaks) via mocked storage.
3. Known limitations: documented-unfixed formats pinned as xfail so they
   flip green automatically once the parser learns them.
"""

import asyncio
import json
import sys
import types

import pytest
from fastapi import BackgroundTasks

import routers.chat as rc

LEAK_CLASSIC = "<|tool_call|>call:read_email{id:5}<tool_call|>"
LEAK_MANGLED = "<|tool_call>call:list_notes{{}}<tool_call|>"
LEAK_BARE = "call:list_notes{{}}"


# ------------------------------------------------------------ unit tests --

def test_clean_assistant_reply_drops_pure_leak():
    """Every leak variant seen in the wild must sanitize to empty string."""
    # Original observed forms.
    assert rc._clean_assistant_reply(LEAK_CLASSIC) == ""
    assert rc._clean_assistant_reply(LEAK_MANGLED) == ""
    assert rc._clean_assistant_reply(LEAK_BARE) == ""
    # Several blocks back-to-back within ONE message.
    assert rc._clean_assistant_reply(
        LEAK_CLASSIC + LEAK_MANGLED + LEAK_BARE
        + "<|tool_call|>call:create_note{}<tool_call|>"
    ) == ""
    # Truncated stream: opening tag, closing tag never arrives.
    assert rc._clean_assistant_reply("<|tool_call|>call:list_notes{") == ""
    # Truncated stream: tags present but argument payload cut mid-token.
    assert rc._clean_assistant_reply("call:read_email{id:") == ""
    assert rc._clean_assistant_reply('call:create_note{{"title":') == ""
    # Tags present, payload missing entirely.
    assert rc._clean_assistant_reply("<|tool_call|>call:list_notes<tool_call|>") == ""
    # Nested/doubled wrappers around a valid span.
    assert rc._clean_assistant_reply(
        "<|tool_call|><|tool_call|>call:list_notes{{}}<tool_call|></tool_call|>"
    ) == ""
    assert rc._clean_assistant_reply(
        "<tool_call|><|tool_call|>call:a{}<tool_call|></tool_call|>"
    ) == ""


def test_clean_assistant_reply_keeps_surrounding_text():
    # Leak at the START of the message.
    assert rc._clean_assistant_reply(LEAK_CLASSIC + " Merhaba dünya") == "Merhaba dünya"
    # Leak in the MIDDLE of the message.
    assert rc._clean_assistant_reply("Merhaba " + LEAK_CLASSIC + " dünya") == "Merhaba dünya"
    # Leak at the END of the message.
    assert rc._clean_assistant_reply("Merhaba dünya " + LEAK_MANGLED) == "Merhaba dünya"


def test_clean_assistant_reply_whitespace_only_remainder():
    # Only whitespace survives cleaning -> normalized to empty string.
    assert rc._clean_assistant_reply(LEAK_CLASSIC + "  \n  ") == ""
    assert rc._clean_assistant_reply(LEAK_CLASSIC + "   " + LEAK_MANGLED) == ""
    assert rc._clean_assistant_reply("\n\t" + LEAK_BARE + "\n") == ""


def test_clean_assistant_reply_strips_prefix():
    assert rc._clean_assistant_reply("piSynapse: normal cevap") == "normal cevap"


def test_clean_assistant_reply_handles_empty_and_none():
    assert rc._clean_assistant_reply("") == ""
    assert rc._clean_assistant_reply(None) == ""


# ------------------------------------------------------ integration tests --

def _run_chat_stream(monkeypatch, tokens, message="notlarımı listele"):
    """Drive the REAL /chat/stream endpoint against in-memory fakes."""
    cap = types.SimpleNamespace(calls=[], events=[])

    async def save_stub(session_id, role, content, **kw):
        cap.calls.append((role, content))
        if role == "assistant":
            cap.events.append("assistant_saved")

    async def fake_stream(*args, **kwargs):
        for tok in tokens:
            yield {"token": tok}
        yield {"done": True, "memories_saved": 0, "reasoning": ""}

    async def _empty(*a, **k):
        return []

    async def fake_retrieve(*a, **k):
        return [], {"latency_ms": 0.0}

    async def fake_meta(*a, **k):
        return {"summary": ""}

    async def fake_intent(*a, **k):
        return ("action", None)

    monkeypatch.setattr(rc, "chat_with_ollama_stream", fake_stream)
    monkeypatch.setattr(rc, "save_message", save_stub)
    monkeypatch.setattr(rc, "get_history", _empty)
    monkeypatch.setattr(rc, "_gather_memories", _empty)
    monkeypatch.setattr(rc, "retrieve_relevant_history", fake_retrieve)
    monkeypatch.setattr(rc, "get_session_meta", fake_meta)
    monkeypatch.setattr(rc, "merge_history", lambda history, retrieved: list(history))

    import llm
    monkeypatch.setattr(llm, "_classify_intent", fake_intent)
    monkeypatch.setattr(llm, "contextual_email_followup", lambda *a, **k: False)

    fake_main = types.SimpleNamespace(
        _session_limiter=types.SimpleNamespace(allow=lambda sid: (True, None)),
    )
    monkeypatch.setitem(sys.modules, "main", fake_main)

    req = rc.ChatRequest(
        message=message, session_id="session_hygiene_integration", user_id="tester",
    )
    collected = []

    async def runner():
        response = await rc.chat_stream(req, BackgroundTasks())
        async for sse in response.body_iterator:
            collected.append(sse)
            try:
                obj = json.loads(sse.removeprefix("data: ").strip())
            except ValueError:
                continue
            if isinstance(obj, dict) and obj.get("done") and "token" not in obj:
                cap.events.append("client_done_chunk")

    asyncio.run(runner())
    return cap, collected


def test_stream_save_path_sanitizes_before_persisting(monkeypatch):
    """Prove the real done-branch save goes through the sanitizer."""
    cap, chunks = _run_chat_stream(
        monkeypatch,
        ["İşte notların ", LEAK_CLASSIC, " özeti."],
    )

    saved = [content for role, content in cap.calls if role == "assistant"]
    assert saved == ["İşte notların özeti."], cap.calls

    # Sanitized persist happens BEFORE the done chunk reaches the client.
    assert cap.events.index("assistant_saved") < cap.events.index("client_done_chunk")
    assert any('"done"' in c for c in chunks)


def test_stream_pure_leak_reply_is_not_persisted(monkeypatch):
    """Pure leak => save skipped entirely (no empty row, no fallback write),
    while the client still receives the done event.
    """
    cap, chunks = _run_chat_stream(monkeypatch, [LEAK_MANGLED])

    roles = [role for role, _ in cap.calls]
    assert "assistant" not in roles, cap.calls
    assert ("user", "notlarımı listele") in cap.calls
    assert any('"done"' in c for c in chunks)


# ------------------------------------------------------ known limitations --
# Deliberately UNFIXED: pin today's blind spots as xfail. When the parser
# learns these formats the tests flip green (strict=False allows xpass).

@pytest.mark.xfail(
    reason="known limitation: alternate <tool|call> delimiter unrecognized; "
    "only the bare call: body is stripped, delimiter shells remain",
    strict=False,
)
def test_known_limitation_alternate_delimiter():
    assert rc._clean_assistant_reply("<tool|call>call:list_notes{{}}<tool|call>") == ""


@pytest.mark.xfail(
    reason="known limitation: JSON tool_calls echo is detected upstream "
    "(_check_tool_leak) but strip_tool_leaks has no remover for it",
    strict=False,
)
def test_known_limitation_json_echo_survives_strip():
    assert rc._clean_assistant_reply('[{"name": "list_notes", "arguments": {}}]') == ""
