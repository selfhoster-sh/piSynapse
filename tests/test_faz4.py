"""Tests for the FAZ 4 low-priority cleanups.

Covers: weather geo-cache LRU bounds, calendar widget today-cache TTL + write
invalidation, opportunistic DB VACUUM, embedding legacy-blob deserialization,
and the narrowed body-size limit for /chat routes.
"""

import io
import pickle
from datetime import datetime

import numpy as np
import pytest

import calendar_ops
import main as mainmod
import weather
from embedding import _deserialize

# -- Bulgu 15: weather._geo_cache LRU bounds -----------------------------------

def test_geo_cache_evicts_least_recently_used():
    assert weather._GEO_CACHE_MAX == 100
    weather._geo_cache.clear()
    for i in range(weather._GEO_CACHE_MAX + 5):
        weather._cache_city(f"city{i}", str(i), str(i + 1))
    assert len(weather._geo_cache) == weather._GEO_CACHE_MAX
    assert "city0" not in weather._geo_cache
    assert "city104" in weather._geo_cache


def test_geo_cache_lookup_moves_entry_to_most_recent():
    weather._geo_cache.clear()
    weather._cache_city("a", "1", "1")
    weather._cache_city("b", "2", "2")
    assert next(iter(weather._geo_cache)) == "a"
    assert weather._geo_lookup("a") == ("1", "1")
    assert next(iter(weather._geo_cache)) == "b"  # "a" was moved to most-recent
    assert list(weather._geo_cache)[-1] == "a"


def test_geo_cache_miss_returns_none():
    weather._geo_cache.clear()
    assert weather._geo_lookup("nope") is None


# -- Bulgu 27: calendar widget today-cache -------------------------------------

class _FakeProp:
    def __init__(self, value):
        self.value = value


class _FakeVevent:
    def __init__(self, title, hour, uid):
        self.summary = _FakeProp(title)
        self.dtstart = _FakeProp(datetime(2026, 8, 16, hour, 30))
        self.uid = _FakeProp(uid)


class _FakeEvent:
    def __init__(self, title, hour, uid):
        vi = type("VI", (), {"vevent": _FakeVevent(title, hour, uid)})
        self.vobject_instance = vi()


class _FakeCalendar:
    def __init__(self, events):
        self.events = events
        self.calls = 0

    def date_search(self, start, end):
        self.calls += 1
        return self.events


@pytest.fixture
def calendar_widget(monkeypatch):
    cal = _FakeCalendar([_FakeEvent("Planlı toplantı", 9, "uid-1")])
    monkeypatch.setattr(calendar_ops, "_get_nextcloud_client", lambda: object())
    monkeypatch.setattr(calendar_ops, "_get_primary_calendar", lambda c: cal)
    monkeypatch.setattr(calendar_ops, "_today_cache", None)
    return cal


def test_today_cache_serves_second_call_from_cache(calendar_widget):
    first = calendar_ops.list_events_today()
    second = calendar_ops.list_events_today()
    assert first == second == [{"time": "09:30", "title": "Planlı toplantı", "uid": "uid-1"}]
    assert calendar_widget.calls == 1


def test_today_cache_expires_after_ttl(calendar_widget, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(calendar_ops.time, "monotonic", lambda: clock[0])
    calendar_ops.list_events_today()
    clock[0] = calendar_ops._TODAY_CACHE_TTL + 1.0
    calendar_ops.list_events_today()
    assert calendar_widget.calls == 2


def test_today_cache_invalidated_on_write(calendar_widget):
    calendar_ops.list_events_today()
    assert calendar_widget.calls == 1
    calendar_ops._invalidate_today_cache()
    calendar_ops.list_events_today()
    assert calendar_widget.calls == 2


def test_today_cache_failure_is_not_cached(calendar_widget, monkeypatch):
    monkeypatch.setattr(calendar_ops, "_get_primary_calendar", lambda c: (_ for _ in ()).throw(RuntimeError("down")))
    assert calendar_ops.list_events_today() == []
    assert calendar_ops.list_events_today() == []


# -- Bulgu 20: opportunistic VACUUM --------------------------------------------

@pytest.mark.asyncio
async def test_vacuum_compacts_fragmented_db(tmp_path):
    import aiosqlite

    from db import _vacuum_if_fragmented

    path = tmp_path / "frag.db"
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=OFF")
    await conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, payload TEXT)")
    await conn.executemany("INSERT INTO t (payload) VALUES (?)", [("x" * 500,) for _ in range(5000)])
    await conn.commit()
    await conn.execute("DELETE FROM t")
    await conn.commit()

    async with conn.execute("PRAGMA page_count") as cur:
        before = (await cur.fetchone())[0]
    async with conn.execute("PRAGMA freelist_count") as cur:
        free_before = (await cur.fetchone())[0]
    assert before > 256 and free_before / before > 0.2  # precondition for the helper

    await _vacuum_if_fragmented(conn)

    async with conn.execute("PRAGMA page_count") as cur:
        after = (await cur.fetchone())[0]
    assert after < before
    await conn.close()


