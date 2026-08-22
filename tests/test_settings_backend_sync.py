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
    (tmp_path / ".env").write_text(initial)

    body = rc.SettingsUpdate(values=values)
    result = asyncio.run(rc.update_settings(body))
    content = (tmp_path / ".env").read_text()
    return result, content


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
