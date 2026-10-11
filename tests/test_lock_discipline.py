"""Lock-discipline invariant (analysis D4).

Every `_commit_with_retry` on the shared connection must run while the
process-wide `_write_lock` is held — otherwise its `db.commit()` flushes
whatever transaction is open, including another coroutine's partially-
assembled one, so a later rollback on that other path finds its work
already committed (torn state).

This wraps the real commit to assert the lock is held, then exercises the
write paths that were audited in D4. A future edit that unwraps one of
them trips this guard.
"""
import asyncio

import pytest

import db as dbmod


@pytest.fixture
def idb(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "inv.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def violations(monkeypatch):
    """Wrap _commit_with_retry: record any call made without the lock."""
    real = dbmod._commit_with_retry
    seen = {"commits": 0, "unlocked": []}

    async def guarded(db):
        seen["commits"] += 1
        try:
            locked = dbmod._write_lock().locked()
        except Exception:
            locked = True
        if not locked:
            seen["unlocked"].append(True)
        return await real(db)

    monkeypatch.setattr(dbmod, "_commit_with_retry", guarded)
    return seen


def test_audited_write_paths_hold_the_lock(idb, violations, monkeypatch):
    async def no_embed(*a, **k):
        return None

    import embedding

    monkeypatch.setattr(embedding, "embed_async", no_embed)

    async def exercise():
        # Memories
        await dbmod.save_memory("ilk not", user_id="u1")
        mems = await dbmod.get_memories(user_id="u1")
        await dbmod.delete_memory("u1", mems[0]["id"])
        # Sessions
        await dbmod.update_session_name("s1", "Yeni", user_id="u1")
        await dbmod.update_session_summary("s1", "ozet", 0, user_id="u1")
        # Audit-side leaf writers
        await dbmod.log_intent_audit("msj", "notes", 0.5, 0.1, "test")
        await dbmod.record_pattern_decision("sig1", "notes", "approved", "patron")
        await dbmod.purge_intent_audit(days=0)
        # Confirm/correct need a row
        await dbmod.log_tool_call("list_notes", {}, True, user_id="u1")
        db = await dbmod.get_db()
        cur = await db.execute("SELECT id FROM tool_audit_log ORDER BY id DESC LIMIT 1")
        aid = (await cur.fetchone())[0]
        await dbmod.set_tool_correction(aid, "list_notes", user_id="u1")
        await dbmod.set_tool_confirmation(aid, user_id="u1")
        # Sync upsert (wrapped in this session)
        await dbmod.upsert_sync_items("u1", [{
            "uuid": "x", "entity_type": "task", "data": {},
            "updated_at": "2026-10-11T10:00:00Z", "deleted": False, "origin": "test",
        }])

    asyncio.run(exercise())
    assert violations["commits"] > 0, "no commits were exercised — test is not proving anything"
    assert violations["unlocked"] == [], (
        f"{len(violations['unlocked'])} commit(s) ran WITHOUT the write lock (D4 regression)"
    )
