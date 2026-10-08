"""Cross-user isolation for the process-global Nextcloud caches (2026-10-08 analysis).

calendar_ops / nextcloud_tasks keep module-level caches (primary calendar,
events, todos) while the caller's Nextcloud identity is request-scoped
(NC_CREDS / NC_SHARED_OK). Every entry must be keyed by utils.nc_cache_key;
the task-calendar cache must also be gated by credentials BEFORE it is read
(the 2026-09-27 hole came back through that path).
"""
from contextlib import contextmanager

import pytest

import calendar_ops
import nextcloud_tasks as nt
from utils import NC_CREDS, NC_SHARED_OK, nc_cache_key

USER_A = {"url": "https://cloud-a.example", "user": "alice", "password": "pw-a"}
USER_B = {"url": "https://cloud-b.example", "user": "bob", "password": "pw-b"}


@contextmanager
def identity(creds: dict | None = None, shared: bool = False):
    t1 = NC_CREDS.set(creds)
    t2 = NC_SHARED_OK.set(shared)
    try:
        yield
    finally:
        NC_CREDS.reset(t1)
        NC_SHARED_OK.reset(t2)


@pytest.fixture(autouse=True)
def clean_caches():
    yield
    nt._task_calendars.clear()
    nt._todos_cache = None
    nt._todos_cache_ts = 0
    calendar_ops._primary_calendars.clear()
    calendar_ops._find_events_cache = None
    calendar_ops._today_cache = None


class FakeCal:
    def __init__(self, marker):
        self.marker = marker

    def get_supported_components(self):
        return ["VTODO"]

    def todos(self, include_completed=False):
        return [f"todos-from-{self.marker}"]


class FakePrincipal:
    def __init__(self, marker):
        self.marker = marker

    def calendars(self):
        return [FakeCal(self.marker)]


class FakeClient:
    def __init__(self, marker):
        self.marker = marker

    def principal(self):
        return FakePrincipal(self.marker)


# -- identity key ----------------------------------------------------------

def test_cache_key_distinct_per_identity():
    with identity(USER_A):
        key_a = nc_cache_key()
    with identity(USER_B):
        key_b = nc_cache_key()
    with identity(shared=True):
        key_shared = nc_cache_key()
    with identity():
        key_deny = nc_cache_key()
    assert len({key_a, key_b, key_shared, key_deny}) == 4
    with identity(USER_A):
        assert nc_cache_key() == key_a  # stable for the same identity


# -- task calendar: gate before cache + per-identity entries ---------------

def test_task_calendar_gate_runs_before_cache(monkeypatch):
    # Populate the cache under user A.
    monkeypatch.setattr(
        nt, "_build_dav_client",
        lambda url, user, pw, timeout: FakeClient(url),
    )
    with identity(USER_A):
        cal_a = nt._get_task_calendar()
    assert cal_a.marker == USER_A["url"]

    # No identity at all (no creds, shared not allowed): the credential gate
    # must deny BEFORE the cache is consulted — a raw global cache hit would
    # hand over user A's calendar (the 2026-09-27 hole reopened).
    with identity():
        assert nt._get_task_calendar() is None


def test_task_calendar_cached_per_identity(monkeypatch):
    monkeypatch.setattr(
        nt, "_build_dav_client",
        lambda url, user, pw, timeout: FakeClient(url),
    )
    with identity(USER_A):
        cal_a = nt._get_task_calendar()
        cal_a2 = nt._get_task_calendar()  # same identity → served from cache
    with identity(USER_B):
        cal_b = nt._get_task_calendar()
    assert cal_a is cal_a2
    assert cal_b is not cal_a
    assert cal_b.marker == USER_B["url"]


def test_todos_cache_never_served_across_identities(monkeypatch):
    monkeypatch.setattr(
        nt, "_build_dav_client",
        lambda url, user, pw, timeout: FakeClient(url),
    )
    with identity(USER_A):
        assert nt._fetch_todos_cached(False) == [f"todos-from-{USER_A['url']}"]
        # Same identity within TTL → cache hit (no marker change possible).
        assert nt._fetch_todos_cached(False) == [f"todos-from-{USER_A['url']}"]
    with identity(USER_B):
        assert nt._fetch_todos_cached(False) == [f"todos-from-{USER_B['url']}"]
    with identity():
        # No identity: callers are gated before this, but even a direct call
        # must never surface another user's todos.
        with pytest.raises(AttributeError):  # _get_task_calendar() → None
            nt._fetch_todos_cached(False)


# -- calendar_ops: primary calendar + event caches -------------------------

def test_primary_calendar_per_identity():
    with identity(USER_A):
        cal_a = calendar_ops._get_primary_calendar(FakeClient("A"))
        cal_a2 = calendar_ops._get_primary_calendar(FakeClient("A"))
    with identity(USER_B):
        cal_b = calendar_ops._get_primary_calendar(FakeClient("B"))
    assert cal_a is cal_a2
    assert cal_b is not cal_a
    assert cal_b.marker == "B"


def test_find_events_cache_never_served_across_identities(monkeypatch):
    def deny(_c):
        raise RuntimeError("stop-before-network")

    monkeypatch.setattr(calendar_ops, "_get_calendar", deny)

    with identity(USER_A):
        assert calendar_ops._find_events() is None  # failure not cached
        # Seed a fresh A entry (key computed under A's identity).
        calendar_ops._find_events_cache = (float("inf"), nc_cache_key(), ["A-event"])
        assert calendar_ops._find_events() == ["A-event"]  # A: hit
    with identity(USER_B):
        assert calendar_ops._find_events() is None  # B: miss → refetch → fails
    with identity(USER_A):
        assert calendar_ops._find_events() == ["A-event"]  # A still intact


def test_today_cache_never_served_across_identities(monkeypatch):
    def deny(_c):
        raise RuntimeError("stop-before-network")

    monkeypatch.setattr(calendar_ops, "_get_primary_calendar", deny)

    with identity(USER_A):
        calendar_ops._today_cache = (float("inf"), nc_cache_key(), [{"title": "A-event"}])
        assert calendar_ops.list_events_today() == [{"title": "A-event"}]  # A: hit
    with identity(USER_B):
        assert calendar_ops.list_events_today() == []  # B: miss → fetch fails → []
    with identity(USER_A):
        assert calendar_ops.list_events_today() == [{"title": "A-event"}]  # A intact
