"""Installer robustness (Faz 7a): batch mode, atomic downloads, rerun safety."""

import os

import install as inst


def test_menu_batch_returns_default_without_stdin(monkeypatch):
    monkeypatch.setattr(inst, "BATCH_MODE", True)
    assert inst.menu("Pick", [("a", ""), ("b", "")], default=2) == 2
    assert inst.ask("Name", "def") == "def"
    assert inst.ask_yesno("Sure?", default=False) is False


def test_piper_partial_download_leaves_no_poisin_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    def fake_run(cmd, **kw):
        tmp = cmd[cmd.index("-o") + 1]
        os.makedirs(os.path.dirname(tmp), exist_ok=True)
        open(tmp, "w").close()  # interrupted download residue

        class R:
            returncode = 1

        return R()

    monkeypatch.setattr(inst.subprocess, "run", fake_run)
    assert inst._download_piper_voice("v", "repo/v") is False
    d = os.path.join("models", "piper")
    assert not os.path.exists(os.path.join(d, "v.onnx"))
    assert not os.path.exists(os.path.join(d, "v.onnx.tmp"))


def test_piper_existing_nonempty_file_skips_download(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    d = os.path.join("models", "piper")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "v.onnx"), "wb").write(b"data")
    open(os.path.join(d, "v.onnx.json"), "wb").write(b"{}")

    def _boom(cmd, **kw):
        raise AssertionError("curl must not run for complete files")

    monkeypatch.setattr(inst.subprocess, "run", _boom)
    assert inst._download_piper_voice("v", "repo/v") is True


def test_trusted_hosts_not_preserved(monkeypatch):
    import re as _re

    src = open(inst.__file__, encoding="utf-8").read()
    m = _re.search(r"preserved_keys = \{(.*?)\}", src, _re.S)
    assert m, "preserved_keys block not found"
    assert '"TRUSTED_HOSTS"' not in m.group(1)


def test_ensure_data_dirs_owner_only(monkeypatch, tmp_path):
    import stat as _stat

    monkeypatch.chdir(tmp_path)
    inst._ensure_data_dirs()
    for d in ("models", "corpus_data", "audit_exports", "backups"):
        st = os.stat(d)
        assert _stat.S_IMODE(st.st_mode) == 0o700, d


def test_check_resources_never_raises():
    inst._check_resources("gemma4:e2b")
    inst._check_resources("gemma4:e4b")


def test_piserve_unit_points_at_repo_and_hardens():
    from pathlib import Path

    unit = inst._render_piserve_unit(
        "user", "/home/user", "/usr/bin/python3",
        Path("/home/user/piSynapse/litert_serve/server.py"),
    )
    assert "ExecStart=/usr/bin/python3 /home/user/piSynapse/litert_serve/server.py" in unit
    assert "WorkingDirectory=/home/user/piSynapse/litert_serve" in unit
    assert "UMask=0077" in unit
    assert "EnvironmentFile=-/home/user/piSynapse/.env" in unit
    assert "litert.service" not in unit
    assert "/home/user/litert_serve" not in unit  # orphan path never served


def test_pisynapse_unit_orders_after_piserve():
    unit = inst._render_pisynapse_unit(
        "user", "/home/user/piSynapse",
        "/home/user/piSynapse/venv/bin/uvicorn", wants_litert=True,
    )
    assert "After=network-online.target piserve.service" in unit
    assert "WorkingDirectory=/home/user/piSynapse" in unit
    assert "UMask=0077" in unit
    # Dead legacy name must never appear as a dependency.
    assert " litert.service" not in unit


def test_pisynapse_unit_without_litert_has_no_piserve_dep():
    unit = inst._render_pisynapse_unit(
        "user", "/home/user/piSynapse",
        "/home/user/piSynapse/venv/bin/uvicorn", wants_litert=False,
    )
    assert "piserve.service" not in unit


def test_run_enforces_default_timeout(monkeypatch):
    """Downloads must not hang forever: _run injects a hard timeout."""
    seen = {}

    class R:
        returncode = 0

    def fake_run(cmd, **kw):
        seen.update(kw)
        return R()

    monkeypatch.setattr(inst.subprocess, "run", fake_run)
    inst._run(["echo", "hi"])
    assert seen.get("timeout") == inst._STEP_TIMEOUT


