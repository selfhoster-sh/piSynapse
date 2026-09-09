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
        "salih", "/home/salih", "/usr/bin/python3",
        Path("/home/salih/piSynapse/litert_serve/server.py"),
    )
    assert "ExecStart=/usr/bin/python3 /home/salih/piSynapse/litert_serve/server.py" in unit
    assert "WorkingDirectory=/home/salih/piSynapse/litert_serve" in unit
    assert "UMask=0077" in unit
    assert "EnvironmentFile=-/home/salih/piSynapse/.env" in unit
    assert "litert.service" not in unit
    assert "/home/salih/litert_serve" not in unit  # orphan path never served


def test_pisynapse_unit_orders_after_piserve():
    unit = inst._render_pisynapse_unit(
        "salih", "/home/salih/piSynapse",
        "/home/salih/piSynapse/venv/bin/uvicorn", wants_litert=True,
    )
    assert "After=network-online.target piserve.service" in unit
    assert "WorkingDirectory=/home/salih/piSynapse" in unit
    assert "UMask=0077" in unit
    # Dead legacy name must never appear as a dependency.
    assert " litert.service" not in unit


def test_pisynapse_unit_without_litert_has_no_piserve_dep():
    unit = inst._render_pisynapse_unit(
        "salih", "/home/salih/piSynapse",
        "/home/salih/piSynapse/venv/bin/uvicorn", wants_litert=False,
    )
    assert "piserve.service" not in unit
