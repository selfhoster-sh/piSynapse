"""Packaging metadata stays complete (analysis A/B: `pip install .` ImportError).

pyproject's setuptools lists drifted: modules the app imports (auth,
credstore, retrieval, title, textnorm, messages, tool_verification) were
missing from py-modules, and two runtime deps (bcrypt, cryptography) were
missing from dependencies — `pip install .` produced an incomplete package.
These guards keep the list honest.
"""
import glob
import os

import tomllib

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _pyproject() -> dict:
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def _dep_names(lines) -> set:
    names = set()
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        names.add(ln.split(">=")[0].split("==")[0].split("[")[0].strip().lower())
    return names


def test_every_top_level_module_is_packaged():
    mods = {os.path.basename(p)[:-3] for p in glob.glob(os.path.join(ROOT, "*.py"))}
    listed = set(_pyproject()["tool"]["setuptools"]["py-modules"])
    missing = mods - listed
    extra = listed - mods
    assert not missing, f"top-level modules not packaged: {sorted(missing)}"
    assert not extra, f"py-modules lists non-existent modules: {sorted(extra)}"


def test_dependencies_cover_requirements_txt():
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        req = _dep_names(f.readlines())
    deps = _dep_names(_pyproject()["project"]["dependencies"])
    missing = req - deps
    assert not missing, f"runtime deps missing from pyproject: {sorted(missing)}"
