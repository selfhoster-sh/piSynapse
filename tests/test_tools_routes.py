"""Tests for the tool taxonomy endpoint (GET /tools/groups)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm.intent import _KEYWORD_CHECKS, tool_group_keys
from routers.tools import router as tools_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(tools_router)
    return TestClient(app)


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
        "utility",
        "weather",
    ]


def test_groups_never_returns_human_readable_strings(client):
    resp = client.get("/tools/groups")
    groups = resp.json()["groups"]
    for g in groups:
        assert g.isascii()
        assert g.islower()
        assert " " not in g