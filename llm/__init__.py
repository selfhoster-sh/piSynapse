"""LLM package: intent classification, streaming, payload building, and summarization."""
from .chat import SUMMARY_SYSTEM_PROMPT, _llm_request, chat_with_ollama, summarize_conversation
from .intent import (
    _INTENT_PROMPT,
    _TOOL_EMBED_CORPUS,
    _classify_intent,
    _get_tool_embeddings,
    _tool_embed_cache,
)
from .payload import _build_full_messages, _build_payload, _normalize_messages_for_backend
from .stream import EARLY_BUFFER_CHARS, chat_with_ollama_stream
from .utils import (
    _PREFIX_RE,
    _THINKING_STRIP_RE,
    _TOOL_CLEANUP_RE,
    _TOOL_LEAK_RE,
    _TOOL_NAMES_ALTERNATION,
    _check_tool_leak,
    _get_client,
    strip_prefix,
)

__all__ = [
    "chat_with_ollama",
    "chat_with_ollama_stream",
    "summarize_conversation",
    "strip_prefix",
    "_classify_intent",
    "_build_payload",
    "_build_full_messages",
    "_normalize_messages_for_backend",
    "_llm_request",
    "SUMMARY_SYSTEM_PROMPT",
    "EARLY_BUFFER_CHARS",
]
