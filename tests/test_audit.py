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
    assert json.loads(params) == {"to": "[REDACTED]", "cc": "[REDACTED]"}

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
    assert stored["to"] == "[REDACTED]"
    assert stored["subject"] == "[REDACTED]"
    assert stored["cc"] == "[REDACTED]"


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
    assert n == 2

    rows = asyncio.run(_fetch_all(
        "SELECT is_summary, day, total_calls, success_count, error_count, tool_breakdown "
        "FROM tool_audit_log"
    ))

    assert len(rows) == 2
    # Check both summary days
    summaries = [r for r in rows if r[0] == 1]
    assert len(summaries) == 2
    days = {s[1] for s in summaries}
    assert days == {"2026-07-05", "2026-08-15"}
    # Check 2026-07-05 summary
    s1 = next(s for s in summaries if s[1] == "2026-07-05")
    assert s1[2] == 4  # total_calls
    assert s1[3] == 3  # success_count
    assert s1[4] == 1  # error_count
    breakdown = json.loads(s1[5])
    assert breakdown["get_datetime"] == 3
    assert breakdown["send_email"] == 1

    # Check 2026-08-15 summary
    s2 = next(s for s in summaries if s[1] == "2026-08-15")
    assert s2[2] == 1  # total_calls
    assert s2[3] == 1  # success_count
    assert s2[4] == 0  # error_count
    breakdown2 = json.loads(s2[5])
    assert breakdown2["get_datetime"] == 1

    # No detail rows should remain for rolled-up days
    for day in ["2026-07-05", "2026-08-15"]:
        remaining_detail = asyncio.run(_fetch_all(
            "SELECT COUNT(*) FROM tool_audit_log WHERE is_summary = 0 AND day = ?",
            (day,),
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
    from datetime import datetime, timedelta
    # Relative dates: hardcoded ones age past the threshold and turn the
    # test into a time bomb (the 2026-08-10 row detonated on 2026-08-24).
    old_day = (datetime.now() - timedelta(days=26)).strftime("%Y-%m-%d %H:%M:%S")
    recent_day = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")

    async def seed():
        db = await dbmod.get_db()
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("get_datetime", "{}", 1, old_day),
        )
        await db.execute(
            "INSERT INTO tool_audit_log (tool_name, params, success, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("send_email", "{}", 1, recent_day),
        )
        await db.commit()

    asyncio.run(seed())

    assert asyncio.run(dbmod.rollup_tool_audit()) == 1

    summary_days = asyncio.run(_fetch_all(
        "SELECT day FROM tool_audit_log WHERE is_summary = 1"
    ))
    assert [r[0] for r in summary_days] == [old_day[:10]]

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


# -- Correction endpoint validation tests --

import pytest
from tools.definitions import TOOL_NAMES
from fastapi import HTTPException


async def _create_audit_entry():
    """Helper to create an audit log entry and return its ID."""
    db = await dbmod.get_db()
    await db.execute(
        "INSERT INTO tool_audit_log (tool_name, params, success, duration_ms, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("get_datetime", "{}", 1, 10.0, "2026-08-28 10:00:00"),
    )
    await db.commit()
    rows = await _fetch_all("SELECT id FROM tool_audit_log WHERE tool_name = 'get_datetime'")
    return rows[0][0]


def _validate_tool_name(expected_tool: str):
    """Validation logic extracted from the endpoint for unit testing."""
    if expected_tool not in TOOL_NAMES:
        valid_tools = ", ".join(sorted(TOOL_NAMES))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid expected_tool: '{expected_tool}'. Valid tools: {valid_tools}",
        )


def test_tool_correction_valid_tool(audit_db):
    """Valid tool name should be accepted."""
    audit_id = asyncio.run(_create_audit_entry())
    from db import set_tool_correction
    result = asyncio.run(set_tool_correction(audit_id, "create_calendar_event"))
    assert result is True

    # Verify the correction was saved
    rows = asyncio.run(_fetch_all(
        "SELECT expected_tool, corrected_at FROM tool_audit_log WHERE id = ?",
        (audit_id,),
    ))
    assert rows[0][0] == "create_calendar_event"
    assert rows[0][1] is not None


def test_tool_correction_invalid_tool(audit_db):
    """Invalid tool name should raise HTTPException with descriptive error."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_tool_name("not_a_real_tool")
    assert exc_info.value.status_code == 400
    assert "Invalid expected_tool" in exc_info.value.detail
    assert "not_a_real_tool" in exc_info.value.detail
    # Should list valid tools
    assert "create_calendar_event" in exc_info.value.detail
    assert "get_datetime" in exc_info.value.detail


def test_tool_correction_empty_tool(audit_db):
    """Empty string as tool name should raise HTTPException."""
    with pytest.raises(HTTPException) as exc_info:
        _validate_tool_name("")
    assert exc_info.value.status_code == 400
    assert "Invalid expected_tool" in exc_info.value.detail


def test_tool_names_single_source_of_truth():
    """TOOL_NAMES should match the tool definitions and be non-empty."""
    assert len(TOOL_NAMES) > 0
    # Check some expected tools are present
    expected = {"get_datetime", "create_calendar_event", "list_calendar_events", "send_email", "save_memory"}
    assert expected.issubset(TOOL_NAMES)
    # Ensure no duplicates (set property)
    from tools.definitions import TOOLS
    assert len(TOOL_NAMES) == len({t["function"]["name"] for t in TOOLS})
