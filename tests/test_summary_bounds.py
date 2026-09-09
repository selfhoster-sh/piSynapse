"""Rolling-summary fold bounds (Faz 4a).

A single fold must stay within the engine's context budget no matter how
large the backlog is: oldest-first, capped message count, per-message
truncation, boundary advancing by exactly what was folded.
"""

import asyncio

import pytest

import db as dbmod


@pytest.fixture
def sum_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "sum.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def _seed(session_id, user_id, n, prefix="m", content_fn=None):
    async def _go():
        db = await dbmod.get_db()
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            content = content_fn(i) if content_fn else f"{prefix}{i}"
            await db.execute(
                "INSERT INTO conversations (session_id, role, content, user_id) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, user_id),
            )
        await db.commit()
        # Mirror save_message: every conversation row gets an FTS row
        # (raw conversation-only inserts trip the external-content FTS quirk
        # on subquery deletes and do not occur in production).
        await db.execute(
            "INSERT INTO conversations_fts (rowid, content, session_id) "
            "SELECT id, content, session_id FROM conversations "
            "WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        await db.commit()

    asyncio.run(_go())


def test_fold_caps_huge_pending_oldest_first(sum_db):
    _seed("sx", "alice", 100)
    rows, new_boundary = asyncio.run(
        dbmod.get_messages_to_summarize("sx", 12, 0, 5, user_id="alice")
    )
    # 100 total, 12 kept raw -> 88 pending; only the oldest 30 fold now.
    assert len(rows) == dbmod.FOLD_MAX_MESSAGES
    assert [r["content"] for r in rows] == [f"m{i}" for i in range(30)]

    async def _id_of(content):
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT id FROM conversations WHERE session_id = 'sx' AND content = ?",
            (content,),
        )
        return (await cur.fetchone())[0]

    assert new_boundary == asyncio.run(_id_of("m29"))


def test_fold_progresses_to_completion_without_gaps(sum_db):
    _seed("sx", "alice", 100)
    seen: list[str] = []
    until = 0
    calls = 0
    while True:
        rows, until = asyncio.run(
            dbmod.get_messages_to_summarize("sx", 12, until, 5, user_id="alice")
        )
        if not rows:
            break
        seen.extend(r["content"] for r in rows)
        calls += 1
        assert calls < 10, "fold must converge in a few turns"
    # Pending was m0..m87 (100 - 12 kept raw), covered exactly once, in order.
    assert seen == [f"m{i}" for i in range(88)]


def test_long_message_truncated(sum_db):
    _seed("sx", "alice", 20, content_fn=lambda i: "x" * 2000 if i == 3 else f"m{i}")
    rows, _ = asyncio.run(
        dbmod.get_messages_to_summarize("sx", 12, 0, 5, user_id="alice")
    )
    long_rows = [r for r in rows if r["content"].startswith("x")]
    assert len(long_rows) == 1
    assert len(long_rows[0]["content"]) == dbmod.FOLD_MAX_CHARS_PER_MESSAGE + 1


def test_empty_span_advances_boundary(sum_db):
    _seed("sx", "alice", 20, content_fn=lambda i: "   ")
    rows, new_boundary = asyncio.run(
        dbmod.get_messages_to_summarize("sx", 12, 0, 5, user_id="alice")
    )
    assert rows == []
    assert new_boundary > 0
    # Second call continues past the empty span instead of retrying it.
    rows2, new_boundary2 = asyncio.run(
        dbmod.get_messages_to_summarize("sx", 12, new_boundary, 5, user_id="alice")
    )
    assert rows2 == []
    assert new_boundary2 >= new_boundary


def _msg_ids(session_id="sx"):
    async def _go():
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT id FROM conversations WHERE session_id = ? ORDER BY id", (session_id,)
        )
        return [r[0] for r in await cur.fetchall()]

    return asyncio.run(_go())


def test_branch_delete_clamps_boundary(sum_db):
    _seed("sx", "alice", 10)
    ids = _msg_ids()
    asyncio.run(dbmod.update_session_summary("sx", "sum", 8, user_id="alice"))
    asyncio.run(dbmod.delete_branch("sx", ids[5], user_id="alice"))
    meta = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta["summary"] == "sum"
    assert meta["summarized_until"] == ids[4]


