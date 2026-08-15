"""Tests for FAZ 3 stability fixes: retry backoff, periodic cleanup, SSE idle
timeout, DAV/notes error handling and singleton locking.
"""

import asyncio

import httpx
import pytest

import db as dbmod
import utils as utilsmod

# -- retry: exponential backoff + 429/5xx vs deterministic 4xx (bulgu 9) --

def test_retry_uses_exponential_backoff(monkeypatch):
    sleeps = []

    async def fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    @utilsmod.retry(attempts=3, delay=1.0, backoff=2.0, jitter=0.0)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]  # delay * backoff^0, delay * backoff^1


def test_retry_does_not_retry_4xx_non_429():
    calls = {"n": 0}

    @utilsmod.retry(attempts=3, delay=1.0, backoff=2.0, jitter=0.0)
    async def flaky():
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "403 Forbidden",
            request=httpx.Request("GET", "http://example.com"),
            response=httpx.Response(403),
        )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(flaky())
    assert calls["n"] == 1  # deterministic 4xx → no retry


def test_retry_retries_on_429(monkeypatch):
    sleeps = []

    async def fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    @utilsmod.retry(attempts=3, delay=1.0, backoff=2.0, jitter=0.0)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise httpx.HTTPStatusError(
                "429 Too Many Requests",
                request=httpx.Request("GET", "http://example.com"),
                response=httpx.Response(429),
            )
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert calls["n"] == 2
    assert sleeps == [1.0]


def test_retry_retries_on_5xx(monkeypatch):
    sleeps = []

    async def fake_sleep(secs):
        sleeps.append(secs)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    calls = {"n": 0}

    @utilsmod.retry(attempts=3, delay=1.0, backoff=2.0, jitter=0.0)
    async def flaky():
        calls["n"] += 1
        raise httpx.HTTPStatusError(
            "500 Internal Server Error",
            request=httpx.Request("GET", "http://example.com"),
            response=httpx.Response(500),
        )

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(flaky())
    assert calls["n"] == 3
    assert sleeps == [1.0, 2.0]


# -- periodic retention cleanup loop (bulgu 7) --

