"""ui.js hygiene guards (analysis C9/C9b — the safe subset of the i18n pass).

Two footguns removed:
- a local `const t = setTimeout(...)` shadowed the global i18n `t()` in
  renderSessions' touch handler — harmless today (no t() call in that scope)
  but a latent trap the moment someone translates a string there;
- `optsArr = '|'.repeat(0) + optsArr` was a literal no-op ("keep parity"
  placeholder) left in the option-normalization path.

C1/C2 (hardcoded literals -> STRINGS) and C10 (dead STRINGS keys) are NOT
covered here: they need a browser and a reliable usage oracle — deferred.
"""
import os
import re

ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(name: str) -> str:
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


def test_local_t_does_not_shadow_i18n_t():
    ui = _read("static/ui.js")
    assert not re.search(r"\b(const|let|var)\s+t\s*=\s*setTimeout", ui), (
        "a local `t` shadows the i18n t() function — rename it (e.g. tid)"
    )


def test_no_noop_repeat_zero():
    ui = _read("static/ui.js")
    assert "'|'.repeat(0)" not in ui
    assert ".repeat(0)" not in ui
