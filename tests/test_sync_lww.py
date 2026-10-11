"""Sync items: origin column + true LWW + canonical timestamps (analysis D3/D5).

- D5: the 2026-09-05 sync-compatibility rule (updated_at + deleted + origin)
  was violated — sync_items had no origin. Added to the schema AND as a
  migration for existing databases; the API model takes it optionally so
  older clients keep working.
- D3: the upsert claimed last-write-wins but DO UPDATE was UNCONDITIONAL —
  a delayed old push clobbered newer data. Now strictly-newer-wins
  (WHERE excluded.updated_at > stored), under the process write lock.
- D3: updated_at was free text, so the LWW/since STRING comparisons were
  lexicographic garbage across formats (mixed offsets, missing micros).
  Now normalized to fixed-width canonical UTC on write, on pull filters,
  and via an every-boot repair for legacy stored rows.
"""
import asyncio
import os

import aiosqlite
import pytest

import db as dbmod


@pytest.fixture
def sync_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "sync.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


async def _origin_column_exists():
    db = await dbmod.get_db()
    cur = await db.execute("PRAGMA table_info(sync_items)")
    return any(row[1] == "origin" for row in await cur.fetchall())


def _item(uuid, ts, data="v", deleted=False, origin=""):
    return {"uuid": uuid, "entity_type": "task", "data": {"v": data},
            "updated_at": ts, "deleted": deleted, "origin": origin}


# ── Schema / migration (D5) ───────────────────────────────────────────────────

def test_origin_column_on_fresh_db(sync_db):
    assert asyncio.run(_origin_column_exists())


def test_migration_adds_origin_to_old_db(tmp_path, monkeypatch):
    """A pre-origin database (user_version 22) gains the column via init_db."""
    path = str(tmp_path / "old.db")

    async def build_old():
        con = await aiosqlite.connect(path)
        await con.execute(
            """CREATE TABLE sync_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uuid TEXT NOT NULL,
                user_id TEXT NOT NULL DEFAULT 'default',
                entity_type TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                updated_at TEXT NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, uuid)
            )"""
        )
        await con.execute("PRAGMA user_version = 22")
        await con.commit()
        await con.close()

    asyncio.run(build_old())
    monkeypatch.setattr(dbmod, "DB_PATH", path)
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    assert asyncio.run(_origin_column_exists())

    async def _version():
        db = await dbmod.get_db()
        cur = await db.execute("PRAGMA user_version")
        return (await cur.fetchone())[0]

    assert asyncio.run(_version()) == 23
    asyncio.run(dbmod.close_db())


# ── LWW (D3a) ─────────────────────────────────────────────────────────────────

def test_newer_write_wins(sync_db):
    n1 = asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z", "old")]))
    n2 = asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T11:00:00Z", "new")]))
    assert (n1, n2) == (1, 1)
    items = asyncio.run(dbmod.get_sync_items("u1"))
    assert items[0]["data"]["v"] == "new"


def test_older_write_dropped_and_not_counted(sync_db):
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T11:00:00Z", "new")]))
    n = asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z", "stale")]))
    assert n == 0  # the delayed old push was refused
    items = asyncio.run(dbmod.get_sync_items("u1"))
    assert items[0]["data"]["v"] == "new"


def test_equal_timestamp_dropped(sync_db):
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z", "first")]))
    n = asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z", "second")]))
    assert n == 0
    items = asyncio.run(dbmod.get_sync_items("u1"))
    assert items[0]["data"]["v"] == "first"


def test_tombstone_respects_lww_both_directions(sync_db):
    # Newer tombstone wins over older live data.
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z", "live")]))
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T12:00:00Z", "x", deleted=True)]))
    assert asyncio.run(dbmod.get_sync_items("u1"))[0]["deleted"] is True
    # A delayed OLD live write cannot resurrect it.
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T11:00:00Z", "zombie")]))
    assert asyncio.run(dbmod.get_sync_items("u1"))[0]["deleted"] is True


