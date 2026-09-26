"""pytest configuration for piSynapse tests."""

import asyncio
import os
import sys

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Deterministic API key: the auth middleware is fail-closed (no key = 503 on
# protected routes), and config.py load_dotenv() would otherwise pick up a
# machine-specific .env. setdefault keeps a key present regardless so tests
# never depend on the local .env. Respect an explicitly exported API_KEY.
os.environ.setdefault("API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _hermetic_embeddings(monkeypatch):
    """No test may download ML weights: deterministic bag-of-words vectors.

    Same text → same vector; overlapping texts → high cosine (keeps
    duplicate/conflict tests meaningful); disjoint texts → near-orthogonal.
    Per-test fakes still override this (they apply after autouse fixtures).
    """
    import re as _re

    import numpy as _np

    import embedding as embmod

    _dim = 128
    _word_re = _re.compile(r"[a-zçğıöşüâîû0-9]+")

    def _vec(text):
        v = _np.zeros(_dim, dtype="float32")
        words = _word_re.findall(str(text or "").casefold()) or ["<empty>"]
        for w in words:
            v[abs(hash(w)) % _dim] += 1.0
        n = float(_np.linalg.norm(v)) or 1.0
        return (v / n).tobytes()

    async def _embed_async(text="", *a, **k):
        return _vec(text)

    async def _embed_batch_async(texts=(), *a, **k):
        return [_vec(t) for t in texts]

    def _embed_sync(text="", *a, **k):
        return _vec(text)

    monkeypatch.setattr(embmod, "embed_async", _embed_async)
    monkeypatch.setattr(embmod, "embed_batch_async", _embed_batch_async)
    monkeypatch.setattr(embmod, "embed", _embed_sync)


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Every test gets a fresh initialized DB (test-DB isolation rule).

    No test may depend on the ambient live assistant.db: CI checkouts have
    no such file, so any default-DB access fails with 'no such table'.
    Tests needing specific rows layer their own fixtures on top of this one.
    """
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "t.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    # Rate limiters are process-global token buckets: refill them so one
    # test's traffic can never 429 the next (CI runs the suite in 1 process).
    import main as mainmod

    monkeypatch.setattr(mainmod, "_rate_limiter", mainmod._RateLimiter(rpm=mainmod._rate_limiter.rpm))
    monkeypatch.setattr(mainmod, "_session_limiter", mainmod._RateLimiter(rpm=mainmod._session_limiter.rpm))
    monkeypatch.setattr(mainmod, "_public_limiter", mainmod._RateLimiter(rpm=mainmod._public_limiter.rpm))
    yield
    asyncio.run(dbmod.close_db())


def pytest_sessionfinish(session, exitstatus):
    # Safety net: a leaked module-global aiosqlite connection keeps its
    # NON-daemon worker thread alive, which would block interpreter exit and
    # leave CI "in_progress" forever (all tests already reported). Close it.
    try:
        from db import close_db

        asyncio.run(close_db())
    except Exception:
        pass