def test_run_respects_explicit_timeout(monkeypatch):
    seen = {}

    class R:
        returncode = 0

    def fake_run(cmd, **kw):
        seen.update(kw)
        return R()

    monkeypatch.setattr(inst.subprocess, "run", fake_run)
    inst._run(["echo"], timeout=5)
    assert seen["timeout"] == 5


def test_sudo_prefix_dash_n_only_in_batch(monkeypatch):
    monkeypatch.setattr(inst, "BATCH_MODE", True)
    assert inst._sudo_prefix() == ["sudo", "-n"]
    monkeypatch.setattr(inst, "BATCH_MODE", False)
    assert inst._sudo_prefix() == ["sudo"]


def test_check_sudo_batch_warns_when_unavailable(monkeypatch):
    log = []

    class R:
        returncode = 1

    monkeypatch.setattr(inst, "BATCH_MODE", True)
    monkeypatch.setattr(inst.subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr(inst, "warn", lambda m: log.append(m))
    inst._check_sudo_batch()
    assert any("passwordless sudo" in m for m in log)


def test_check_sudo_batch_silent_when_interactive(monkeypatch):
    log = []
    monkeypatch.setattr(inst, "BATCH_MODE", False)
    monkeypatch.setattr(inst, "warn", lambda m: log.append(m))
    inst._check_sudo_batch()
    assert log == []


def test_generated_creds_key_is_valid_fernet():
    from cryptography.fernet import Fernet
    key = inst._generate_creds_key()
    Fernet(key.encode("utf-8"))  # raises if not a valid Fernet key


def test_creds_key_fallback_without_cryptography(monkeypatch):
    from cryptography.fernet import Fernet
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ImportError("simulated missing cryptography")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    key = inst._generate_creds_key()
    Fernet(key.encode("utf-8"))  # the fallback key must still be Fernet-valid


def test_report_missing_deps_all_present(monkeypatch):
    log = []
    monkeypatch.setattr(inst, "ok", lambda m: log.append(("ok", m)))
    inst._report_missing_deps([])
    assert log == [("ok", "All system dependencies satisfied")]


def test_report_missing_deps_summarizes_and_can_abort(monkeypatch):
    import types

    log = []
    monkeypatch.setattr(inst, "DISTRO", types.SimpleNamespace(pm="apt"))
    monkeypatch.setattr(inst, "BATCH_MODE", False)
    monkeypatch.setattr(inst, "warn", lambda m: log.append(("warn", m)))
    monkeypatch.setattr(inst, "info", lambda m: log.append(("info", m)))
    monkeypatch.setattr(inst, "error", lambda m: log.append(("error", m)))
    monkeypatch.setattr(inst, "ask_yesno", lambda p, default=True: False)  # user says no

    import pytest

    with pytest.raises(SystemExit):
        inst._report_missing_deps(["ffmpeg", "curl"])
    warns = [m for k, m in log if k == "warn"]
    infos = [m for k, m in log if k == "info"]
    assert any("ffmpeg" in m and "curl" in m for m in warns)
    assert any("sudo apt install ffmpeg curl" in m for m in infos)


def test_report_missing_deps_continues_when_user_agrees(monkeypatch):
    import types

    monkeypatch.setattr(inst, "DISTRO", types.SimpleNamespace(pm="apt"))
    monkeypatch.setattr(inst, "BATCH_MODE", False)
    monkeypatch.setattr(inst, "warn", lambda m: None)
    monkeypatch.setattr(inst, "info", lambda m: None)
    monkeypatch.setattr(inst, "ask_yesno", lambda p, default=True: True)  # continue
    inst._report_missing_deps(["ffmpeg"])  # must NOT exit


def test_report_missing_deps_batch_never_prompts(monkeypatch):
    monkeypatch.setattr(inst, "BATCH_MODE", True)
    monkeypatch.setattr(inst, "warn", lambda m: None)
    monkeypatch.setattr(inst, "info", lambda m: None)

    def _boom(*a, **k):
        raise AssertionError("batch must not prompt")

    monkeypatch.setattr(inst, "ask_yesno", _boom)
    inst._report_missing_deps(["curl"])  # no prompt, no exit


def test_find_litert_bin_expands_glob_in_dir_component(tmp_path, monkeypatch):
    """The '~/Library/Python/3.*/bin' candidate must actually match — the old
    code globbed only the filename inside a literal '*' directory (dead code)."""
    home = tmp_path / "home"
    bindir = home / "Library" / "Python" / "3.12" / "bin"
    bindir.mkdir(parents=True)
    exe = bindir / "litert-lm"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o755)

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(inst.shutil, "which", lambda name: None)
    assert inst._find_litert_bin() == str(exe)


