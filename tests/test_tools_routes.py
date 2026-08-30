"""Tests for the tool taxonomy endpoint (GET /tools/groups)."""

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db as dbmod
import llm.intent as li_mod
from llm.intent import _KEYWORD_CHECKS, tool_group_keys
from routers.tools import router as tools_router
from tools.definitions import TOOL_GROUPS, get_combined_tools, get_tools_for_group


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(tools_router)
    return TestClient(app)


@pytest.fixture
def audit_db(tmp_path, monkeypatch):
    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "tg.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    yield dbmod
    asyncio.run(dbmod.close_db())


def test_tool_group_keys_derived_from_keyword_checks():
    expected = sorted({group for _, group in _KEYWORD_CHECKS})
    assert tool_group_keys() == tuple(expected)


def test_groups_returns_canonical_keys(client):
    resp = client.get("/tools/groups")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["groups"] == [
        "calendar",
        "email",
        "memory",
        "notes",
        "tasks",
        "weather",
    ]


def test_groups_never_returns_human_readable_strings(client):
    resp = client.get("/tools/groups")
    groups = resp.json()["groups"]
    for g in groups:
        assert g.isascii()
        assert g.islower()
        assert " " not in g


def test_utility_is_not_a_classification_target():
    assert "utility" not in _KEYWORD_CHECKS
    assert "utility" not in tool_group_keys()
    assert "utility" not in TOOL_GROUPS
    assert all(g != "utility" for g, _ in li_mod._TOOL_EMBED_CORPUS)


def test_every_domain_toolset_includes_get_datetime():
    for group in ("calendar", "tasks", "weather", "notes", "memory", "email"):
        assert "get_datetime" in TOOL_GROUPS[group]
        names = {t["function"]["name"] for t in get_tools_for_group(group)}
        assert "get_datetime" in names


def test_combined_fallback_includes_get_datetime():
    names = {t["function"]["name"] for t in get_combined_tools()}
    assert "get_datetime" in names


def test_bare_datetime_query_has_no_keyword_group():
    # Regression: "saat kaç" must no longer route to the removed utility
    # group. It goes to the embedding/LLM/question fallback where combined
    # tools (with get_datetime) are still available.
    assert li_mod._keyword_group("saat kaç") is None
    assert li_mod._hit_groups("saat kaç") == set()


def test_bare_datetime_query_falls_back_without_garbage(audit_db, monkeypatch):
    monkeypatch.setattr(li_mod, "_tool_embed_cache", [])
    monkeypatch.setattr(li_mod, "get", lambda k, d=None: {"INTENT_LLM_FALLBACK": "off"}.get(k, d))
    intent, group = asyncio.run(li_mod._classify_intent("saat kaç"))
    assert intent == "question"
    assert group is None
