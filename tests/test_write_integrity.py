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


def _index_names():
    async def _go():
        db = await dbmod.get_db()
        cur = await db.execute("SELECT name FROM sqlite_master WHERE type = 'index'")
        return {r[0] for r in await cur.fetchall()}

    return asyncio.run(_go())


def test_parallel_import_same_key_inserts_once(wdb):
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
        {"role": "user", "content": "bye"},
    ]

    async def _go():
        results = await asyncio.gather(*[
            dbmod.import_messages("sx", msgs, "key-1", user_id="alice")
            for _ in range(4)
        ])
        db = await dbmod.get_db()
        cur = await db.execute("SELECT COUNT(*) FROM conversations")
        total = (await cur.fetchone())[0]
        return results, total

    results, total = asyncio.run(_go())
    assert sorted(results) == [0, 0, 0, 3], results
    assert total == 3, total


def test_legacy_duplicate_imports_deduped_on_init(wdb):
    async def _setup():
        db = await dbmod.get_db()
        await db.execute("DROP INDEX idx_conversations_client_key")
        for _ in range(2):
            await db.execute(
                "INSERT INTO conversations (session_id, role, content, client_key, user_id) "
                "VALUES ('sx', 'user', 'dup', 'legacy-9', 'alice')"
            )
        await db.commit()

    asyncio.run(_setup())
    asyncio.run(dbmod.init_db())

    names = _index_names()
    for want in (
        "idx_conversations_client_key",
        "idx_memories_created",
        "idx_tool_audit_conv",
        "idx_tool_audit_day",
    ):
        assert want in names, f"missing index {want}"

    async def _count():
        db = await dbmod.get_db()
        cur = await db.execute(
            "SELECT COUNT(*) FROM conversations WHERE client_key = 'legacy-9'"
        )
        return (await cur.fetchone())[0]

    assert asyncio.run(_count()) == 1


def test_fts_failure_does_not_eat_message(wdb):
    async def _go():
        db = await dbmod.get_db()
        await db.execute("DROP TABLE conversations_fts")
        await db.commit()
        rowid = await dbmod.save_message("sx", "user", "still here", user_id="alice")
        cur = await db.execute(
            "SELECT content FROM conversations WHERE id = ?", (rowid,)
        )
        row = await cur.fetchone()
        return rowid, row

    rowid, row = asyncio.run(_go())
    assert rowid and row and row[0] == "still here"


def test_legacy_upgrade_applies_all_repairs(wdb):
    """Downgrade a fresh DB to pre-multi-user shape, then boot current code.

    Drops the newest columns/tables, rewinds user_version, plants legacy
    rows (duplicate imports, NULL owners, legacy map rows). After init_db
    everything must be repaired: columns back, dupes deduped, NULLs
    normalized, maps reassigned, index present.
    """

    async def _downgrade():
        db = await dbmod.get_db()
        for tbl in ("email_session_map", "notes_session_map", "tasks_session_map",
                    "calendar_session_map", "tool_audit_log"):
            await db.execute(f"ALTER TABLE {tbl} DROP COLUMN user_id")
        await db.execute("DROP TABLE users")
        await db.execute("DROP TABLE user_settings")
        await db.execute("DROP INDEX IF EXISTS idx_conversations_client_key")
        # Duplicate import pair + NULL owner, as the old code allowed.
        await db.execute(
            "INSERT INTO conversations (session_id, role, content, client_key, user_id) "
            "VALUES ('sx','user','a','k:0','alice'), ('sx','user','a','k:0','alice'),"
            " ('sx','user','NULL-owned',NULL,NULL), ('sx','user','owned',NULL,'alice')"
        )
        await db.execute("INSERT INTO sessions (id, user_id, name) VALUES ('sx', 'alice', 'Old')")
        await db.execute(
            "INSERT INTO email_session_map (session_id, seq, message_id) "
            "VALUES ('sx', 1, 'm1')"
        )
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, success, conversation_id) "
            "VALUES ('list_notes', 1, 4)"
        )
        await db.execute(f"PRAGMA user_version = {len(dbmod.MIGRATIONS) - 5}")
        await db.commit()

    asyncio.run(_downgrade())
    asyncio.run(dbmod.init_db())

    async def _verify():
        db = await dbmod.get_db()
        out = {}
        cur = await db.execute("PRAGMA user_version")
        out["version"] = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM conversations")
        out["conv"] = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT COUNT(*) FROM conversations WHERE user_id IS NULL"
        )
        out["nulls"] = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_conversations_client_key'"
        )
        out["index"] = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT user_id FROM email_session_map WHERE session_id = 'sx'"
        )
        out["map_owner"] = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT user_id FROM tool_audit_log WHERE conversation_id = 4"
        )
        out["audit_owner"] = (await cur.fetchone())[0]
        cur = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('users', 'user_settings')"
        )
        out["tables"] = sorted(r[0] for r in await cur.fetchall())
        return out

    v = asyncio.run(_verify())
    assert v["version"] == len(dbmod.MIGRATIONS)
    assert v["conv"] == 3  # duplicate pair collapsed; NULL-owned + owned kept
    assert v["nulls"] == 0  # NULL owners normalized to default
    assert v["index"] == "idx_conversations_client_key"
    assert v["map_owner"] == "alice"  # session sx owned by alice
    assert v["audit_owner"] == "alice"  # audit inherits its conversation's owner
    assert v["tables"] == ["user_settings", "users"]
