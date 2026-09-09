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

