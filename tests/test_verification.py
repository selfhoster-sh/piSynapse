"""Tests for ID-based backend verification (tool_verification.py).

Covers the three create tools in VERIFY_SCOPE (create_task,
create_calendar_event, save_memory):
- success/failure mapping to the five verification_status values
- duplicate summary/content DISCRIMINATION: verification must be driven by
  the structured entity_id (UID/rowid), NOT by matching the human-readable
  summary/content — two identical creates must verify independently.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import tool_verification
from tool_verification import _verify


class TestScopeAndFailure:
    async def test_non_scope_tool_is_not_verified(self):
        assert await _verify("list_tasks", {}, "OK", True, None) is None
        assert await _verify("send_email", {}, "OK", True, None) is None

    async def test_failed_tool_call_is_not_verified(self):
        assert await _verify("create_task", {}, "ERROR: failed", False, "uid-x") is None
        assert await _verify("save_memory", {}, "ERROR: failed", False, 3) is None

    async def test_failure_without_entity_id_stays_none(self):
        assert await _verify("create_calendar_event", {}, "ERROR: failed", False, None) is None


class TestCreateTask:
    async def test_verified_by_uid(self):
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("", [{"uid": "t1", "summary": "Buy milk"}]))):
            status = await _verify("create_task", {"summary": "Buy milk"}, "OK Task created.", True, "t1")
        assert status == "verified"

    async def test_uid_miss_reports_failed(self):
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("", [{"uid": "OTHER", "summary": "x"}]))):
            status = await _verify("create_task", {"summary": "Buy milk"}, "OK Task created.", True, "t1")
        assert status == "verification_failed"

    async def test_duplicate_summary_discriminates_by_uid(self):
        # Two creates with the IDENTICAL summary must verify independently:
        # A's uid exists, B's does not. Summary-based matching would wrongly
        # mark both verified — ID-based verification must tell them apart.
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("", [{"uid": "A", "summary": "Meet"}]))):
            status_a = await _verify("create_task", {"summary": "Meet"}, "OK", True, "A")
            status_b = await _verify("create_task", {"summary": "Meet"}, "OK", True, "B")
        assert status_a == "verified"
        assert status_b == "verification_failed"

    async def test_fallback_content_match_when_uid_missing(self):
        with patch("nextcloud_tasks.search_tasks", new=AsyncMock(return_value=("", [{"uid": "t1", "summary": "Buy milk"}]))):
            status = await _verify("create_task", {"summary": "Buy milk"}, "OK", True, None)
        assert status == "verified_by_fallback"

    async def test_fallback_miss_is_unverified(self):
        with patch("nextcloud_tasks.search_tasks", new=AsyncMock(return_value=("Nothing found.", []))):
            status = await _verify("create_task", {"summary": "Ghost task"}, "OK", True, None)
        assert status == "unverified"

    async def test_fallback_skipped_when_uid_present_but_missing(self):
        # Even if the summary would match, missing UID must NOT fall back.
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("", [{"uid": "A", "summary": "Meet"}]))), \
             patch("nextcloud_tasks.search_tasks", new=AsyncMock(return_value=("", [{"uid": "A", "summary": "Meet"}]))):
            status = await _verify("create_task", {"summary": "Meet"}, "OK", True, "MISSING")
        assert status == "verification_failed"


class TestCreateCalendarEvent:
    async def test_verified_by_uid(self):
        with patch("calendar_ops.list_events", return_value=("", [{"uid": "ev-1", "summary": "Dentist"}])):
            status = await _verify("create_calendar_event", {"summary": "Dentist", "start_time": "2026-09-01T10:00:00"}, "OK", True, "ev-1")
        assert status == "verified"

    async def test_uid_miss_reports_failed(self):
        with patch("calendar_ops.list_events", return_value=("", [{"uid": "OTHER", "summary": "Dentist"}])):
            status = await _verify("create_calendar_event", {"summary": "Dentist", "start_time": "2026-09-01T10:00:00"}, "OK", True, "ev-1")
        assert status == "verification_failed"

    async def test_duplicate_summary_discriminates_by_uid(self):
        with patch("calendar_ops.list_events", return_value=("", [{"uid": "A", "summary": "Meet"}])):
            status_a = await _verify("create_calendar_event", {"summary": "Meet", "start_time": "2026-09-01T10:00:00"}, "OK", True, "A")
            status_b = await _verify("create_calendar_event", {"summary": "Meet", "start_time": "2026-09-01T10:00:00"}, "OK", True, "B")
        assert status_a == "verified"
        assert status_b == "verification_failed"

    async def test_fallback_summary_match_when_uid_missing(self):
        with patch("calendar_ops.list_events", return_value=("", [{"uid": "ev-1", "summary": "Dentist"}])):
            status = await _verify("create_calendar_event", {"summary": "Dentist", "start_time": "2026-09-01T10:00:00"}, "OK", True, None)
        assert status == "verified_by_fallback"

    async def test_fallback_miss_is_unverified(self):
        with patch("calendar_ops.list_events", return_value=("No events.", [])):
            status = await _verify("create_calendar_event", {"summary": "Dentist", "start_time": "2026-09-01T10:00:00"}, "OK", True, None)
        assert status == "unverified"


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    import db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "verify.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


class TestSaveMemory:
    async def _seed(self, mem_db, content, mem_id=7):
        db = await mem_db.get_db()
        await db.execute(
            "INSERT INTO memories (id, user_id, content, category, importance) VALUES (?, ?, ?, ?, ?)",
            (mem_id, "default", content, "general", 5),
        )
        await db.commit()

    async def test_verified_by_rowid(self, mem_db):
        await self._seed(mem_db, "Kullanıcı Python sever")
        status = await _verify("save_memory", {"content": "Kullanıcı Python sever"}, "Memory saved.", True, 7)
        assert status == "verified"

    async def test_rowid_miss_reports_failed(self, mem_db):
        await self._seed(mem_db, "Kullanıcı Python sever")
        status = await _verify("save_memory", {"content": "Kullanıcı Python sever"}, "Memory saved.", True, 999)
        assert status == "verification_failed"

    async def test_duplicate_content_discriminates_by_rowid(self, mem_db):
        # Same content saved twice: the second time returns the EXISTING
        # memory's rowid (dedupe). ID-based check must verify each rowid
        # independently of the shared content.
        await self._seed(mem_db, "Kahveyi şekersiz sever")
        await self._seed(mem_db, "Kahveyi şekersiz sever", mem_id=8)
        status_a = await _verify("save_memory", {"content": "Kahveyi şekersiz sever"}, "Memory saved.", True, 7)
        status_b = await _verify("save_memory", {"content": "Kahveyi şekersiz sever"}, "Memory saved.", True, 8)
        status_c = await _verify("save_memory", {"content": "Kahveyi şekersiz sever"}, "Memory updated (similar content exists).", True, 77)
        assert status_a == "verified"
        assert status_b == "verified"
        assert status_c == "verification_failed"

    async def test_fallback_content_match_when_rowid_missing(self, mem_db):
        await self._seed(mem_db, "Kullanıcı Python sever")
        status = await _verify("save_memory", {"content": "Kullanıcı Python sever"}, "Memory saved.", True, None)
        assert status == "verified_by_fallback"

    async def test_fallback_miss_is_unverified(self, mem_db):
        status = await _verify("save_memory", {"content": "Var olmayan içerik"}, "Memory saved.", True, None)
        assert status == "unverified"


def test_run_verification_passes_status_to_audit(monkeypatch):
    import tool_verification as tv

    captured = {}

    async def fake_log(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)

    monkeypatch.setattr(tv, "log_tool_call", fake_log)
    with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("", [{"uid": "t1", "summary": "Buy milk"}]))):
        asyncio.run(
            tv.run_verification(
                "create_task", {"summary": "Buy milk"}, "OK Task created.", True,
                entity_id="t1", duration_ms=5.0,
            )
        )
    assert captured.get("verification_status") == "verified"
    assert captured["args"][:3] == ("create_task", {"summary": "Buy milk"}, True)


def test_run_verification_never_raises(monkeypatch):
    import tool_verification as tv

    async def boom_log(**kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(tv, "log_tool_call", boom_log)
    # Even with log_tool_call exploding, run_verification must not raise.
    asyncio.run(
        tv.run_verification("create_task", {"summary": "X"}, "OK", True, entity_id="t1")
    )


def test_run_verification_backend_error_swallowed(monkeypatch):
    import tool_verification as tv

    captured = {}

    async def fake_log(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(tv, "log_tool_call", fake_log)
    with patch("nextcloud_tasks.list_tasks", new=AsyncMock(side_effect=RuntimeError("nextcloud down"))):
        asyncio.run(tv.run_verification("create_task", {"summary": "X"}, "OK", True, entity_id="t1"))
    # Backend failure -> verification_failed, propagated as a status, no raise.
    assert captured.get("verification_status") == "verification_failed"