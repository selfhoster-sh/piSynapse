"""Tests for semantic history retrieval (lost-in-the-middle mitigation)."""

import asyncio

import numpy as np

import embedding
import retrieval
from retrieval import merge_history, retrieve_relevant_history, split_recent


def _vec(*vals) -> bytes:
    return np.array(vals, dtype="float32").tobytes()


def test_split_recent_short_history_keeps_all():
    hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    recent, older = split_recent(hist, recent_window=8)
    assert recent == hist
    assert older == []


def test_split_recent_splits_verbatim_and_candidates():
    hist = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    recent, older = split_recent(hist, recent_window=8)
    assert [m["content"] for m in older] == [f"m{i}" for i in range(2)]
    assert [m["content"] for m in recent] == [f"m{i}" for i in range(2, 10)]


def test_merge_history_replaces_older_part_with_retrieved():
    hist = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    retrieved = [{"role": "assistant", "content": "relevant"}]
    merged = merge_history(hist, retrieved, recent_window=8)
    assert [m["content"] for m in merged] == ["relevant"] + [f"m{i}" for i in range(2, 10)]


def test_merge_history_falls_back_when_nothing_retrieved():
    hist = [{"role": "user", "content": f"m{i}"} for i in range(10)]
    assert merge_history(hist, []) is hist


def test_retrieve_keeps_most_relevant_in_chronological_order(monkeypatch):
    candidates = [
        {"role": "user", "content": "c1", "timestamp": "2026-08-01 10:00"},
        {"role": "assistant", "content": "c2", "timestamp": "2026-08-01 11:00"},
        {"role": "user", "content": "c3", "timestamp": "2026-08-01 12:00"},
        {"role": "user", "content": "c4", "timestamp": "2026-08-01 09:00"},
    ]
    query_vec = _vec(1, 0, 0, 0)
    vecs = [_vec(0, 1, 0, 0), _vec(1, 0, 0, 0), _vec(0, 0, 1, 0), _vec(0.6, 0.8, 0, 0)]

    async def fake_fetch(session_id, recent_window=8):
        return candidates

    async def fake_embed(texts):
        assert texts[0] == "query"
        return [query_vec] + vecs

    monkeypatch.setattr(retrieval, "_fetch_candidates", fake_fetch)
    monkeypatch.setattr(embedding, "embed_batch_async", fake_embed)

    picked, stats = asyncio.run(retrieve_relevant_history("s1", "query", top_k=2, threshold=0.4))

    assert [m["content"] for m in picked] == ["c4", "c2"]
    assert stats["candidates"] == 4
    assert stats["retrieved"] == 2
    assert stats["latency_ms"] >= 0


def test_retrieve_threshold_filters_low_similarity(monkeypatch):
    candidates = [
        {"role": "user", "content": "c1", "timestamp": "2026-08-01 10:00"},
        {"role": "user", "content": "c2", "timestamp": "2026-08-01 11:00"},
    ]
    query_vec = _vec(1, 0)
    vecs = [_vec(0, 1), _vec(1, 0)]

    async def fake_fetch(session_id, recent_window=8):
        return candidates

    async def fake_embed(texts):
        return [query_vec] + vecs

    monkeypatch.setattr(retrieval, "_fetch_candidates", fake_fetch)
    monkeypatch.setattr(embedding, "embed_batch_async", fake_embed)

    picked, stats = asyncio.run(retrieve_relevant_history("s1", "query", top_k=5, threshold=0.9))

    assert [m["content"] for m in picked] == ["c2"]
    assert stats["retrieved"] == 1


def test_retrieve_falls_back_when_embedding_fails(monkeypatch):
    async def fake_fetch(session_id, recent_window=8):
        return [{"role": "user", "content": "c1", "timestamp": "2026-08-01 10:00"}]

    async def raiser(texts):
        raise RuntimeError("onnx boom")

    monkeypatch.setattr(retrieval, "_fetch_candidates", fake_fetch)
    monkeypatch.setattr(embedding, "embed_batch_async", raiser)

    picked, stats = asyncio.run(retrieve_relevant_history("s1", "query"))
    assert picked == []
    assert stats["retrieved"] == 0


def test_retrieve_empty_query_skips_candidates(monkeypatch):
    async def boom(session_id, recent_window=8):
        raise AssertionError("must not hit DB for empty query")

    monkeypatch.setattr(retrieval, "_fetch_candidates", boom)

    picked, stats = asyncio.run(retrieve_relevant_history("s1", "   "))
    assert picked == []
    assert stats["candidates"] == 0


def test_retrieve_timeout_falls_back_when_budget_exceeded(monkeypatch):
    async def slow_embed(texts):
        await asyncio.sleep(5)
        return []

    async def fake_fetch(session_id, recent_window=8):
        return [{"role": "user", "content": "c1", "timestamp": "2026-08-01 10:00"}]

    monkeypatch.setattr(retrieval, "_fetch_candidates", fake_fetch)
    monkeypatch.setattr(embedding, "embed_batch_async", slow_embed)

    picked, stats = asyncio.run(retrieve_relevant_history("s1", "query", time_budget_ms=100))
    assert picked == []
    assert stats["timeout"] is True


def test_retrieve_reuses_precomputed_query_embedding(monkeypatch):
    candidates = [
        {"role": "user", "content": "c1", "timestamp": "2026-08-01 10:00"},
        {"role": "user", "content": "c2", "timestamp": "2026-08-01 11:00"},
    ]
    query_vec = _vec(1, 0)
    vecs = [_vec(0, 1), _vec(1, 0)]

    embedded: list[list[str]] = []

    async def fake_fetch(session_id, recent_window=8):
        return candidates

    async def fake_embed(texts):
        embedded.append(texts)
        return vecs

    monkeypatch.setattr(retrieval, "_fetch_candidates", fake_fetch)
    monkeypatch.setattr(embedding, "embed_batch_async", fake_embed)

    picked, stats = asyncio.run(
        retrieve_relevant_history("s1", "query", query_embedding=query_vec, top_k=2, threshold=0.1)
    )
    assert [m["content"] for m in picked] == ["c2"]
    # The query must not be embedded again — only the candidates are batched.
    assert embedded == [["c1", "c2"]]
