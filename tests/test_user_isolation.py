"""Cross-user isolation: same session_id under two user_ids must not leak.

Faz 1 acceptance: identical session_id + different user_id -> no shared
summary rows, no shared retrieval candidates, no shared FTS hits, no
cross-user summary clobbering.
"""

import asyncio

import numpy as np
import pytest

import db as dbmod
import embedding
from db import (
    clear_history,
    get_messages_to_summarize,
    get_session_meta,
    save_message,
    search_sessions,
    update_session_summary,
)
from retrieval import _fetch_candidates


@pytest.fixture
def iso_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "iso.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def _vec(*vals) -> bytes:
    return np.array(vals, dtype="float32").tobytes()


def _seed_conversation(session_id, user_id, texts, blob=None):
    async def _go():
        db = await dbmod.get_db()
        for i, t in enumerate(texts):
            role = "user" if i % 2 == 0 else "assistant"
            await db.execute(
                "INSERT INTO conversations (session_id, role, content, user_id, embedding) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, role, t, user_id, blob),
            )
        await db.commit()
        # Mirror save_message: every conversation row gets an FTS row.
        # NOTE: never read bare `rowid` from the external-content FTS table
        # inside a write (it corrupts the index); each test uses a fresh DB
        # so no dedup guard is needed here.
        await db.execute(
            "INSERT INTO conversations_fts (rowid, content, session_id) "
            "SELECT id, content, session_id FROM conversations "
            "WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await db.commit()

    asyncio.run(_go())


def test_summarize_boundary_is_per_user(iso_db):
    _seed_conversation("sx", "alice", [f"a{i}" for i in range(8)])
    _seed_conversation("sx", "bob", [f"b{i}" for i in range(8)])
    rows_a, _ = asyncio.run(
        dbmod.get_messages_to_summarize("sx", 4, 0, 2, user_id="alice")
    )
    rows_b, _ = asyncio.run(
        dbmod.get_messages_to_summarize("sx", 4, 0, 2, user_id="bob")
    )
    assert rows_a and all(r["content"].startswith("a") for r in rows_a)
    assert rows_b and all(r["content"].startswith("b") for r in rows_b)


def test_update_session_summary_does_not_clobber_other_user(iso_db):
    asyncio.run(dbmod.update_session_summary("sx", "A-sum", 9, user_id="alice"))
    # bob collides on the same session_id: his write must not touch alice's row
    asyncio.run(dbmod.update_session_summary("sx", "EVIL", 99, user_id="bob"))
    meta_a = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta_a == {"summary": "A-sum", "summarized_until": 9}


def test_save_message_session_touch_preserves_other_user_summary(iso_db):
    asyncio.run(dbmod.update_session_summary("sx", "A-sum", 4, user_id="alice"))
    asyncio.run(
        dbmod.save_message("sx", "user", "hello", user_id="bob")
    )
    meta_a = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta_a["summary"] == "A-sum"
    assert meta_a["summarized_until"] == 4


def test_retrieval_fetch_is_per_user(iso_db):
    _seed_conversation("sx", "alice", ["a0", "a1", "a2"])
    _seed_conversation("sx", "bob", ["b0", "b1"])
    got = asyncio.run(_fetch_candidates("sx", 1, "alice"))
    assert got
    assert all("a" in (m["content"] or "") for m in got)
    assert not any((m["content"] or "").startswith("b") for m in got)


def test_clear_history_fts_is_per_user(iso_db):
    _seed_conversation("sx", "alice", ["alice secret recipe"])
    _seed_conversation("sx", "bob", ["bob secret recipe"])
    asyncio.run(dbmod.clear_history("sx", "alice"))

    async def _left():
        db = await dbmod.get_db()
        rows = await (
            await db.execute("SELECT content, user_id FROM conversations")
        ).fetchall()
        # MATCH probes the FTS index itself (bare rowid/content SELECTs on an
        # external-content table reflect the content table, not the index).
        bob_hit = await (
            await db.execute(
                "SELECT content FROM conversations_fts "
                "WHERE conversations_fts MATCH 'bob'"
            )
        ).fetchall()
        alice_hit = await (
            await db.execute(
                "SELECT content FROM conversations_fts "
                "WHERE conversations_fts MATCH 'alice'"
            )
        ).fetchall()
        return rows, bob_hit, alice_hit

    rows, bob_hit, alice_hit = asyncio.run(_left())
    assert rows and all(u == "bob" for _, u in rows), "bob's rows must survive"
    assert bob_hit, "bob's FTS index entry must survive"
    assert not alice_hit, "alice's FTS index entry must be gone"


def test_search_sessions_semantic_is_per_user(iso_db, monkeypatch):
    # Both users talk about the same topic in different sessions; the query
    # embedding is close to both. Alice must never see bob's session.
    _seed_conversation("sa", "alice", ["mavi kapi kolu tamir"], blob=_vec(1, 0))
    _seed_conversation("sb", "bob", ["mavi kapi kolu boya"], blob=_vec(0.9, 0.1))

    async def fake_embed(_text):
        return _vec(1, 0)

    monkeypatch.setattr(embedding, "embed_async", fake_embed)
    results = asyncio.run(
        dbmod.search_sessions("mavi kapi kolu", limit=10, user_id="alice")
    )
    sids = {r["session_id"] for r in results}
    assert "sa" in sids
    assert "sb" not in sids
