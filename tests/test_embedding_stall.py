"""Embedding stall breaker: hung downloads must time out (2026-10-05 incident).

`TextEmbedding(model_name=...)` downloads weights on first use. A download
hung at 0% raises NO exception, so the old breaker (exception-only) never
tripped: `_model_lock` was held forever and every embed caller queued
behind it, pinning threads until the pool exhausted. `get_model` now runs
the load in a daemon thread with a hard join timeout, arms the cooldown on
timeout, and fails concurrent callers fast ("load already in progress")
instead of serializing them behind one download.
"""
import threading
import time

import pytest

import embedding as embmod


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    monkeypatch.setattr(embmod, "_model", None)
    monkeypatch.setattr(embmod, "_model_error_ts", 0.0)
    monkeypatch.setattr(embmod, "_loading", False)
    yield


class _HungTE:
    """Fake FastEmbed model whose constructor blocks (the 0% download)."""

    def __init__(self, model_name=None, started=None, release=None):
        if started:
            started.set()
        if release:
            release.wait(10)
        # If released late, the abandoned thread just completes and is
        # garbage-collected — nobody reads the result after a timeout.


def test_hung_download_times_out_and_arms_cooldown(monkeypatch):
    release = threading.Event()
    monkeypatch.setattr(
        embmod, "TextEmbedding",
        lambda model_name=None: _HungTE(model_name, started=None, release=release),
    )
    monkeypatch.setattr(embmod, "_MODEL_LOAD_TIMEOUT", 0.3)

    t0 = time.monotonic()
    with pytest.raises(RuntimeError) as exc:
        embmod.get_model()
    assert time.monotonic() - t0 < 5  # bounded, not forever
    assert "timed out" in str(exc.value)
    assert embmod._model_error_ts > 0  # cooldown armed

    # Retry inside the cooldown fails fast with the COOLDOWN message —
    # proving the loading flag was released (not stuck on "in progress").
    with pytest.raises(RuntimeError) as exc2:
        embmod.get_model()
    assert "cooldown" in str(exc2.value)
    release.set()


def test_concurrent_caller_fails_fast_while_loading(monkeypatch):
    started = threading.Event()
    release = threading.Event()
    monkeypatch.setattr(
        embmod, "TextEmbedding",
        lambda model_name=None: _HungTE(model_name, started=started, release=release),
    )
    monkeypatch.setattr(embmod, "_MODEL_LOAD_TIMEOUT", 0.5)

    first_caller_errors = []

    def _first_caller():
        try:
            embmod.get_model()
        except RuntimeError as e:
            first_caller_errors.append(str(e))

    t1 = threading.Thread(target=_first_caller)
    t1.start()
    assert started.wait(2)  # the load thread entered its constructor

    t0 = time.monotonic()
    with pytest.raises(RuntimeError) as exc:
        embmod.get_model()  # second caller while the first load hangs
    assert time.monotonic() - t0 < 0.3  # instant — did NOT queue behind the load
    assert "in progress" in str(exc.value)

    # Do NOT release the hang yet: t1's join(0.5) must hit its timeout
    # deterministically (the load thread stays blocked on release).
    t1.join(5)
    assert any("timed out" in e for e in first_caller_errors)
    release.set()  # cleanup: let the abandoned daemon thread exit


def test_successful_load_returns_model_and_caches(monkeypatch):
    calls = []

    class _FakeTE:
        pass

    monkeypatch.setattr(embmod, "TextEmbedding", lambda **k: calls.append(1) or _FakeTE())
    m1 = embmod.get_model()
    m2 = embmod.get_model()
    assert isinstance(m1, _FakeTE)
    assert m1 is m2  # cached — one load per process
    assert calls == [1]
    assert embmod._loading is False


def test_load_exception_preserves_type_and_arms_cooldown(monkeypatch):
    class _BoomTE:
        def __init__(self, model_name=None):
            raise OSError("network down")

    monkeypatch.setattr(embmod, "TextEmbedding", _BoomTE)
    with pytest.raises(OSError):
        embmod.get_model()
    assert embmod._model_error_ts > 0
    with pytest.raises(RuntimeError) as exc:
        embmod.get_model()
    assert "cooldown" in str(exc.value)
