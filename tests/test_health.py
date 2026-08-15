"""Tests for the /health endpoint's dependency aggregation (collect_health)."""

import asyncio

import main as mainmod


async def _ok():
    return "ok"


def test_collect_health_all_ok(monkeypatch):
    monkeypatch.setattr(mainmod, "_check_db", _ok)
    monkeypatch.setattr(mainmod, "_check_llm", _ok)
    monkeypatch.setattr(mainmod, "_check_nextcloud", _ok)

    result = asyncio.run(mainmod.collect_health())

    assert result["status"] == "healthy"
    assert result["dependencies"] == {"db": "ok", "llm": "ok", "nextcloud": "ok"}
    assert "model" in result


def test_collect_health_degraded_when_dependency_fails(monkeypatch):
    async def llm_err():
        return "error"

    monkeypatch.setattr(mainmod, "_check_db", _ok)
    monkeypatch.setattr(mainmod, "_check_llm", llm_err)
    monkeypatch.setattr(mainmod, "_check_nextcloud", _ok)

    result = asyncio.run(mainmod.collect_health())

    assert result["status"] == "degraded"
    assert result["dependencies"]["llm"] == "error"


def test_collect_health_disabled_nextcloud_does_not_degrade(monkeypatch):
    async def nc_disabled():
        return "disabled"

    monkeypatch.setattr(mainmod, "_check_db", _ok)
    monkeypatch.setattr(mainmod, "_check_llm", _ok)
    monkeypatch.setattr(mainmod, "_check_nextcloud", nc_disabled)

    result = asyncio.run(mainmod.collect_health())

    assert result["status"] == "healthy"
    assert result["dependencies"]["nextcloud"] == "disabled"
