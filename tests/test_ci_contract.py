"""CI contract (analysis B3/B6/Y18): reproducible, version-aware, audited.

Guards against CI drifting back to floating installs, a single Python
version (a Py3.12-only sqlite3 rowcount regression once slipped through a
3.11-only CI), or a dropped dependency audit.
"""
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _ci() -> str:
    with open(os.path.join(ROOT, ".github/workflows/ci.yml"), encoding="utf-8") as f:
        return f.read()


def test_ci_installs_from_the_pinned_lock():
    ci = _ci()
    assert "pip install -r requirements-lock.txt" in ci
    assert "pip install -r requirements.txt" not in ci, (
        "CI must use the pinned lock, not the floating requirements file"
    )


def test_ci_tests_both_python_versions():
    ci = _ci()
    assert '"3.11"' in ci and '"3.12"' in ci, (
        "CI must run the Pi target (3.11) AND current dev (3.12) — "
        "version-specific bugs are real (sqlite3 rowcount on 3.12)"
    )


def test_ci_runs_dependency_audit():
    assert "pip-audit" in _ci()
