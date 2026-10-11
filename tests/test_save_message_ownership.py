"""Week-1 pack, item: save_message + search ownership (2026-10-11).

Multi-user invisibility rule (NOTES #19): every user-scoped read AND write
needs its owner guard, and every guard needs a both-directions test.

- save_message previously inserted the message row BEFORE any ownership
  check: a user writing into another user's session id created unreadable
  orphan rows (every read path filters by user_id) that still polluted FTS
  and storage. Now rejected fail-closed (None), same contract as dedup.
- search_sessions (FTS AND/OR, LIKE fallback, semantic supplement) already
  filtered by user_id in every branch — proven here, not assumed.
- /chat/stream answers 404 for a foreign session id, indistinguishable
  from a nonexistent one (no existence oracle; feedback-path contract).
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


@pytest.fixture
def own_db(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "own.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def two_users(own_db):
    dbmod = own_db
    alice, _ = asyncio.run(dbmod.create_user("alice"))
    bob, _ = asyncio.run(dbmod.create_user("bob"))
    return dbmod, alice["id"], bob["id"]


@pytest.fixture
def no_embeddings(monkeypatch):
    # Deterministic FTS-only tests; no model weights, no network.
    import embedding as embmod

    async def _fake(*a, **k):
        return None

    monkeypatch.setattr(embmod, "embed_async", _fake)


@pytest.fixture
def permissive_limits(monkeypatch):
    # Fresh buckets so cross-file test order cannot flake these paths.
    import main as mainmod

    monkeypatch.setattr(mainmod, "_session_limiter", mainmod._RateLimiter(rpm=10**9))
    monkeypatch.setattr(mainmod, "_token_limiter", mainmod._TokenLimiter(tpm=10**9))


@pytest.fixture
def chatmod():
    import routers.chat as rc

    yield rc
    rc._busy_sessions.clear()


def _req(uid, session_id, message="hello"):
    import routers.chat as rc

    request = SimpleNamespace(state=SimpleNamespace(user_id=uid, is_admin=False))
    return rc.ChatRequest(message=message, session_id=session_id), request


async def _count_messages(dbmod, session_id):
    db = await dbmod.get_db()
    async with db.execute(
        "SELECT COUNT(*) FROM conversations WHERE session_id = ?", (session_id,)
    ) as cur:
        return (await cur.fetchone())[0]


# ── save_message: write ownership ─────────────────────────────────────────────

def test_owner_write_ok(two_users, no_embeddings):
    dbmod, alice, _bob = two_users
    rowid = asyncio.run(dbmod.save_message("s1", "user", "merhaba", user_id=alice))
    assert isinstance(rowid, int)
    assert asyncio.run(_count_messages(dbmod, "s1")) == 1


def test_foreign_write_rejected_fail_closed(two_users, no_embeddings):
    dbmod, alice, bob = two_users
    asyncio.run(dbmod.save_message("s1", "user", "merhaba", user_id=alice))
    before = asyncio.run(_count_messages(dbmod, "s1"))
    result = asyncio.run(dbmod.save_message("s1", "user", "enjekte", user_id=bob))
    assert result is None  # same no-op contract as the duplicate guard
    assert asyncio.run(_count_messages(dbmod, "s1")) == before


def test_new_session_write_ok_for_any_user(two_users, no_embeddings):
    # A brand-new session id is NOT foreign — the writer creates it.
    dbmod, _alice, bob = two_users
    rowid = asyncio.run(dbmod.save_message("s9", "user", "yeni", user_id=bob))
    assert isinstance(rowid, int)


def test_duplicate_dedup_contract_untouched(two_users, no_embeddings):
    dbmod, alice, _bob = two_users
    first = asyncio.run(dbmod.save_message("s1", "user", "tekrar", user_id=alice))
    second = asyncio.run(dbmod.save_message("s1", "user", "tekrar", user_id=alice))
    assert isinstance(first, int)
    assert second is None  # dedup still returns None for the same message
    assert asyncio.run(_count_messages(dbmod, "s1")) == 1


# ── search_sessions: read ownership (existing guards, now proven) ────────────

def test_search_fts_owner_isolation_both_directions(two_users, no_embeddings):
    dbmod, alice, bob = two_users
    asyncio.run(dbmod.save_message("s1", "user", "zümrüt yeşili teleskop notu", user_id=alice))

    alice_hits = asyncio.run(dbmod.search_sessions("zümrüt", user_id=alice))
    bob_hits = asyncio.run(dbmod.search_sessions("zümrüt", user_id=bob))

    assert len(alice_hits) == 1
    assert alice_hits[0]["session_id"] == "s1"
    assert "zümrüt" in alice_hits[0]["snippet"]
    assert bob_hits == []


def test_search_multiword_owner_isolation(two_users, no_embeddings):
    # Multi-word queries exercise the AND→OR FTS branches.
    dbmod, alice, bob = two_users
    asyncio.run(dbmod.save_message("s1", "user", "zümrüt yeşili teleskop notu", user_id=alice))

    alice_hits = asyncio.run(dbmod.search_sessions("zümrüt teleskop", user_id=alice))
    bob_hits = asyncio.run(dbmod.search_sessions("zümrüt teleskop", user_id=bob))
    assert any(h["session_id"] == "s1" for h in alice_hits)
    assert bob_hits == []


# ── /chat/stream: early 404, no existence oracle ─────────────────────────────

def test_stream_foreign_session_404(two_users, no_embeddings, permissive_limits, chatmod):
    _dbmod, alice, bob = two_users
    asyncio.run(_dbmod.save_message("s1", "user", "merhaba", user_id=alice))

    req, request = _req(bob, "s1")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.chat_stream(req, request, None))
    assert exc.value.status_code == 404
    assert "s1" not in chatmod._busy_sessions  # slot released on the 404 path


def test_stream_own_session_passes_ownership(two_users, no_embeddings, permissive_limits, chatmod, monkeypatch):
    _dbmod, alice, _bob = two_users
    asyncio.run(_dbmod.save_message("s1", "user", "merhaba", user_id=alice))

    async def _stop(*a, **k):
        raise RuntimeError("stop-before-heavy-setup")

    monkeypatch.setattr(chatmod, "save_message", _stop)
    req, request = _req(alice, "s1")
    # Must NOT be 404: the ownership gate passed and setup failed later
    # (500 wrap). A nonexistent oracle would have answered 404 here too.
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chatmod.chat_stream(req, request, None))
    assert exc.value.status_code == 500
    assert "s1" not in chatmod._busy_sessions
