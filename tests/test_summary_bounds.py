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
