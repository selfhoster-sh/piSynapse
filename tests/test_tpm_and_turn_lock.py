"""Week-1 security pack part 2 (2026-10-11): TPM budget + turn serialization.

Sector-standard gaps closed after the multi-user isolation research:

A. Token-per-minute budget (OWASP LLM10 "Unbounded Consumption"). RPM alone
   cannot bound cost: one long-context request can burn orders of magnitude
   more compute than many short ones. ChatGPT's gateway and BeyondScale both
   treat TPM as the binding constraint for LLM workloads. We pre-check the
   unbounded user input before it reaches the model and debit actual usage
   (history + output) when the stream finishes.

B. One active turn per session (reject policy, per LangSmith/Zylos). Two
   parallel /stream calls on one session would both read the pre-existing
   history and interleave assistant writes, and the second would overwrite
   the first's abort event.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def chatmod():
    import routers.chat as chatmod

    yield chatmod
    chatmod._busy_sessions.clear()


@pytest.fixture
def token_limiter():
    import main as mainmod

    limiter = mainmod._token_limiter
    saved = dict(limiter._windows)
    limiter._windows.clear()
    yield limiter
    limiter._windows.clear()
    limiter._windows.update(saved)


def _req(uid="u1", session_id="s1", message="hello"):
    from routers.chat import ChatRequest

    request = SimpleNamespace(state=SimpleNamespace(user_id=uid, is_admin=False))
    return ChatRequest(message=message, session_id=session_id), request


# ── estimate_tokens ───────────────────────────────────────────────────────────

def test_estimate_tokens_empty_is_zero():
    from main import estimate_tokens

    assert estimate_tokens("") == 0


def test_estimate_tokens_positive_for_short_text():
    from main import estimate_tokens

    assert estimate_tokens("hi") >= 1


def test_estimate_tokens_counts_multibyte_not_char_length():
    # A pure character count would undercount Turkish/CJK; we use UTF-8 bytes.
    from main import estimate_tokens

    ascii_text = "a" * 30
    turkish_text = "ışık" * 10  # 4 chars each, multibyte
    assert estimate_tokens(turkish_text) >= estimate_tokens("i" * 40)
    assert estimate_tokens(ascii_text) == 10  # 30 bytes // 3


# ── _TokenLimiter ─────────────────────────────────────────────────────────────

def test_token_limiter_allows_within_budget(token_limiter):
    ok, remaining = token_limiter.check("u1", 100)
    assert ok is True
    assert remaining == token_limiter.tpm - 100


def test_token_limiter_denies_over_budget(token_limiter):
    token_limiter.debit("u1", token_limiter.tpm)
    ok, remaining = token_limiter.check("u1", 1)
    assert ok is False
    assert remaining == 0


def test_token_limiter_debit_reduces_remaining(token_limiter):
    token_limiter.debit("u1", 5000)
    ok, remaining = token_limiter.check("u1", 100)
    assert ok is True
    assert remaining == token_limiter.tpm - 5000 - 100


def test_token_limiter_users_independent(token_limiter):
    token_limiter.debit("u1", token_limiter.tpm)
    assert token_limiter.check("u1", 1)[0] is False
    assert token_limiter.check("u2", 1)[0] is True  # other user unaffected


def test_token_limiter_zero_debit_is_noop(token_limiter):
    token_limiter.debit("u1", 0)
    assert token_limiter.check("u1", 1)[0] is True


# ── B: one active turn per session ────────────────────────────────────────────

def test_parallel_turn_on_busy_session_rejected_409(chatmod, token_limiter):
    chatmod._busy_sessions.add("s1")
    req, request = _req(session_id="s1")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.chat_stream(req, request, None))
    assert exc.value.status_code == 409
    # The rejected call must not disturb the already-running turn's slot.
    assert "s1" in chatmod._busy_sessions


# ── A: TPM budget denial ──────────────────────────────────────────────────────

def test_over_budget_turn_rejected_429_and_slot_released(chatmod, token_limiter, monkeypatch):
    monkeypatch.setattr(token_limiter, "tpm", 100)
    req, request = _req(session_id="s1", message="hello")  # msg + allowance >> 100
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.chat_stream(req, request, None))
    assert exc.value.status_code == 429
    # The TPM denial happens after the busy slot was taken — it must be released.
    assert "s1" not in chatmod._busy_sessions


def test_different_session_slots_independent(chatmod, token_limiter, monkeypatch):
    chatmod._busy_sessions.add("s1")
    # Force the TPM denial so the s2 call stops BEFORE touching the DB —
    # this proves the busy check passed for s2 (no 409) without a live DB.
    monkeypatch.setattr(token_limiter, "tpm", 0)
    req, request = _req(session_id="s2")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.chat_stream(req, request, None))
    assert exc.value.status_code == 429  # not 409 — s2 was not busy
    assert "s2" not in chatmod._busy_sessions
    assert "s1" in chatmod._busy_sessions  # original slot untouched
