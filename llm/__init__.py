"""LLM package: intent classification, streaming, payload building, and summarization."""
from .chat import SUMMARY_SYSTEM_PROMPT, _llm_request, chat_with_ollama, summarize_conversation
from .intent import (
    _classify_intent,
    contextual_email_followup,
    is_contextual_followup,
    llm_resolve_with_evidence,
    resolve_resume_context,
)
from .payload import _build_full_messages, _build_payload, _normalize_messages_for_backend
from .stream import EARLY_BUFFER_CHARS, chat_with_ollama_stream
from .utils import strip_prefix

__all__ = [
    "chat_with_ollama",
    "chat_with_ollama_stream",
    "summarize_conversation",
    "strip_prefix",
    "_classify_intent",
    "contextual_email_followup",
    "is_contextual_followup",
    "resolve_resume_context",
    "llm_resolve_with_evidence",
    "_build_payload",
    "_build_full_messages",
    "_normalize_messages_for_backend",
    "_llm_request",
    "SUMMARY_SYSTEM_PROMPT",
    "EARLY_BUFFER_CHARS",
]
