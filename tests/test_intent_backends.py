"""Intent classification pipeline across both backends.

Layers: FastEmbed embedding (backend-agnostic, local ONNX) -> keyword
heuristics -> optional LLM fallback (branches litert vs ollama).
"""

import asyncio

import numpy as np

import llm.intent as li


def _vec(*vals):
    return np.array(vals, dtype=np.float32).tobytes()


class _Resp:
    def raise_for_status(self):
        return None

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


class _IntentClient:
    def __init__(self, body=None, fail=False):
        self.body = body or {}
        self.fail = fail
        self.posts = []

    async def post(self, url, json=None):
        self.posts.append((url, json))
        if self.fail:
            raise RuntimeError("backend down")
        return _Resp(self.body)


def _patch_cfg(monkeypatch, *, backend="litert", llm_fallback="off"):
    def fake_get(key, default=None):
        if key == "LLM_BACKEND":
            return backend
        if key == "INTENT_LLM_FALLBACK":
            return llm_fallback
        if key == "LLM_MODEL":
            return "gemma4-e2b"
        if key == "LLM_KEEP_ALIVE":
            return "4h"
        return default

    monkeypatch.setattr(li, "get", fake_get)


def test_embedding_hit_routes_action_without_llm(monkeypatch):
    v_notes, v_weather = _vec(1, 0, 0), _vec(0, 1, 0)

    async def fake_corpus():
        return [("notes", "notes desc", v_notes), ("weather", "w desc", v_weather)]

    async def fake_embed(text):
        return v_notes

    monkeypatch.setattr(li, "_get_tool_embeddings", fake_corpus)
    import embedding as emb_mod
    monkeypatch.setattr(emb_mod, "embed_async", fake_embed)
    _patch_cfg(monkeypatch)

    intent, group = asyncio.run(li._classify_intent("notlarımı listele"))
    assert (intent, group) == ("action", "notes")


def test_keyword_path_when_corpus_empty(monkeypatch):
    monkeypatch.setattr(li, "_tool_embed_cache", [])
    _patch_cfg(monkeypatch, llm_fallback="off")

    intent, group = asyncio.run(li._classify_intent("yarın için hava tahmini"))
    assert (intent, group) == ("action", "weather")


def test_keyword_group_english_routing():
    cases = {
        "set up a meeting for tomorrow": "calendar",
        "add an event to my calendar": "calendar",
        "what is the weather forecast in berlin": "weather",
        "today's temperature": "weather",
        "add buy milk to my to-do list": "tasks",
        "complete the report assignment": "tasks",
        "send an email to alice": "email",
        "write down a note for me": "notes",
        "please remember my wifi password": "memory",
    }
    for msg, expected in cases.items():
        assert li._keyword_group(msg) == expected, f"{msg!r} -> {expected}"


def test_keyword_group_english_does_not_collide_negation():
    # Bare english "not" must NOT route a negation into the notes group.
    assert li._keyword_group("i could not find the file") is None


def test_llm_fallback_litert_branch(monkeypatch):
    monkeypatch.setattr(li, "_tool_embed_cache", [])
    _patch_cfg(monkeypatch, backend="litert", llm_fallback="on")
    client = _IntentClient(body={"choices": [{"message": {"content": "Notes"}}]})
    monkeypatch.setattr(li, "_get_client", lambda: client)

    intent, group = asyncio.run(li._classify_intent("bana bir şarkı önerir misin"))

    assert (intent, group) == ("action", "notes")
    url, payload = client.posts[0]
    assert url.endswith("/v1/chat/completions")
    assert payload["max_completion_tokens"] == 20


def test_llm_fallback_ollama_branch(monkeypatch):
    monkeypatch.setattr(li, "_tool_embed_cache", [])
    _patch_cfg(monkeypatch, backend="ollama", llm_fallback="on")
    client = _IntentClient(body={"message": {"content": "question"}})
    monkeypatch.setattr(li, "_get_client", lambda: client)

    intent, group = asyncio.run(li._classify_intent("bana bir şarkı önerir misin"))

    assert (intent, group) == ("question", None)
    url, payload = client.posts[0]
    assert url.endswith("/api/chat")
    assert payload["options"]["num_predict"] == 20
    assert "keep_alive" in payload


def test_llm_fallback_failure_defaults_to_question(monkeypatch):
    monkeypatch.setattr(li, "_tool_embed_cache", [])
    _patch_cfg(monkeypatch, backend="litert", llm_fallback="on")
    client = _IntentClient(fail=True)
    monkeypatch.setattr(li, "_get_client", lambda: client)

    intent, group = asyncio.run(li._classify_intent("bana bir şarkı önerir misin"))
    assert (intent, group) == ("question", None)
