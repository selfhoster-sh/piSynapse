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


def test_save_message_returns_true_rowid(iso_db):
    async def _go():
        db = await dbmod.get_db()
        id1 = await dbmod.save_message("sx", "user", "first", user_id="alice")
        id2 = await dbmod.save_message("sx", "user", "second", user_id="alice")
        rows = await (
            await db.execute("SELECT id, content FROM conversations ORDER BY id")
        ).fetchall()
        return id1, id2, rows

    id1, id2, rows = asyncio.run(_go())
    assert (id1, id2) == (rows[0][0], rows[1][0])
    assert [r[1] for r in rows] == ["first", "second"]


def test_update_session_name_guarded_cross_user(iso_db):
    asyncio.run(dbmod.update_session_name("sx", "Alice Title", user_id="alice"))
    asyncio.run(dbmod.update_session_name("sx", "EVIL", user_id="bob"))

    async def _name():
        db = await dbmod.get_db()
        cur = await db.execute("SELECT name FROM sessions WHERE id = ?", ("sx",))
        return (await cur.fetchone())[0]

    assert asyncio.run(_name()) == "Alice Title"


def test_update_session_summary_bumps_last_active(iso_db):
    asyncio.run(dbmod.update_session_summary("sx", "sum", 3, user_id="alice"))

    async def _row():
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT summary, summarized_until, last_active FROM sessions WHERE id = ?",
            ("sx",),
        )
        return await cur.fetchone()

    summary, until, last_active = asyncio.run(_row())
    assert (summary, until) == ("sum", 3)
    assert last_active, "last_active must be set on summary write"


def test_session_maps_are_per_user(iso_db):
    import prompt as promptmod

    # NOTE: alice and bob use different sessions here. Sharing one session_id
    # across users trips UNIQUE(session_id, seq) on insert — a known accepted
    # residual (uuid session ids never collide in practice; the constraint
    # cannot cover user_id without a table rebuild, and these rows are
    # disposable caches). Reads/writes below prove the invisibility rule.
    async def _go():
        await dbmod.save_email_map("sa", [{"id": "m1", "subject": "A"}], "alice")
        await dbmod.save_email_map("sb", [{"id": "m2", "subject": "B"}], "bob")

    asyncio.run(_go())

    async def _read():
        return (
            await promptmod.get_email_context("sa", "alice"),
            await promptmod.get_email_context("sa", "bob"),
            await promptmod.get_email_context("sb", "bob"),
        )

    got_a, got_b_wrong_session, got_b = asyncio.run(_read())
    assert [m["id"] for m in got_a] == ["m1"]
    assert got_b_wrong_session == []
    assert [m["id"] for m in got_b] == ["m2"]

    # clear_history("sb", "bob"): only bob's rows go.
    asyncio.run(dbmod.clear_history("sb", "bob"))
    got_a2, _, got_b2 = asyncio.run(_read())
    assert [m["id"] for m in got_a2] == ["m1"]
    assert got_b2 == []


def test_map_backfill_reassigns_legacy_rows(iso_db):
    async def _legacy():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO sessions (id, user_id, name) VALUES ('sx', 'alice', 'T')"
        )
        await db.execute(
            "INSERT INTO email_session_map (session_id, seq, message_id) "
            "VALUES ('sx', 1, 'legacy-1')"
        )
        await db.commit()

    asyncio.run(_legacy())
    asyncio.run(dbmod.init_db())  # rerun applies the backfill block

    async def _owner():
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT user_id FROM email_session_map WHERE session_id = 'sx'"
        )
        return (await cur.fetchone())[0]

    assert asyncio.run(_owner()) == "alice"


def test_audit_rows_carry_owner(iso_db):
    async def _go():
        await dbmod.log_tool_call("list_notes", {}, True, user_id="alice")
        await dbmod.log_tool_call("list_notes", {}, True, user_id="bob")
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT user_id, COUNT(*) FROM tool_audit_log GROUP BY user_id ORDER BY user_id"
        )
        return await cur.fetchall()

    assert asyncio.run(_go()) == [("alice", 1), ("bob", 1)]