# ── Timestamp canonicalization (D3b) ─────────────────────────────────────────

def test_offsets_normalized_to_canonical_utc(sync_db):
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T20:00:00+03:00")]))
    items = asyncio.run(dbmod.get_sync_items("u1"))
    assert items[0]["updated_at"] == "2026-10-11T17:00:00.000000Z"


def test_unparseable_timestamp_dropped_fail_closed(sync_db):
    n = asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "yarin sabah")]))
    assert n == 0
    assert asyncio.run(dbmod.get_sync_items("u1")) == []


def test_mixed_formats_compare_chronologically(sync_db):
    # The exact lie the old free-text comparisons told: "…:00Z" vs "…:00.5Z".
    asyncio.run(dbmod.upsert_sync_items("u1", [
        _item("a", "2026-10-11T10:00:00.500000Z", "half-second"),
        _item("b", "2026-10-11T10:00:00Z", "whole-second"),
    ]))
    pulled = asyncio.run(dbmod.get_sync_items("u1", since="2026-10-11T10:00:00Z"))
    assert [i["uuid"] for i in pulled] == ["a"]  # .5s > .0s, not the reverse


def test_since_with_client_offset_normalizes(sync_db):
    asyncio.run(dbmod.upsert_sync_items("u1", [
        _item("a", "2026-10-11T10:00:00Z"),
        _item("b", "2026-10-11T12:00:00Z"),
    ]))
    # Client in +03:00 asking for everything after 13:00 local == 10:00 UTC.
    pulled = asyncio.run(dbmod.get_sync_items("u1", since="2026-10-11T13:00:00+03:00"))
    assert [i["uuid"] for i in pulled] == ["b"]


def test_legacy_stored_rows_normalized_on_boot(sync_db):
    async def seed_legacy():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO sync_items (uuid, user_id, entity_type, data, updated_at, deleted) "
            "VALUES ('legacy', 'u1', 'task', '{}', '2026-10-11 09:00:00', 0)"
        )
        await db.execute(
            "INSERT INTO sync_items (uuid, user_id, entity_type, data, updated_at, deleted) "
            "VALUES ('canon', 'u1', 'task', '{}', '2026-10-11T09:30:00.000000Z', 0)"
        )
        await db.commit()

    asyncio.run(seed_legacy())
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())  # every-boot repair runs
    items = asyncio.run(dbmod.get_sync_items("u1"))
    by_uuid = {i["uuid"]: i["updated_at"] for i in items}
    assert by_uuid["legacy"] == "2026-10-11T09:00:00.000000Z"  # canonicalized
    assert by_uuid["canon"] == "2026-10-11T09:30:00.000000Z"  # untouched
    # And now comparisons across the legacy row are valid:
    pulled = asyncio.run(dbmod.get_sync_items("u1", since="2026-10-11T09:00:00.000000Z"))
    assert {i["uuid"] for i in pulled} == {"canon"}


# ── Origin + lock ─────────────────────────────────────────────────────────────

def test_origin_round_trip(sync_db):
    asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z", origin="phone-1")]))
    items = asyncio.run(dbmod.get_sync_items("u1"))
    assert items[0]["origin"] == "phone-1"
    # A phone can skip its own echoes on pull.
    assert [i for i in items if i["origin"] != "phone-1"] == []


def test_upsert_holds_write_lock(sync_db, monkeypatch):
    import contextlib

    acquisitions = []

    @contextlib.asynccontextmanager
    async def spy_lock():
        acquisitions.append(1)
        yield

    monkeypatch.setattr(dbmod, "_write_lock", spy_lock)
    n = asyncio.run(dbmod.upsert_sync_items("u1", [_item("a", "2026-10-11T10:00:00Z")]))
    assert n == 1
    assert acquisitions, "upsert_sync_items must serialize via _write_lock"
