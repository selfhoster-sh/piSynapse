"""SSE keepalive: idle gaps emit `: ping` comments, streams survive."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def stream_client(tmp_path, monkeypatch):
    import db as dbmod

    monkeypatch.setattr(dbmod, "DB_PATH", str(tmp_path / "k.db"))
    asyncio.run(dbmod.close_db())
    asyncio.run(dbmod.init_db())
    import routers.chat as rc

    async def _slow_stream(*a, **k):
        await asyncio.sleep(0.25)
        yield {"token": "hi"}
        yield {"done": True, "memories_saved": 0}

    async def _fake_embed(message):
        return b"fake"

    async def _fake_embed_async(*a, **k):
        return b"fake"

    async def _fake_intent(message, query_embedding=None):
        return ("question", "notes")

    monkeypatch.setattr(rc, "chat_with_ollama_stream", _slow_stream)
    monkeypatch.setattr(rc, "_shared_query_embedding", _fake_embed)
    monkeypatch.setattr(rc, "KEEPALIVE_S", 0.05)
    import embedding as embmod

    # The endpoint path re-embeds via search_memories regardless of the
    # passed vector — stub the model (no weights in CI, slow download live).
    monkeypatch.setattr(embmod, "embed_async", _fake_embed_async)
    monkeypatch.setattr(embmod, "embed_batch_async", _fake_embed_async)
    import llm as llmm

    monkeypatch.setattr(llmm, "_classify_intent", _fake_intent)

    app = FastAPI()
    app.include_router(rc.router)
    client = TestClient(app, base_url="http://localhost")
    yield client
    asyncio.run(dbmod.close_db())


def test_idle_gap_emits_ping_and_stream_completes(stream_client):
    r = stream_client.post("/chat/stream", json={"message": "hi", "session_id": "s1"})
    assert r.status_code == 200
    body = r.content
    assert b": ping" in body  # keepalive fired during the 0.25s gap
    assert b'"hi"' in body  # token survived the wait (no truncation)
    assert b'"done": true' in body  # terminal event intact


def test_fast_stream_has_no_ping(stream_client, monkeypatch):
    import routers.chat as rc

    async def _fast_stream(*a, **k):
        yield {"token": "yo"}
        yield {"done": True, "memories_saved": 0}

    monkeypatch.setattr(rc, "chat_with_ollama_stream", _fast_stream)
    r = stream_client.post("/chat/stream", json={"message": "hi", "session_id": "s2"})
    assert r.status_code == 200
    assert b": ping" not in r.content
    assert b'"yo"' in r.content
