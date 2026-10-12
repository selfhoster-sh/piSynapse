"""POST /chat/ (non-stream) endpoint — was 0% (tests only hit /stream).

Mirrors chat_stream's setup but calls the non-stream `chat_with_ollama`.
Exercised here against in-memory fakes so every branch is controlled:
happy reply, pending_action (confirmation), empty-after-sanitize, the
resume-resolver branch, and the 400/429/500 error paths.
"""
import asyncio
import sys
import types

import pytest
from fastapi import BackgroundTasks, HTTPException

import routers.chat as rc


def _install_fakes(monkeypatch, *, intent=("question", None), result=None,
                   followup=False, resume=None, evidence=("question", None)):
    saved = []

    async def save_stub(session_id, role, content, **kw):
        saved.append((role, content))
        return 1

    async def fake_embed(_msg):
        return b"emb"

    async def _empty(*a, **k):
        return []

    async def fake_retrieve(*a, **k):
        return [], {"latency_ms": 0.0}

    async def fake_meta(*a, **k):
        return {"summary": ""}

    async def fake_intent(*a, **k):
        return intent

    async def fake_chat(*a, **k):
        return result if result is not None else {
            "reply": "Merhaba!", "pending_action": None, "memories_saved": 0, "thinking": None,
        }

    async def fake_resume(*a, **k):
        return resume

    async def fake_evidence(*a, **k):
        return evidence

    monkeypatch.setattr(rc, "save_message", save_stub)
    monkeypatch.setattr(rc, "_shared_query_embedding", fake_embed)
    monkeypatch.setattr(rc, "get_history", _empty)
    monkeypatch.setattr(rc, "_gather_memories", _empty)
    monkeypatch.setattr(rc, "retrieve_relevant_history", fake_retrieve)
    monkeypatch.setattr(rc, "get_session_meta", fake_meta)
    monkeypatch.setattr(rc, "merge_history", lambda h, r: list(h))
    monkeypatch.setattr(rc, "chat_with_ollama", fake_chat)

    import llm

    monkeypatch.setattr(llm, "_classify_intent", fake_intent)
    monkeypatch.setattr(llm, "is_contextual_followup", lambda *_a: followup)
    monkeypatch.setattr(llm, "resolve_resume_context", fake_resume)
    monkeypatch.setattr(llm, "llm_resolve_with_evidence", fake_evidence)

    fake_main = types.SimpleNamespace(
        _session_limiter=types.SimpleNamespace(allow=lambda sid: (True, None)),
    )
    monkeypatch.setitem(sys.modules, "main", fake_main)
    return saved


def _req(message="selam", session_id="s1", images=None):
    return rc.ChatRequest(message=message, session_id=session_id, images=images or [])


def _call(req):
    fake_request = types.SimpleNamespace(state=types.SimpleNamespace(user_id="tester"))
    return asyncio.run(rc.chat_endpoint(req, fake_request, BackgroundTasks()))


def test_happy_path_saves_assistant_reply(monkeypatch):
    saved = _install_fakes(monkeypatch)
    resp = _call(_req())
    assert resp.reply == "Merhaba!"
    assert ("assistant", "Merhaba!") in saved


def test_pending_action_short_circuits_without_save(monkeypatch):
    saved = _install_fakes(monkeypatch, result={
        "reply": "", "pending_action": {"tool": "send_email", "params": {}},
        "memories_saved": 0, "thinking": None,
    })
    resp = _call(_req())
    assert resp.pending_action == {"tool": "send_email", "params": {}}
    assert all(role != "assistant" for role, _c in saved)  # nothing persisted


def test_empty_after_sanitize_not_saved(monkeypatch):
    # A reply that sanitizes to empty must not be persisted.
    saved = _install_fakes(monkeypatch, result={
        "reply": "   \n  ", "pending_action": None, "memories_saved": 0, "thinking": None,
    })
    _call(_req())
    assert all(role != "assistant" for role, _c in saved)


def test_resume_resolver_promotes_question_to_action(monkeypatch):
    saved = _install_fakes(monkeypatch, followup=True, resume="notes")
    resp = _call(_req("devam edelim"))
    assert resp.reply == "Merhaba!"  # ran to completion


def test_resume_evidence_fallback_when_no_resume(monkeypatch):
    saved = _install_fakes(monkeypatch, followup=True, resume=None,
                           evidence=("action", "calendar"))
    _call(_req("peki ya yarın"))
    assert ("assistant", "Merhaba!") in saved


def test_empty_message_400(monkeypatch):
    _install_fakes(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        _call(_req(message="   "))
    assert exc.value.status_code == 400


def test_session_rate_limited_429(monkeypatch):
    _install_fakes(monkeypatch)
    fake_main = sys.modules["main"]
    fake_main._session_limiter = types.SimpleNamespace(allow=lambda sid: (False, None))
    with pytest.raises(HTTPException) as exc:
        _call(_req())
    assert exc.value.status_code == 429


def test_setup_failure_wrapped_as_500(monkeypatch):
    _install_fakes(monkeypatch)

    async def boom(*a, **k):
        raise RuntimeError("backend exploded")

    monkeypatch.setattr(rc, "save_message", boom)
    with pytest.raises(HTTPException) as exc:
        _call(_req())
    assert exc.value.status_code == 500