def test_periodic_cleanup_loop_ticks_and_propagates_cancel(monkeypatch):
    cleaned = []

    async def fake_cleanup():
        cleaned.append(1)

    monkeypatch.setattr(dbmod, "cleanup_expired_data", fake_cleanup)
    slept = []

    async def fake_sleep(secs):
        slept.append(secs)
        if len(slept) == 2:
            raise asyncio.CancelledError

    async def go():
        await dbmod.periodic_cleanup_loop(interval=86400, sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert slept == [86400, 86400]
    assert cleaned == [1]


def test_periodic_cleanup_loop_retries_after_error(monkeypatch):
    attempts = []

    async def failing_cleanup():
        attempts.append(1)
        raise RuntimeError("db locked")

    monkeypatch.setattr(dbmod, "cleanup_expired_data", failing_cleanup)
    slept = []

    async def fake_sleep(secs):
        slept.append(secs)
        if len(slept) == 3:
            raise asyncio.CancelledError

    async def go():
        await dbmod.periodic_cleanup_loop(interval=3600, sleep=fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())

    assert attempts == [1, 1]
    assert slept == [3600, 3600, 3600]


# -- tool audit rollup: atomic per-day transaction (bulgu 22) --

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


def test_rollup_uses_single_transaction_and_stays_idempotent(audit_db):
    async def seed():
        db = await dbmod.get_db()
        for i in range(3):
            await db.execute(
                "INSERT INTO tool_audit_log (tool_name, params, success, created_at) "
                "VALUES (?, ?, ?, ?)",
                ("get_datetime", "{}", 1, f"2026-06-0{i+1} 12:00:00"),
            )
        await db.commit()

    asyncio.run(seed())
    assert asyncio.run(dbmod.rollup_tool_audit()) == 3
    # Second pass: no duplicate summary rows, nothing left to summarize.
    assert asyncio.run(dbmod.rollup_tool_audit()) == 0

    rows = asyncio.run(_fetch_all("SELECT is_summary, day FROM tool_audit_log"))
    summaries = [r for r in rows if r[0] == 1]
    assert len(summaries) == 3
    assert {r[1] for r in summaries} == {"2026-06-01", "2026-06-02", "2026-06-03"}


# -- SSE per-read idle timeout (bulgu 12) --

def test_iter_sse_lines_aborts_on_idle_timeout(monkeypatch):
    from llm import stream as streammod

    async def aiter_bytes():
        yield b'data: {"hello": 1}\n'
        await asyncio.sleep(0.05)
        yield b'data: {"world": 2}\n'

    class FakeResp:
        def aiter_bytes(self):
            return aiter_bytes()

    async def go():
        lines = []
        async for line in streammod._iter_sse_lines(FakeResp(), idle_timeout=0.02):
            lines.append(line)
        return lines

    lines = asyncio.run(go())
    # Only the first line arrives before the 20ms idle gap aborts the stream.
    assert lines == ['data: {"hello": 1}']


def test_iter_sse_lines_yields_all_lines():
    from llm import stream as streammod

    async def aiter_bytes():
        yield b"line one\nline two\n"
        yield b"line three\n"

    class FakeResp:
        def aiter_bytes(self):
            return aiter_bytes()

    async def go():
        return [line async for line in streammod._iter_sse_lines(FakeResp(), idle_timeout=5.0)]

    assert asyncio.run(go()) == ["line one", "line two", "line three"]


# -- Nextcloud tasks: don't swallow network errors as "not found" (bulgu 25) --

def test_tasks_list_raises_on_fetch_error(monkeypatch):
    import nextcloud_tasks as nt
    monkeypatch.setattr(utilsmod.time, "sleep", lambda s: None)

    class BoomCal:
        def todos(self):
            raise RuntimeError("network unreachable")

    monkeypatch.setattr(nt, "_get_task_calendar", lambda: BoomCal())
    with pytest.raises(RuntimeError):
        nt._list_tasks_sync(show_completed=False)


def test_tasks_complete_raises_on_fetch_error(monkeypatch):
    import nextcloud_tasks as nt
    monkeypatch.setattr(utilsmod.time, "sleep", lambda s: None)

    class BoomCal:
        def todos(self):
            raise RuntimeError("network unreachable")

    monkeypatch.setattr(nt, "_get_task_calendar", lambda: BoomCal())
    with pytest.raises(RuntimeError):
        nt._complete_task_sync("abc")


# -- Nextcloud notes: NotFound vs network error (bulgu 25, 26) --

def test_notes_delete_returns_false_only_for_404(monkeypatch):
    from nextcloud_notes import NextcloudNotesClient, NotFoundError
    monkeypatch.setattr(utilsmod.time, "sleep", lambda s: None)

    client = NextcloudNotesClient()
    client._request = lambda *a, **k: (_ for _ in ()).throw(NotFoundError("gone"))
    assert client.delete_note(1) is False


def test_notes_delete_raises_on_network_error(monkeypatch):
    from nextcloud_notes import NextcloudNotesClient
    monkeypatch.setattr(utilsmod.time, "sleep", lambda s: None)

    client = NextcloudNotesClient()
    client._request = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("timeout"))
    with pytest.raises(RuntimeError):
        client.delete_note(1)


def test_notes_update_fetches_merge_within_single_retry_scope(monkeypatch):
    from nextcloud_notes import NextcloudNotesClient

    calls = []
    client = NextcloudNotesClient()

    def fake_request(method, path, data=None):
        calls.append((method, path))
        if method == "GET":
            return {"etag": "abc", "title": "old"}
        return {"id": 1, "etag": "def"}

    client._request = fake_request
    result = client.update_note(1, title="new")
    assert result["etag"] == "def"
    assert calls == [("GET", "notes/1"), ("PUT", "notes/1")]


def test_notes_404_maps_to_not_found(monkeypatch):
    from nextcloud_notes import NextcloudNotesClient, NotFoundError
    monkeypatch.setattr(utilsmod.time, "sleep", lambda s: None)

    client = NextcloudNotesClient()

    def fake_request(method, path, data=None):
        raise NotFoundError("gone")

    client._request = fake_request
    assert client.update_note(99, title="x") is None
