"""Tests for the retry/regenerate feature: dedup and delete_last_assistant."""

import asyncio

import pytest

import db as dbmod


@pytest.fixture
def retry_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "retry.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


async def _count_messages(session_id: str) -> int:
    db = await dbmod.get_db()
    cur = await db.execute(
        "SELECT COUNT(*) FROM conversations WHERE session_id = ?", (session_id,)
    )
    return (await cur.fetchone())[0]


async def _last_role(session_id: str) -> str | None:
    db = await dbmod.get_db()
    cur = await db.execute(
        "SELECT role FROM conversations WHERE session_id = ? ORDER BY id DESC LIMIT 1",
        (session_id,),
    )
    row = await cur.fetchone()
    return row[0] if row else None


class TestDedup:
    def test_identical_user_message_not_duplicated(self, retry_db):
        """Simulate the real regenerate flow: DELETE last assistant then
        re-send the user message — dedup must prevent a duplicate row."""
        sid = "dedup-test"
        asyncio.run(dbmod.save_message(sid, "user", "hello"))
        asyncio.run(dbmod.save_message(sid, "assistant", "hi there"))
        asyncio.run(dbmod.delete_last_assistant(sid))  # simulate regenerate start
        asyncio.run(dbmod.save_message(sid, "user", "hello"))  # retry dedup
        assert asyncio.run(_count_messages(sid)) == 1  # only the first user msg

    def test_different_user_message_not_deduplicated(self, retry_db):
        """Two DISTINCT user messages must both be stored."""
        sid = "diff-test"
        asyncio.run(dbmod.save_message(sid, "user", "hello"))
        asyncio.run(dbmod.save_message(sid, "user", "world"))
        assert asyncio.run(_count_messages(sid)) == 2

    def test_assistant_message_never_deduplicated(self, retry_db):
        """Assistant messages must always be stored (dedup is user-only)."""
        sid = "asst-test"
        asyncio.run(dbmod.save_message(sid, "assistant", "same"))
        asyncio.run(dbmod.save_message(sid, "assistant", "same"))
        assert asyncio.run(_count_messages(sid)) == 2

    def test_dedup_on_empty_session(self, retry_db):
        """First message in an empty session must never be skipped."""
        asyncio.run(dbmod.save_message("empty", "user", "first"))
        assert asyncio.run(_count_messages("empty")) == 1


class TestDeleteLastAssistant:
    def test_removes_last_assistant(self, retry_db):
        """delete_last_assistant must remove the most recent assistant row."""
        sid = "del-test"
        asyncio.run(dbmod.save_message(sid, "user", "q1"))
        asyncio.run(dbmod.save_message(sid, "assistant", "a1"))
        asyncio.run(dbmod.save_message(sid, "user", "q2"))
        asyncio.run(dbmod.save_message(sid, "assistant", "a2"))
        result = asyncio.run(dbmod.delete_last_assistant(sid))
        assert result is True
        assert asyncio.run(_count_messages(sid)) == 3
        assert asyncio.run(_last_role(sid)) == "user"

    def test_no_assistant_returns_false(self, retry_db):
        """If no assistant message exists, returns False and touches nothing."""
        sid = "no-asst"
        asyncio.run(dbmod.save_message(sid, "user", "solo"))
        result = asyncio.run(dbmod.delete_last_assistant(sid))
        assert result is False
        assert asyncio.run(_count_messages(sid)) == 1
        assert asyncio.run(_last_role(sid)) == "user"

    def test_empty_session_returns_false(self, retry_db):
        """Empty session returns False."""
        result = asyncio.run(dbmod.delete_last_assistant("empty-sid"))
        assert result is False
