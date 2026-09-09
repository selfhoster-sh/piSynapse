"""Single-source-of-truth contracts across files that cannot import each other.

install.py must stay stdlib-only (it runs before dependencies exist), so these
checks parse the files as text instead of importing them. If any assertion
fails, update the offending file — never weaken the test.
"""

import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def _env_literal(content: str, key: str) -> str:
    m = re.search(rf"^{key}=(\S+)\s*$", content, re.M)
    assert m, f"{key}= literal not found"
    return m.group(1)


def test_embed_model_single_source():
    install_py = _read("install.py")
    example_env = _read("example.env")
    config_py = _read("config.py")
    embedding_py = _read("embedding.py")

    from_template = _env_literal(install_py, "EMBED_MODEL")
    from_example = _env_literal(example_env, "EMBED_MODEL")
    m = re.search(r'EMBED_MODEL = os\.getenv\("EMBED_MODEL", "([^"]+)"\)', config_py)
    assert m, "config.py EMBED_MODEL default not found"
    from_config = m.group(1)

    assert from_template == from_example == from_config, (
        f"EMBED_MODEL drift: install.py={from_template} example.env={from_example} "
        f"config.py={from_config}"
    )
    # embedding.py must not define its own default (it poisoned cosine scores).
    assert "from config import EMBED_MODEL" in embedding_py
    assert 'os.getenv(\n    "EMBED_MODEL"' not in embedding_py


def test_summary_early_trigger_present_everywhere():
    config_py = _read("config.py")
    example_env = _read("example.env")
    install_py = _read("install.py")

    assert '"SUMMARY_EARLY_TRIGGER":' in config_py  # SETTINGS_SCHEMA (UI)
    assert _env_literal(example_env, "SUMMARY_EARLY_TRIGGER") == "6"
    assert _env_literal(install_py, "SUMMARY_EARLY_TRIGGER") == "6"
    assert '"SUMMARY_EARLY_TRIGGER"' in install_py  # preserved_keys


def test_stt_browser_option_in_schema():
    config_py = _read("config.py")
    m = re.search(r'"STT_ENGINE":\s*\{.*?\]\},', config_py, re.S)
    assert m, "STT_ENGINE schema entry not found"
    assert '"value": "browser"' in m.group(0)


def test_conflict_cosine_wired_everywhere():
    config_py = _read("config.py")
    example_env = _read("example.env")
    install_py = _read("install.py")
    feeder_py = _read("corpus_feeder.py")

    assert _env_literal(example_env, "CONFLICT_COSINE") == "0.50"
    assert _env_literal(install_py, "CONFLICT_COSINE") == "0.50"
    assert '"CONFLICT_COSINE"' in install_py  # preserved_keys
    assert '"CONFLICT_COSINE": (float, 0.50)' in config_py  # _NUMERIC_KEYS
    # Live read through config.get, not a frozen getattr default.
    assert 'config.get("CONFLICT_COSINE", 0.50)' in feeder_py
    assert 'getattr(config, "CONFLICT_COSINE"' not in feeder_py


def test_ui_language_default_is_english_everywhere():
    config_py = _read("config.py")
    example_env = _read("example.env")
    install_py = _read("install.py")
    messages_py = _read("messages.py")

    m = re.search(r'"UI_LANGUAGE":\s*\{[^}]*"default":\s*"(\w+)"', config_py)
    assert m and m.group(1) == "en", "schema default must be en"
    assert _env_literal(example_env, "UI_LANGUAGE") == "en"
    assert _env_literal(install_py, "UI_LANGUAGE") == "en"
    assert 'get("UI_LANGUAGE", "en")' in messages_py


def test_default_user_never_empty():
    config_py = _read("config.py")
    assert 'os.getenv("ASSISTANT_USER", "default") or "default"' in config_py


def test_media_max_mb_parse_is_guarded():
    chat_py = _read("routers/chat.py")
    assert "except (TypeError, ValueError):\n        max_mb = 100" in chat_py


def test_preserved_live_keys_survive_rerun():
    example_env = _read("example.env")
    install_py = _read("install.py")

    for key in ("PISERVE_ADMIN_TOKEN", "AUDIT_EXPORT_DIR"):
        for content, name in ((example_env, "example.env"), (install_py, "install.py")):
            m = re.search(rf"^{key}=(.*)$", content, re.M)
            assert m, f"{key}= line not found in {name}"
            assert m.group(1).strip() == "", f"{key} must default empty in {name}"
        assert f'"{key}"' in install_py  # preserved_keys


def test_litert_max_tokens_matches_config_default():
    install_py = _read("install.py")
    config_py = _read("config.py")

    m_cfg = re.search(r"DEFAULT_LLM_NUM_CTX\s*=\s*(\d+)", config_py)
    assert m_cfg, "config.DEFAULT_LLM_NUM_CTX not found"
    m_inst = re.search(r'"max_num_tokens":\s*(\d+)', install_py)
    assert m_inst, "install.py litert max_num_tokens not found"
    assert m_inst.group(1) == m_cfg.group(1), (
        f"litert max_num_tokens drift: install.py={m_inst.group(1)} "
        f"config.DEFAULT_LLM_NUM_CTX={m_cfg.group(1)}"
    )


def test_lockfile_pins_all_direct_requirements():
    import re as _re

    root = os.path.join(os.path.dirname(__file__), "..")
    with open(os.path.join(root, "requirements.txt"), encoding="utf-8") as f:
        direct = [
            _re.split(r"[<>=!~\s\[]", line.strip())[0].lower()
            for line in f
            if line.strip() and not line.startswith("#")
        ]
    with open(os.path.join(root, "requirements-lock.txt"), encoding="utf-8") as f:
        locked = {}
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "==" not in line:
                continue
            name, ver = line.split("==", 1)
            locked[name.strip().lower()] = ver.strip()
    missing = [d for d in direct if d not in locked or not locked[d]]
    assert not missing, f"unpinned direct requirements: {missing}"


def test_rate_limit_keys_present_everywhere():
    example_env = _read("example.env")
    install_py = _read("install.py")
    config_py = _read("config.py")

    for key, default in (("RATE_LIMIT_RPM", "30"), ("RATE_LIMIT_SESSION_RPM", "20"),
                         ("RATE_LIMIT_PUBLIC_RPM", "120")):
        assert _env_literal(example_env, key) == default
        assert _env_literal(install_py, key) == default
        assert f'"{key}"' in install_py  # preserved_keys
        assert key in config_py  # module constant + _NUMERIC_KEYS
