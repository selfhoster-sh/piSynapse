"""Embedding circuit breaker: failed weight downloads fail fast, never hang chats."""
import time

import embedding as embmod


def test_breaker_fast_fails_after_error(monkeypatch):
    monkeypatch.setattr(embmod, "_model", None)
    monkeypatch.setattr(embmod, "_model_error_ts", time.time())
    t0 = time.time()
    try:
        embmod.get_model()
        raise AssertionError("should raise while in cooldown")
    except RuntimeError:
        pass
    assert time.time() - t0 < 5


def test_breaker_retries_after_cooldown(monkeypatch):
    calls = []

    class FakeModel:
        pass

    monkeypatch.setattr(embmod, "TextEmbedding", lambda **k: calls.append(1) or FakeModel())
    monkeypatch.setattr(embmod, "_model", None)
    monkeypatch.setattr(embmod, "_model_error_ts", time.time() - 700)
    assert embmod.get_model() is not None
    assert calls == [1]