def test_clear_history_clears_summary(sum_db):
    _seed("sx", "alice", 6)
    asyncio.run(dbmod.update_session_summary("sx", "sum", 4, user_id="alice"))
    asyncio.run(dbmod.clear_history("sx", "alice"))
    meta = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta == {"summary": "", "summarized_until": 0}


def test_delete_cascades_feedback_and_audits(sum_db):
    _seed("sx", "alice", 4)
    ids = _msg_ids()

    async def _seed_links():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO message_feedback (message_id, value) VALUES (?, 'up'), (?, 'down')",
            (ids[0], ids[3]),
        )
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, success, is_summary, conversation_id) "
            "VALUES ('get_weather', 1, 0, ?), ('list_notes', 1, 0, ?)",
            (ids[0], ids[2]),
        )
        await db.commit()

    asyncio.run(_seed_links())
    asyncio.run(dbmod.delete_branch("sx", ids[2], user_id="alice"))

    async def _left():
        db = await dbmod.get_db()
        fb = await (
            await db.execute("SELECT message_id FROM message_feedback")
        ).fetchall()
        au = await (
            await db.execute("SELECT conversation_id FROM tool_audit_log")
        ).fetchall()
        return {r[0] for r in fb}, {r[0] for r in au}

    fb, au = asyncio.run(_left())
    assert fb == {ids[0]}
    assert au == {ids[0]}


def test_retention_repair(sum_db, monkeypatch):
    import config as config_module

    monkeypatch.setattr(config_module, "CONVERSATION_RETENTION_DAYS", 1)
    monkeypatch.setattr(config_module, "MEMORY_RETENTION_DAYS", 0)

    async def _seed_old():
        db = await dbmod.get_db()
        for i in range(6):
            await db.execute(
                "INSERT INTO conversations (session_id, role, content, user_id, timestamp) "
                "VALUES ('sx', 'user', ?, 'alice', datetime('now', '-3 days'))",
                (f"old{i}",),
            )
        for i in range(4):
            await db.execute(
                "INSERT INTO conversations (session_id, role, content, user_id) "
                "VALUES ('sx', 'user', ?, 'alice')",
                (f"new{i}",),
            )
        await db.commit()

    asyncio.run(_seed_old())
    fresh_max = _msg_ids()[-1]
    asyncio.run(dbmod.update_session_summary("sx", "sum", 9999, user_id="alice"))
    removed_conv, _ = asyncio.run(dbmod.cleanup_expired_data())
    assert removed_conv == 6
    meta = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta["summary"] == "sum"
    assert meta["summarized_until"] == fresh_max


def test_conditional_summary_write(sum_db):
    asyncio.run(dbmod.update_session_summary("sx", "a", 10, user_id="alice"))
    stale = asyncio.run(
        dbmod.update_session_summary("sx", "b", 15, user_id="alice", expected_until=0)
    )
    assert stale is False
    fresh = asyncio.run(
        dbmod.update_session_summary("sx", "c", 15, user_id="alice", expected_until=10)
    )
    assert fresh is True
    meta = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta == {"summary": "c", "summarized_until": 15}


def test_concurrent_summary_writes_do_not_regress(sum_db, monkeypatch):
    import config as config_module
    import routers.chat as rc

    monkeypatch.setattr(config_module, "HISTORY_LIMIT", 12)
    monkeypatch.setattr(config_module, "SUMMARY_BATCH_SIZE", 5)
    monkeypatch.setattr(config_module, "SUMMARY_EARLY_TRIGGER", 6)
    _seed("sx", "alice", 20)
    ids = _msg_ids()

    calls = []

    async def fake_summarize(messages, previous):
        await asyncio.sleep(0.05)  # force the two folds to overlap
        calls.append(len(messages))
        return f"sum-{len(messages)}"

    monkeypatch.setattr(rc, "summarize_conversation", fake_summarize)

    async def _go():
        await asyncio.gather(
            rc._update_summary("sx", user_id="alice"),
            rc._update_summary("sx", user_id="alice"),
        )

    asyncio.run(_go())
    # Both folds saw the same 8 pending rows; exactly one write wins.
    assert sorted(calls) == [8, 8]
    meta = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta == {"summary": "sum-8", "summarized_until": ids[7]}

    # A follow-up fold converges instead of refolding or regressing.
    asyncio.run(rc._update_summary("sx", user_id="alice"))
    assert sorted(calls) == [8, 8]
    meta2 = asyncio.run(dbmod.get_session_meta("sx", user_id="alice"))
    assert meta2 == meta
