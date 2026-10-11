"""search_memories access-stats write: lock + conditional commit (analysis D2).

The access-stat UPDATE ran on the shared connection WITHOUT _write_lock,
followed by an UNCONDITIONAL _commit_with_retry(db). On a single shared
connection that commit flushes whatever transaction is open — including
another coroutine's partially-assembled one — so a later rollback on that
other path would find its work already committed (torn state).

Fix: the write (and its commit) run under _write_lock, and the commit
happens ONLY when this function actually wrote (a no-hit search has
nothing of its own to flush).
"""
import asyncio
import contextlib

import numpy as np
import pytest

import db as dbmod


def _vec(*vals) -> bytes:
    return np.array(vals, dtype="float32").tobytes()


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "mem.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


@pytest.fixture
def lock_spy(monkeypatch):
    acquisitions = []

    @contextlib.asynccontextmanager
    async def spy():
        acquisitions.append(1)
        yield

    monkeypatch.setattr(dbmod, "_write_lock", spy)
    return acquisitions


async def _seed_memory(content: str, embedding: bytes):
    db = await dbmod.get_db()
    cur = await db.execute(
        "INSERT INTO memories (user_id, content, embedding) VALUES ('u1', ?, ?)",
        (content, embedding),
    )
    await db.commit()
    return cur.lastrowid


async def _access_count(mem_id: int) -> int:
    db = await dbmod.get_db()
    cur = await db.execute("SELECT access_count FROM memories WHERE id = ?", (mem_id,))
    return (await cur.fetchone())[0]


def test_hit_writes_under_lock_and_persists(mem_db, lock_spy):
    mid = asyncio.run(_seed_memory("kirmizi bisiklet", _vec(1.0, 0.0)))
    result = asyncio.run(dbmod.search_memories(
        "bisiklet", user_id="u1", query_embedding=_vec(1.0, 0.0),
    ))
    assert [m["id"] for m in result] == [mid]
    assert lock_spy, "the access-stats write must hold _write_lock"
    assert asyncio.run(_access_count(mid)) == 1  # committed


def test_no_hit_takes_no_lock(mem_db, lock_spy):
    asyncio.run(_seed_memory("kirmizi bisiklet", _vec(1.0, 0.0)))
    result = asyncio.run(dbmod.search_memories(
        "alakasiz", user_id="u1", query_embedding=_vec(-1.0, 0.0),  # orthogonal-ish, < 0.35
    ))
    assert result == []
    assert lock_spy == [], "a no-hit search must not take the write lock or commit"
