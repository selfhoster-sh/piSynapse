"""Write-path integrity under concurrency (Faz 3b).

The shared aiosqlite connection serializes grouped writes through
db._write_lock; these tests prove bursts cannot interleave rows or leave
half-replaced maps behind.
"""

import asyncio

import pytest

import db as dbmod
import embedding


@pytest.fixture
def wdb(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "w.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    # Instant embeddings: save_message must not load the real model here.
    async def _fake_embed(_text):
        return b"\x00" * 16

    monkeypatch.setattr(embedding, "embed_async", _fake_embed)
    yield dbmod
    asyncio.run(dbmod.close_db())


async def _count(sql, params=()):
    db = await dbmod.get_db()
    cur = await db.execute(sql, params)
    return (await cur.fetchone())[0]


def test_concurrent_save_message_bursts_stay_complete(wdb):
    async def _burst(k, n=10):
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            await dbmod.save_message("sx", role, f"w{k}-{i}", user_id="alice")

    async def _go():
        await asyncio.gather(*[_burst(k) for k in range(4)])

    asyncio.run(_go())

    n_conv = asyncio.run(_count("SELECT COUNT(*) FROM conversations"))
    n_fts = asyncio.run(_count("SELECT COUNT(*) FROM conversations_fts"))
    assert n_conv == 40, n_conv
    assert n_fts == n_conv, "every message row must have its FTS row"
    # Each worker's messages are all present exactly once.
    db = asyncio.run(dbmod.get_db())

    async def _contents():
        cur = await db.execute("SELECT content, COUNT(*) FROM conversations GROUP BY content")
        return await cur.fetchall()

    rows = asyncio.run(_contents())
    assert len(rows) == 40
    assert all(c == 1 for _, c in rows)


def test_concurrent_map_replace_is_atomic(wdb):
    a = [{"id": i, "subject": f"a{i}", "from": "a@x", "body": "ba"} for i in range(1, 6)]
    b = [{"id": i, "subject": f"b{i}", "from": "b@x", "body": "bb"} for i in range(1, 4)]

    async def _go():
        await asyncio.gather(
            dbmod.save_email_map("sx", a),
            dbmod.save_email_map("sx", b),
        )
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT subject FROM email_session_map WHERE session_id = ? ORDER BY seq", ("sx",)
        )
        return [r[0] for r in await cur.fetchall()]

    got = asyncio.run(_go())
    # All-or-nothing: exactly one of the two listings, never a mixture.
    assert got == [f"a{i}" for i in range(1, 6)] or got == [f"b{i}" for i in range(1, 4)], got
