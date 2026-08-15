"""Tests for the tool audit log: row insertion, retention rollup, never-raises."""

import asyncio
import json
import os

import pytest

import db as dbmod


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "audit.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


async def _fetch_all(sql, params=()):
    db = await dbmod.get_db()
    cur = await db.execute(sql, params)
    return await cur.fetchall()


def test_log_tool_call_writes_row(audit_db):
    asyncio.run(
        dbmod.log_tool_call("send_email", {"to": "a@b.c", "cc": None}, True, duration_ms=120.5)
    )
    asyncio.run(
        dbmod.log_tool_call("delete_task", {"id": 3}, False, duration_ms=50.0, error="ERROR: task not found")
    )

    rows = asyncio.run(_fetch_all(
        "SELECT tool_name, params, success, duration_ms, error, is_summary, day "
        "FROM tool_audit_log ORDER BY id"
    ))

    assert len(rows) == 2
    name, params, success, dur, err, is_summary, day = rows[0]
    assert name == "send_email"
    assert success == 1
    assert dur == pytest.approx(120.5)
    assert err is None
    assert json.loads(params) == {"to": "a@b.c", "cc": None}

    name, params, success, dur, err, is_summary, day = rows[1]
    assert name == "delete_task"
    assert success == 0
    assert err.startswith("ERROR")
    assert is_summary == 0
    assert day is None


def test_log_tool_call_redacts_sensitive_params(audit_db):
    asyncio.run(
        dbmod.log_tool_call(
            "send_email",
            {"to": "a@b.c", "subject": "hello", "body": "secret email text", "cc": None},
            True,
        )
    )
    rows = asyncio.run(_fetch_all("SELECT params FROM tool_audit_log"))
    stored = json.loads(rows[0][0])
    assert stored["body"] == "[REDACTED]"
    assert stored["to"] == "a@b.c"
    assert stored["subject"] == "hello"
    assert stored["cc"] is None


def test_log_tool_call_redacts_nested_secret_keys(audit_db):
    asyncio.run(
        dbmod.log_tool_call(
            "create_note",
            {"title": "t", "content": "note body", "meta": {"api_key": "topsecret", "ok": 1}},
            True,
        )
    )
    rows = asyncio.run(_fetch_all("SELECT params FROM tool_audit_log"))
    stored = json.loads(rows[0][0])
    assert stored["content"] == "[REDACTED]"
    assert stored["meta"]["api_key"] == "[REDACTED]"
    assert stored["meta"]["ok"] == 1


def test_log_tool_call_caps_oversized_params(audit_db):
    asyncio.run(dbmod.log_tool_call("x", {"big": "y" * 5000}, True))
    stored = asyncio.run(_fetch_all("SELECT params FROM tool_audit_log"))[0][0]
    assert stored.endswith(" ...(truncated)")
    assert len(stored) <= dbmod._AUDIT_PARAMS_MAX_CHARS + len(" ...(truncated)")


def test_rollup_compresses_old_rows_into_daily_summary(audit_db):
    async def seed():
        db = await dbmod.get_db()
        for _ in range(3):
            await db.execute(
                "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                ("get_datetime", "{}", 1, 10.0, "2026-07-05 12:00:00"),
            )
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, error, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("send_email", "{}", 0, 5.0, "ERROR", "2026-07-05 13:00:00"),
        )
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("get_datetime", "{}", 1, 8.0, "2026-08-15 09:00:00"),
        )
        await db.commit()

    asyncio.run(seed())

    n = asyncio.run(dbmod.rollup_tool_audit())
    assert n == 1

    rows = asyncio.run(_fetch_all(
        "SELECT is_summary, day, total_calls, success_count, error_count, tool_breakdown "
        "FROM tool_audit_log"
    ))

    assert len(rows) == 2
    summary = next(r for r in rows if r[0] == 1)
    assert summary[1] == "2026-07-05"
    assert summary[2] == 4
    assert summary[3] == 3
    assert summary[4] == 1
    breakdown = json.loads(summary[5])
    assert breakdown["get_datetime"] == 3
    assert breakdown["send_email"] == 1

    detail = next(r for r in rows if r[0] == 0)
    assert detail[1] is None  # day is only set on summary rows
    assert detail[2] is None  # aggregate columns are only set on summary rows

    remaining_detail = asyncio.run(_fetch_all(
        "SELECT COUNT(*) FROM tool_audit_log WHERE is_summary = 0 AND day = '2026-07-05'"
    ))
    assert remaining_detail[0][0] == 0


