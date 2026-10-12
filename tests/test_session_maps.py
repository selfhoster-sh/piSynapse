"""db.py session-map persistence (notes/tasks/calendar list-number → id maps).

Store/replace/read per session — used so "not 3" / "görevi tamamla 2" resolve
after a restart. Was uncovered (higher-level flows mock it). Real tmp DB.
"""
import asyncio

import pytest

import db as dbmod


@pytest.fixture
def mdb(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "maps.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_notes_map_roundtrip_and_replace(mdb):
    notes = [
        {"id": 10, "title": "Alışveriş", "category": "home", "content": "süt ve ekmek"},
        {"id": 11, "title": "İş", "category": "work", "content": "rapor yaz"},
    ]
    asyncio.run(dbmod.save_notes_map("s1", notes, user_id="u1"))
    got = asyncio.run(dbmod.get_notes_map("s1", user_id="u1"))
    assert [g["id"] for g in got] == [10, 11]
    assert got[0]["title"] == "Alışveriş"
    assert got[0]["preview"] == "süt ve ekmek"

    # Replace with a shorter list — the old rows must be gone.
    asyncio.run(dbmod.save_notes_map("s1", [{"id": 99, "title": "Yeni"}], user_id="u1"))
    got2 = asyncio.run(dbmod.get_notes_map("s1", user_id="u1"))
    assert [g["id"] for g in got2] == [99]


def test_notes_map_empty_inputs_are_noops(mdb):
    asyncio.run(dbmod.save_notes_map("s1", [], user_id="u1"))
    assert asyncio.run(dbmod.get_notes_map("s1", user_id="u1")) == []
    assert asyncio.run(dbmod.get_notes_map("", user_id="u1")) == []
    asyncio.run(dbmod.save_notes_map("", [{"id": 1}], user_id="u1"))  # no-op, no raise


def test_notes_map_user_scoped(mdb):
    asyncio.run(dbmod.save_notes_map("s1", [{"id": 1, "title": "alice-note"}], user_id="alice"))
    assert asyncio.run(dbmod.get_notes_map("s1", user_id="bob")) == []
    assert asyncio.run(dbmod.get_notes_map("s1", user_id="alice"))[0]["title"] == "alice-note"


def test_tasks_map_roundtrip_and_clear(mdb):
    tasks = [
        {"uid": "t1", "summary": "Faturayı öde", "due": "2026-10-20", "priority": 1, "completed": False},
        {"uid": "t2", "summary": "Spor", "priority": 3, "completed": True},
    ]
    asyncio.run(dbmod.save_tasks_map("s1", tasks, user_id="u1"))
    got = asyncio.run(dbmod.get_tasks_map("s1", user_id="u1"))
    assert [g["uid"] for g in got] == ["t1", "t2"]
    assert got[0]["summary"] == "Faturayı öde"
    assert got[1]["completed"] is True

    asyncio.run(dbmod.clear_tasks_map("s1"))
    assert asyncio.run(dbmod.get_tasks_map("s1", user_id="u1")) == []


def test_calendar_map_roundtrip_and_clear(mdb):
    events = [
        {"uid": "e1", "summary": "Toplantı", "start": "2026-10-12 10:00"},
        {"uid": "e2", "summary": "Öğle", "start": "2026-10-12 12:00"},
    ]
    asyncio.run(dbmod.save_calendar_map("s1", events, user_id="u1"))
    got = asyncio.run(dbmod.get_calendar_map("s1", user_id="u1"))
    assert [g["uid"] for g in got] == ["e1", "e2"]
    assert got[0]["start"] == "2026-10-12 10:00"

    asyncio.run(dbmod.clear_calendar_map("s1"))
    assert asyncio.run(dbmod.get_calendar_map("s1", user_id="u1")) == []


def test_calendar_map_empty_and_missing_session(mdb):
    assert asyncio.run(dbmod.get_calendar_map("", user_id="u1")) == []
    asyncio.run(dbmod.save_calendar_map("s1", [], user_id="u1"))  # no-op
    assert asyncio.run(dbmod.get_calendar_map("s1", user_id="u1")) == []