@pytest.mark.asyncio
async def test_vacuum_skips_small_healthy_db(tmp_path):
    import aiosqlite

    from db import _vacuum_if_fragmented

    path = tmp_path / "small.db"
    conn = await aiosqlite.connect(path)
    await conn.execute("PRAGMA journal_mode=OFF")
    await conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    await conn.commit()
    async with conn.execute("PRAGMA page_count") as cur:
        before = (await cur.fetchone())[0]
    assert before <= 256  # below the helper's threshold

    await _vacuum_if_fragmented(conn)

    async with conn.execute("PRAGMA page_count") as cur:
        after = (await cur.fetchone())[0]
    assert after == before
    await conn.close()


# -- Bulgu 21: embedding legacy blob deserialization ---------------------------

def test_deserialize_raw_float32():
    vec = np.array([0.5, -1.0, 2.25], dtype="float32")
    result = _deserialize(vec.tobytes())
    np.testing.assert_allclose(result, vec)


def test_deserialize_raw_float32_starting_with_0x80():
    vec = np.array([0x00000080, 0xC0000000, 0x40400000], dtype=np.uint32).view(np.float32)
    blob = vec.tobytes()
    assert blob[0] == 0x80
    np.testing.assert_allclose(_deserialize(blob), vec)


def test_deserialize_legacy_pickle():
    vec = np.array([0.25, 1.5], dtype="float32")
    blob = pickle.dumps(vec)
    assert blob.startswith(b"\x80")
    np.testing.assert_allclose(_deserialize(blob), vec)


def test_deserialize_legacy_npy():
    vec = np.array([3.0, -0.5], dtype="float32")
    buf = io.BytesIO()
    np.save(buf, vec)
    blob = buf.getvalue()
    assert blob.startswith(b"\x93NUMPY")
    np.testing.assert_allclose(_deserialize(blob), vec)


# -- Bulgu 28: narrowed body-size limit for /chat routes -----------------------

@pytest.fixture
def body_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.middleware("http")(mainmod.security_middleware)

    @app.post("/chat")
    async def chat():
        return {"ok": True}

    @app.post("/chat/tts")
    async def tts():
        return {"ok": True}

    @app.post("/chat/transcribe")
    async def transcribe():
        return {"ok": True}

    return app


@pytest.fixture
def body_client(body_app, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(mainmod, "API_KEY", "secret-key")
    monkeypatch.setattr(mainmod, "TRUSTED_HOSTS", set())
    return TestClient(body_app, base_url="http://localhost")


def test_chat_post_body_capped_at_4mb(body_client):
    big = b"x" * (4 * 1024 * 1024 + 10)
    r = body_client.post("/chat", content=big, headers={"x-api-key": "secret-key"})
    assert r.status_code == 413


def test_tts_post_body_capped_at_4mb(body_client):
    big = b"x" * (4 * 1024 * 1024 + 10)
    r = body_client.post("/chat/tts", content=big, headers={"x-api-key": "secret-key"})
    assert r.status_code == 413


def test_transcribe_post_allows_large_body(body_client):
    big = b"x" * (6 * 1024 * 1024)
    r = body_client.post("/chat/transcribe", content=big, headers={"x-api-key": "secret-key"})
    assert r.status_code != 413  # reaches the handler, which is a stub here
