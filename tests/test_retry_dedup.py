"""Retry duplication fix (week-2/3; analysis: retry mükerrer).

When a stream round is retried (overflow / empty / truncation / tool-leak /
escalation), tokens from the DISCARDED attempt had already been streamed to
the client. Both consumers accumulated them anyway:

- routers/chat.py `generate()`: `reply_parts` kept round-1 tokens, so the
  SAVED assistant message contained both attempts' text concatenated.
- static/ui.js: `fullText` kept growing, so the bubble showed the discarded
  text blended into the regenerated reply.

The `gen_retry` event already flows end-to-end; now it also RESETS both
accumulators. The llm layer itself already resets its per-round buffers
(buf/full_text at the top of each round) — no change needed there.
"""
import asyncio
import os
import re
import sys
import types

from fastapi import BackgroundTasks

import routers.chat as rc

ROOT = os.path.join(os.path.dirname(__file__), "..")


# ── Server: the saved reply keeps only the final attempt ─────────────────────

def _run(monkeypatch, events):
    cap = types.SimpleNamespace(saved=[], sse=[])

    async def save_stub(session_id, role, content, **kw):
        cap.saved.append((role, content))

    async def fake_stream(*args, **kwargs):
        for ev in events:
            yield ev

    async def _empty(*a, **k):
        return []

    async def fake_retrieve(*a, **k):
        return [], {"latency_ms": 0.0}

    async def fake_meta(*a, **k):
        return {"summary": ""}

    async def fake_intent(*a, **k):
        return ("action", None)

    async def _not_foreign(session_id, user_id):
        return False

    monkeypatch.setattr(rc, "chat_with_ollama_stream", fake_stream)
    monkeypatch.setattr(rc, "save_message", save_stub)
    monkeypatch.setattr(rc, "session_foreign", _not_foreign)
    monkeypatch.setattr(rc, "get_history", _empty)
    monkeypatch.setattr(rc, "_gather_memories", _empty)
    monkeypatch.setattr(rc, "retrieve_relevant_history", fake_retrieve)
    monkeypatch.setattr(rc, "get_session_meta", fake_meta)
    monkeypatch.setattr(rc, "merge_history", lambda history, retrieved: list(history))

    import llm

    monkeypatch.setattr(llm, "_classify_intent", fake_intent)
    monkeypatch.setattr(llm, "contextual_email_followup", lambda *a, **k: False)

    from main import estimate_tokens as _real_estimate_tokens

    fake_main = types.SimpleNamespace(
        _session_limiter=types.SimpleNamespace(allow=lambda sid: (True, None)),
        _token_limiter=types.SimpleNamespace(
            check=lambda who, tokens: (True, 10**9),
            debit=lambda who, tokens: None,
        ),
        estimate_tokens=_real_estimate_tokens,
    )
    monkeypatch.setitem(sys.modules, "main", fake_main)

    req = rc.ChatRequest(message="test", session_id="s_retry_dedup", user_id="tester")

    async def runner():
        fake_request = types.SimpleNamespace(state=types.SimpleNamespace(user_id="tester"))
        response = await rc.chat_stream(req, fake_request, BackgroundTasks())
        async for sse in response.body_iterator:
            cap.sse.append(sse)

    asyncio.run(runner())
    return cap


def test_gen_retry_drops_discarded_tokens_from_saved_reply(monkeypatch):
    cap = _run(monkeypatch, [
        {"token": "ESKI-DENEME-METNI"},
        {"gen_retry": {"reason": "overflow"}},
        {"token": "YENI-FINAL-METNI"},
        {"done": True, "memories_saved": 0, "reasoning": ""},
    ])
    assistant = [c for r, c in cap.saved if r == "assistant"]
    assert len(assistant) == 1
    assert "YENI-FINAL-METNI" in assistant[0]
    assert "ESKI-DENEME-METNI" not in assistant[0]  # discarded attempt dropped
    # The retry signal still flows to the client (the UI resets on it).
    assert any("gen_retry" in s for s in cap.sse)
    assert any("YENI-FINAL-METNI" in s for s in cap.sse)


def test_double_retry_keeps_only_last_attempt(monkeypatch):
    cap = _run(monkeypatch, [
        {"token": "A1"},
        {"gen_retry": {"reason": "overflow"}},
        {"token": "A2"},
        {"gen_retry": {"reason": "tool_leak"}},
        {"token": "A3"},
        {"done": True, "memories_saved": 0, "reasoning": ""},
    ])
    assistant = [c for r, c in cap.saved if r == "assistant"]
    assert len(assistant) == 1
    assert "A3" in assistant[0]
    assert "A1" not in assistant[0] and "A2" not in assistant[0]


def test_stream_without_retry_untouched(monkeypatch):
    cap = _run(monkeypatch, [
        {"token": "düz akış"},
        {"done": True, "memories_saved": 0, "reasoning": ""},
    ])
    assistant = [c for r, c in cap.saved if r == "assistant"]
    assert assistant == ["düz akış"]


# ── UI source contract: the bubble resets on gen_retry ───────────────────────

def test_ui_gen_retry_resets_accumulators():
    ui = open(os.path.join(ROOT, "static/ui.js"), encoding="utf-8").read()
    m = re.search(r"\} else if\(data\.gen_retry\)\{(.*?)\} else if\(data\.confirm\)\{", ui, re.S)
    assert m, "gen_retry branch not found in ui.js"
    block = m.group(1)
    assert "fullText=''" in block, "UI must reset fullText on gen_retry"
    assert "fullReasoning=''" in block, "UI must reset fullReasoning on gen_retry"
    assert "bubble.innerHTML=''" in block, "UI must clear the streaming bubble on gen_retry"
