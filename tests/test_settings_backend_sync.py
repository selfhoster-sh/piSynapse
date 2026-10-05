"""Backend-switch model sync in PATCH /config/settings.

Convention (install.py): LLM_MODEL is stored dash-form for litert
("gemma4-e2b") and colon-form for ollama ("gemma4:e2b"). Switching the
backend must keep both in sync — otherwise every LLM call 404s.
"""

import asyncio

import routers.config as rc


class _FakeOptions:
    """Stands in for get_llm_model_options, keyed by backend."""

    def __init__(self, per_backend):
        self.per_backend = per_backend
        self.requested = []

    async def __call__(self, backend=None):
        target = (backend or "litert").strip().lower()
        self.requested.append(target)
        return [{"value": v} for v in self.per_backend[target]]


def _run_update(monkeypatch, tmp_path, values, options_fake, initial="LLM_BACKEND=litert\nLLM_MODEL=gemma4-e2b\n"):
    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / ".env")
    monkeypatch.setattr(rc, "get_llm_model_options", options_fake)
    # Pre-flight probe is a network call — default to reachable here; the
    # gate's own behavior is covered by dedicated tests below.
    import config as _cfg

    monkeypatch.setattr(_cfg, "probe_backend", lambda b: (True, ""))
    (tmp_path / ".env").write_text(initial)

    from types import SimpleNamespace

    admin_request = SimpleNamespace(state=SimpleNamespace(user_id="default", is_admin=True))
    body = rc.SettingsUpdate(values=values)
    result = asyncio.run(rc.update_settings(body, admin_request))
    content = (tmp_path / ".env").read_text()
    return result, content


def test_backend_switch_rejected_when_daemon_down(monkeypatch, tmp_path):
    """Pre-flight gate: no persistence when the new daemon is unreachable."""
    monkeypatch.setenv("LLM_BACKEND", "litert")
    monkeypatch.setenv("LLM_MODEL", "gemma4-e2b")
    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("LLM_BACKEND=litert\nLLM_MODEL=gemma4-e2b\n")
    import config as _cfg

    monkeypatch.setattr(_cfg, "probe_backend", lambda b: (False, "ollama daemon not reachable"))

    from types import SimpleNamespace

    admin_request = SimpleNamespace(state=SimpleNamespace(user_id="default", is_admin=True))
    from fastapi import HTTPException

    try:
        asyncio.run(rc.update_settings(rc.SettingsUpdate(values={"LLM_BACKEND": "ollama"}), admin_request))
        raise AssertionError("should have raised")
    except HTTPException as e:
        assert e.status_code == 409  # startable: client offers to start it
        assert "ollama" in e.detail.lower()
    # Nothing mutated: .env and process env stay on the old backend.
    assert "ollama" not in (tmp_path / ".env").read_text()
    import os

    assert os.environ["LLM_BACKEND"] == "litert"


def test_backend_switch_starts_daemon_on_request(monkeypatch, tmp_path):
    """With start_backend=true and a daemon that then answers, the switch succeeds."""
    monkeypatch.setenv("LLM_BACKEND", "litert")
    monkeypatch.setenv("LLM_MODEL", "gemma4-e2b")
    monkeypatch.setattr(rc, "ENV_PATH", tmp_path / ".env")
    (tmp_path / ".env").write_text("LLM_BACKEND=litert\nLLM_MODEL=gemma4-e2b\n")
    import config as _cfg

    calls = {"probe": 0, "start": []}

    def fake_probe(b):
        calls["probe"] += 1
        return (calls["probe"] > 1, "" if calls["probe"] > 1 else "down")

    monkeypatch.setattr(_cfg, "probe_backend", fake_probe)
    monkeypatch.setattr(_cfg, "start_backend", lambda b, wait_s=25: calls["start"].append(b) or (True, ""))
    monkeypatch.setattr(rc, "get_llm_model_options", _FakeOptions({"litert": ["gemma4-e2b"], "ollama": ["gemma4:e2b"]}))

    from types import SimpleNamespace

    admin_request = SimpleNamespace(state=SimpleNamespace(user_id="default", is_admin=True))
    result = asyncio.run(rc.update_settings(
        rc.SettingsUpdate(values={"LLM_BACKEND": "ollama"}, start_backend=True), admin_request))
    assert calls["start"] == ["ollama"]  # started exactly once
    assert "LLM_BACKEND" in result["updated"]
    assert "ollama" in (tmp_path / ".env").read_text()


def test_backend_switch_automaps_model(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_BACKEND", "litert")
    monkeypatch.setenv("LLM_MODEL", "gemma4-e2b")
    fake = _FakeOptions({"litert": ["gemma4-e2b"], "ollama": ["gemma4:e2b"]})

    result, content = _run_update(
        monkeypatch, tmp_path, {"LLM_BACKEND": "ollama"}, fake,
    )

    assert result["ok"] is True
    assert sorted(result["updated"]) == ["LLM_BACKEND", "LLM_MODEL"]
    assert "LLM_MODEL=gemma4:e2b" in content
    # Model validation/mapping queried the NEW backend's daemon.
    assert "ollama" in fake.requested


def test_backend_switch_with_explicit_model_validates_against_new_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_BACKEND", "litert")
    monkeypatch.setenv("LLM_MODEL", "gemma4-e2b")
    fake = _FakeOptions({"litert": ["gemma4-e2b"], "ollama": ["gemma4:e2b", "qwen:7b"]})

    result, content = _run_update(
        monkeypatch, tmp_path,
        {"LLM_BACKEND": "ollama", "LLM_MODEL": "qwen:7b"}, fake,
    )

    # Colon-form id would be rejected against litert's list; it must be
    # validated against ollama's list instead.
    assert result["ok"] is True
    assert "LLM_MODEL=qwen:7b" in content


def test_switch_without_equivalent_keeps_old_model_and_succeeds(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_BACKEND", "litert")
    monkeypatch.setenv("LLM_MODEL", "some-only-litert-model")
    fake = _FakeOptions({"litert": ["some-only-litert-model"], "ollama": ["gemma4:e2b"]})

    result, content = _run_update(
        monkeypatch, tmp_path, {"LLM_BACKEND": "ollama"}, fake,
        initial="LLM_BACKEND=litert\nLLM_MODEL=some-only-litert-model\n",
    )

    assert result["ok"] is True
    assert "LLM_MODEL=some-only-litert-model" in content  # untouched, manual pick needed


def test_no_backend_change_skips_automap(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_BACKEND", "litert")
    monkeypatch.setenv("LLM_MODEL", "gemma4-e2b")
    fake = _FakeOptions({"litert": ["gemma4-e2b"], "ollama": ["gemma4:e2b"]})

    result, content = _run_update(
        monkeypatch, tmp_path, {"LLM_NUM_CTX": "4096"}, fake,
    )

    assert result["ok"] is True
    assert result["updated"] == ["LLM_NUM_CTX"]
    assert "LLM_MODEL=gemma4-e2b" in content
