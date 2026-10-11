"""Playwright must never touch the live database (test-DB isolation rule).

NOTES 2026-09-09 incident: a full-suite run once wrote a test admin row
into the live assistant.db. The playwright webServer used to boot the
real app with the repo-root assistant.db (and reuseExistingServer: true
could even attach to the dev/systemd instance running it). The config
now starts a self-contained server: dedicated port, throwaway per-run
DB under tmpdir, never reusing an existing instance.

Node is not available in every dev environment, so this is a
source-contract test (test_install_template pattern) — the suite itself
must still be run where Node exists (Pi / dev machine).
"""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_playwright_server_boots_isolated():
    cfg = _read("playwright.config.js")
    assert "reuseExistingServer: false" in cfg, (
        "e2e must never attach to a dev/systemd instance — those run the live DB"
    )
    assert "DB_PATH" in cfg and "tmpdir" in cfg, (
        "the e2e server must boot with a throwaway DB under tmpdir"
    )
    # Per-run uniqueness (no stale state / cross-run bleed).
    assert re.search(r"pisynapse-e2e-.?\{?process\.pid\}?", cfg) or "process.pid" in cfg
    # Never the live database literal.
    assert "assistant.db" not in cfg


def test_playwright_port_dedicated():
    cfg = _read("playwright.config.js")
    m = re.search(r"const E2E_PORT = (\d+)", cfg)
    assert m, "E2E_PORT constant not found"
    assert m.group(1) != "8765", (
        "e2e must not share the dev-service port — a running dev instance "
        "would conflict with (or be mistaken for) the isolated e2e server"
    )
    # baseURL and webServer must both use the constant, not literals.
    assert cfg.count("${E2E_PORT}") >= 2
