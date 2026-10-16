"""install.py model pre-download: retry + visible cause (analysis D2).

The old single silent attempt gave the user only "failed" — no reason, no
retry. New behaviour: 2 attempts, the stderr tail is shown, and the exact
command to redo it later is printed; a failure never blocks the install.
"""
import types

import install as inst


def _patch(monkeypatch, outcomes, log):
    seq = list(outcomes)

    def fake_run(*a, **k):
        nxt = seq.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt

    monkeypatch.setattr(inst.subprocess, "run", fake_run)
    monkeypatch.setattr(inst, "venv_bin", lambda name: "/fake/python")
    monkeypatch.setattr(inst.time, "sleep", lambda _s: None)
    monkeypatch.setattr(inst, "ok", lambda m: log.append(("ok", m)))
    monkeypatch.setattr(inst, "warn", lambda m: log.append(("warn", m)))
    monkeypatch.setattr(inst, "info", lambda m: log.append(("info", m)))


def _res(code, stderr=""):
    return types.SimpleNamespace(returncode=code, stderr=stderr)


def test_success_first_try(monkeypatch):
    log = []
    _patch(monkeypatch, [_res(0)], log)
    assert inst._predownload_one("Embedding", "print(1)") is True
    assert ("ok", "Embedding ready") in log
    assert not any(k == "warn" for k, _ in log)


def test_retries_once_then_succeeds(monkeypatch):
    log = []
    # first fails, second succeeds
    _patch(monkeypatch, [_res(1, "connection reset\nlast line error"), _res(0)], log)
    assert inst._predownload_one("Whisper", "print(1)") is True
    warns = [m for k, m in log if k == "warn"]
    assert any("attempt 1/2" in m and "last line error" in m for m in warns)


def test_two_failures_give_up_with_manual_command(monkeypatch):
    log = []
    _patch(monkeypatch, [_res(2, "boom"), _res(2, "boom again")], log)
    assert inst._predownload_one("Embedding", "x = 1") is False
    assert sum(1 for k, _ in log if k == "warn") == 2
    infos = [m for k, m in log if k == "info"]
    assert infos and "/fake/python" in infos[0] and "x = 1" in infos[0]


def test_timeout_is_handled_and_retried(monkeypatch):
    log = []
    _patch(monkeypatch, [inst.subprocess.TimeoutExpired("cmd", 1200), _res(0)], log)
    assert inst._predownload_one("Embedding", "y = 2") is True
    assert any("timed out" in m for k, m in log if k == "warn")
