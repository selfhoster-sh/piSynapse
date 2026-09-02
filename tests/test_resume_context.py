"""C-8: contextual follow-up routing.

Layer 0 — deterministic session resolver: an anaphoric follow-up ("devam
edelim son yaptığımız işe") is resolved from the last tool the session
actually executed, never from the utterance alone.
Layer 1 — LLM verdict WITH history + evidence verification: a model verdict is
accepted only when its supporting evidence is verifiable against the
conversation; fabricated evidence is discarded (no guessing).
"""

import asyncio

import pytest

import db as dbmod
import llm.intent as li_mod


@pytest.fixture
def intent_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "ctx.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def _seed_tool_execution(session_id: str, tool_name: str, user_text: str,
                         verification_status: str | None = None):
    """Insert a user->assistant turn linked to a successful tool audit row."""

    async def _go():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, 'user', ?)",
            (session_id, user_text),
        )
        await db.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES (?, 'assistant', ?)",
            (session_id, "İşte sonuçlar"),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT id FROM conversations WHERE session_id = ? AND role = 'assistant' "
            "ORDER BY id DESC LIMIT 1",
            (session_id,),
        )
        asst_id = (await cur.fetchall())[0][0]
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, conversation_id, success, is_summary, verification_status) "
            "VALUES (?, ?, 1, 0, ?)",
            (tool_name, asst_id, verification_status),
        )
        await db.commit()

    asyncio.run(_go())


def _patch_cfg(monkeypatch, fallback="off"):
    def fake_get(key, default=None):
        return {"INTENT_LLM_FALLBACK": fallback, "LLM_BACKEND": "litert"}.get(key, default)

    monkeypatch.setattr(li_mod, "get", fake_get)


# ── context gate at classification time ───────────────────────────────────────

def test_classify_defers_context_dependent_followup(monkeypatch):
    monkeypatch.setattr(li_mod, "_tool_embed_cache", [])
    _patch_cfg(monkeypatch, fallback="on")
    calls = []

    async def bad_call(*a, **k):
        calls.append(1)
        raise RuntimeError("LLM guess must not be consulted")

    monkeypatch.setattr(li_mod, "_llm_classify_call", bad_call)

    intent, group = asyncio.run(li_mod._classify_intent("devam edelim son yaptığımız işe"))
    assert (intent, group) == ("question", None)
    assert not calls  # no blind LLM guess on an utterance that lacks the domain


def test_classify_explicit_keyword_on_context_dependent(monkeypatch):
    # Anaphoric but the user names the domain RIGHT NOW -> keyword routing wins.
    monkeypatch.setattr(li_mod, "_tool_embed_cache", [])
    _patch_cfg(monkeypatch)
    assert asyncio.run(li_mod._classify_intent(
        "devam edelim en son notu düzenliyordun")) == ("action", "notes")
    assert asyncio.run(li_mod._classify_intent(
        "devam edelim en son epostayı gönderiyordun")) == ("action", "email")


def test_is_contextual_followup_alias():
    assert li_mod.is_contextual_followup("devam edelim en son epostayı gönderiyordun")
    assert li_mod.is_contextual_followup("devam edelim")
    assert not li_mod.is_contextual_followup("en son mailleri göster")


# ── Layer 0: deterministic session resolver ───────────────────────────────────

def test_resolve_resume_context_uses_last_tool(intent_db):
    _seed_tool_execution("s1", "send_email", "Son e-postalarımı özetle")
    result = asyncio.run(li_mod.resolve_resume_context(
        "devam edelim son yaptığımız işe", [], session_id="s1"))
    assert result == "email"


def test_resolve_resume_context_skips_shared_utility_tool(intent_db):
    # get_datetime lives in every group -> carries no domain evidence.
    _seed_tool_execution("s2", "get_datetime", "saat kaç")
    result = asyncio.run(li_mod.resolve_resume_context("devam edelim", [], session_id="s2"))
    assert result is None


def test_resolve_resume_context_ignores_failed_tool(intent_db):
    async def _seed_failed():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO conversations (session_id, role, content) VALUES ('s3', 'user', 'mail at')")
        cur = await db.execute(
            "SELECT id FROM conversations WHERE session_id = 's3' ORDER BY id DESC LIMIT 1")
        mid = (await cur.fetchall())[0][0]
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, conversation_id, success, is_summary) "
            "VALUES ('send_email', ?, 0, 0)", (mid,))
        await db.commit()
    asyncio.run(_seed_failed())
    result = asyncio.run(li_mod.resolve_resume_context(
        "devam edelim", [], session_id="s3"))
    assert result is None