def test_rollup_idempotent(audit_db):
    async def seed():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, created_at) VALUES (?, ?, ?, ?)",
            ("get_datetime", "{}", 1, "2026-07-01 10:00:00"),
        )
        await db.commit()

    asyncio.run(seed())
    assert asyncio.run(dbmod.rollup_tool_audit()) == 1
    assert asyncio.run(dbmod.rollup_tool_audit()) == 0
    rows = asyncio.run(_fetch_all("SELECT is_summary FROM tool_audit_log"))
    assert len(rows) == 1
    assert rows[0][0] == 1


def test_rollup_retention_default_is_14_days(audit_db):
    """Default retention is now 14 days: a 26-day-old row is compressed,
    a 5-day-old row is kept. (Under the old 30-day default the 26-day-old
    row would have survived, so this distinguishes the policy.)
    """

    async def seed():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("get_datetime", "{}", 1, "2026-07-20 10:00:00"),
        )
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("send_email", "{}", 1, "2026-08-10 10:00:00"),
        )
        await db.commit()

    asyncio.run(seed())

    assert asyncio.run(dbmod.rollup_tool_audit()) == 1

    summary_days = asyncio.run(_fetch_all(
        "SELECT day FROM tool_audit_log WHERE is_summary = 1"
    ))
    assert [r[0] for r in summary_days] == ["2026-07-20"]

    remaining_details = asyncio.run(_fetch_all(
        "SELECT day FROM tool_audit_log WHERE is_summary = 0"
    ))
    assert [r[0] for r in remaining_details] == [None]
    assert len(remaining_details) == 1
    detail = asyncio.run(_fetch_all(
        "SELECT tool_name FROM tool_audit_log WHERE is_summary = 0"
    ))
    assert detail[0][0] == "send_email"


def test_log_tool_call_never_raises_when_db_down(audit_db, monkeypatch):
    async def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(dbmod, "get_db", boom)

    asyncio.run(dbmod.log_tool_call("send_email", {}, True, duration_ms=1.0))
    asyncio.run(dbmod.rollup_tool_audit())


# -- Periodic rollup loop (timer logic, mocked time) --

def test_periodic_rollup_loop_ticks_after_interval_and_propagates_cancel(monkeypatch):
    audited = []

    async def fake_audit():
        audited.append(1)

    monkeypatch.setattr(dbmod, "rollup_tool_audit", fake_audit)
    slept = []

    async def fake_sleep(secs):
        slept.append(secs)
        if len(slept) == 2:
            raise asyncio.CancelledError  # stop after the second tick

    async def go():
        await dbmod.periodic_rollup_loop(interval=86400, sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert slept == [86400, 86400]  # waited a full day per tick
    assert audited == [1]           # rollup ran once after the first interval tick


def test_periodic_rollup_loop_retries_after_error(monkeypatch):
    attempts = []

    async def failing_audit():
        attempts.append(1)
        raise RuntimeError("db locked")

    monkeypatch.setattr(dbmod, "rollup_tool_audit", failing_audit)
    slept = []

    async def fake_sleep(secs):
        slept.append(secs)
        if len(slept) == 3:
            raise asyncio.CancelledError  # stop after two full cycles

    async def go():
        await dbmod.periodic_rollup_loop(interval=3600, sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert attempts == [1, 1]  # error logged, retried on the next cycle
    assert slept == [3600, 3600, 3600]


def test_periodic_rollup_loop_propagates_cancel_during_audit(monkeypatch):
    async def cancelled_audit():
        raise asyncio.CancelledError

    monkeypatch.setattr(dbmod, "rollup_tool_audit", cancelled_audit)

    async def fake_sleep(secs):
        return  # let the loop reach the audit step

    async def go():
        await dbmod.periodic_rollup_loop(interval=1, sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())


# -- DB file permissions (owner-only, 0o600) --

def test_db_files_are_600_after_init(audit_db):
    """init_db() must leave the DB and its WAL sidecars owner-only."""
    import stat

    paths = [os.path.abspath(p) for p in (dbmod.DB_PATH, dbmod.DB_PATH + "-wal", dbmod.DB_PATH + "-shm")]
    assert any(os.path.exists(p) for p in paths)
    for p in paths:
        if os.path.exists(p):
            assert stat.S_IMODE(os.stat(p).st_mode) == 0o600, f"{p} is not 0o600"


def test_secure_db_files_fixes_permissive_db(audit_db):
    """_secure_db_files() repairs a pre-existing world-readable DB."""
    import stat

    db = os.path.abspath(dbmod.DB_PATH)
    os.chmod(db, 0o644)
    asyncio.run(dbmod._secure_db_files())
    assert stat.S_IMODE(os.stat(db).st_mode) == 0o600