def test_merge_env_extras_preserves_manual_keys():
    content = "API_KEY=abc\nLLM_MODEL=x\n"
    current = {"API_KEY": "abc", "CUSTOM_THING": "1", "ANOTHER": "2"}
    out, extras = inst._merge_env_extras(content, current)
    assert extras == {"CUSTOM_THING": "1", "ANOTHER": "2"}
    assert "CUSTOM_THING=1" in out and "ANOTHER=2" in out
    assert out.count("API_KEY=") == 1  # managed key not duplicated


def test_merge_env_extras_no_manual_keys():
    out, extras = inst._merge_env_extras("A=1\nB=2\n", {"A": "1", "B": "2"})
    assert extras == {}
    assert out == "A=1\nB=2\n"


# ── pure decision functions (R3, 2026-11-16) ────────────────────────────────

def test_fill_template_substitutes_and_preserves_literal_braces():
    # User-supplied values containing braces must not be re-interpreted
    # (unlike str.format, which would raise or mangle them).
    out = inst._fill_template("key={KEY} val={VAL}", {"KEY": "k", "VAL": "{literal}"})
    assert out == "key=k val={literal}"
    # Unknown placeholders are left untouched.
    assert inst._fill_template("x={MISSING}", {}) == "x={MISSING}"


def test_read_current_env_parses_and_ignores_comments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "# comment\n\nAPI_KEY=secret\nEMPTY=\nBADLINE\nFOO=bar=baz\n", encoding="utf-8"
    )
    assert inst._read_current_env() == {"API_KEY": "secret", "EMPTY": "", "FOO": "bar=baz"}


def test_read_current_env_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert inst._read_current_env() == {}


def test_detect_shell_and_activation_cmd_consistent(monkeypatch):
    monkeypatch.setattr(inst, "IS_WIN", False)
    for shell_name, env_val in (("bash", "/bin/bash"), ("zsh", "/usr/bin/zsh"),
                                ("fish", "/usr/bin/fish")):
        monkeypatch.setenv("SHELL", env_val)
        assert inst.detect_shell() == shell_name
        cmd = inst.activation_cmd(shell_name)
        assert shell_name.split("s")[0] in cmd or "activate" in cmd
    monkeypatch.setenv("SHELL", "")
    assert inst.detect_shell() == "unknown"
    assert "activate" in inst.activation_cmd("unknown")


def test_model_dash_id_replaces_colon_with_dash(monkeypatch):
    monkeypatch.setattr(inst, "STATE", {"model": "gemma4:e2b"})
    assert inst._model_dash_id() == "gemma4-e2b"
    monkeypatch.setattr(inst, "STATE", {"model": "gemma4-e4b"})
    assert inst._model_dash_id() == "gemma4-e4b"
    monkeypatch.setattr(inst, "STATE", {})
    assert inst._model_dash_id() == "gemma4-e2b"  # default


def test_venv_bin_points_at_venv_layout(monkeypatch):
    monkeypatch.setattr(inst, "IS_WIN", False)
    monkeypatch.setattr(inst, "VENV_DIR", "/opt/venv")
    assert inst.venv_bin("python") == "/opt/venv/bin/python"


def test_users_table_empty_reflects_db_state(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / "assistant.db"
    monkeypatch.setattr(inst, "_users_table_empty", inst._users_table_empty)
    # No DB file yet → treated as empty (fresh install path).
    # Call the real helper against a temp DB by monkeypatching its db_path arg usage.
    # _users_table_empty takes db_path; exercise both empty and populated.
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE users (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()
    assert inst._users_table_empty(str(db)) is True
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO users (id) VALUES ('u1')")
    conn.commit()
    conn.close()
    assert inst._users_table_empty(str(db)) is False
    # Missing table / missing file → empty (no crash), so a fresh install proceeds.
    missing = tmp_path / "nope.db"
    assert inst._users_table_empty(str(missing)) is True

