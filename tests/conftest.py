"""pytest configuration for piSynapse tests."""

import asyncio
import os
import sys

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def pytest_sessionfinish(session, exitstatus):
    # Safety net: a leaked module-global aiosqlite connection keeps its
    # NON-daemon worker thread alive, which would block interpreter exit and
    # leave CI "in_progress" forever (all tests already reported). Close it.
    try:
        from db import close_db

        asyncio.run(close_db())
    except Exception:
        pass