def test_resolver_rejects_verification_failed_scope_tool(intent_db):
    # success=1 but the backend re-read could not confirm the create -> the
    # scope-tool create must NOT anchor the session (D-1b).
    _seed_tool_execution("s10", "create_calendar_event", "yarın etkinlik oluştur",
                         verification_status="verification_failed")
    result = asyncio.run(li_mod.resolve_resume_context("devam edelim", [], session_id="s10"))
    assert result is None


def test_resolver_rejects_unverified_scope_tool(intent_db):
    _seed_tool_execution("s11", "create_task", "görev oluştur", verification_status="unverified")
    result = asyncio.run(li_mod.resolve_resume_context("devam edelim", [], session_id="s11"))
    assert result is None


def test_resolver_accepts_verified_scope_tool(intent_db):
    _seed_tool_execution("s12", "create_calendar_event", "yarın etkinlik oluştur",
                         verification_status="verified")
    result = asyncio.run(li_mod.resolve_resume_context("devam edelim", [], session_id="s12"))
    assert result == "calendar"


def test_resolve_resume_context_non_followup_returns_none():
    result = asyncio.run(li_mod.resolve_resume_context(
        "en son mailleri göster", [], session_id=None))
    assert result is None


def test_resolve_resume_context_marker_fallback_without_db():
    # No tool record, but the recent conversation text identifies the domain.
    history = [{"role": "assistant", "content": "İşte e-posta özeti: gönderen: X, konu: Y"}]
    result = asyncio.run(li_mod.resolve_resume_context(
        "devam edelim", history, session_id=None))
    assert result == "email"


def test_resolve_resume_context_no_evidence():
    result = asyncio.run(li_mod.resolve_resume_context(
        "devam edelim", [{"role": "assistant", "content": "merhaba"}], session_id=None))
    assert result is None


# ── Layer 1: LLM verdict + evidence verification ──────────────────────────────

def test_verify_evidence_matches_history():
    history = [{"role": "user", "content": "Son e-postalarımı özetle"}]
    assert li_mod._verify_evidence("son e-postalarımı özetle", "devam et", history)


def test_verify_evidence_rejects_fabrication():
    history = [{"role": "user", "content": "yarın için hava durumunu sor"}]
    assert not li_mod._verify_evidence("haftalık raporu göndermeni istemiştim",
                                       "devam et", history)


def test_verify_evidence_empty_fails():
    assert not li_mod._verify_evidence("", "devam et",
                                       [{"role": "user", "content": "merhaba"}])


def test_llm_resolve_with_evidence_verified(monkeypatch):
    async def fake_call(system, user, max_tokens=20):
        return '{"group": "email", "evidence": "en son e-postamı gönder demiştim"}'

    monkeypatch.setattr(li_mod, "_llm_classify_call", fake_call)
    _patch_cfg(monkeypatch, fallback="on")
    history = [
        {"role": "user", "content": "en son e-postamı gönder demiştim"},
        {"role": "assistant", "content": "Gönderdim"},
    ]
    assert asyncio.run(li_mod.llm_resolve_with_evidence(
        "devam edelim", history)) == ("action", "email")


def test_llm_resolve_with_evidence_rejected_when_fabricated(monkeypatch):
    async def fake_call(system, user, max_tokens=20):
        return '{"group": "tasks", "evidence": "haftalık raporu göndermeni istemiştim"}'

    monkeypatch.setattr(li_mod, "_llm_classify_call", fake_call)
    _patch_cfg(monkeypatch, fallback="on")
    history = [
        {"role": "user", "content": "yarın için hava durumunu sor"},
        {"role": "assistant", "content": "buyur"},
    ]
    assert asyncio.run(li_mod.llm_resolve_with_evidence(
        "devam edelim", history)) == ("question", None)


def test_llm_resolve_with_evidence_question_verdict(monkeypatch):
    async def fake_call(system, user, max_tokens=20):
        return '{"group": "question", "evidence": ""}'

    monkeypatch.setattr(li_mod, "_llm_classify_call", fake_call)
    _patch_cfg(monkeypatch, fallback="on")
    history = [{"role": "assistant", "content": "merhaba"}]
    assert asyncio.run(li_mod.llm_resolve_with_evidence(
        "devam edelim", history)) == ("question", None)


def test_llm_resolve_off_when_fallback_disabled(monkeypatch):
    called = []

    async def fake_call(system, user, max_tokens=20):
        called.append(1)
        return '{"group": "email", "evidence": "x"}'

    monkeypatch.setattr(li_mod, "_llm_classify_call", fake_call)
    _patch_cfg(monkeypatch, fallback="off")
    assert asyncio.run(li_mod.llm_resolve_with_evidence(
        "devam edelim", [{"role": "user", "content": "e-posta"}])) == ("question", None)
    assert not called
