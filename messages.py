"""User-facing message catalog with instance-level localization.

Backend-generated replies that land in chat history (fallbacks, engine
errors) are picked from here using the UI_LANGUAGE setting so a single
self-hosted instance speaks its owner's language consistently.

Model-facing prompts are intentionally NOT localized — small models follow
English instructions best and users never see them (see llm/utils.py).
"""

import contextvars

from config import get

# Per-request language override (multi-user): the chat pipeline resolves the
# caller's effective UI_LANGUAGE once per request and pins it here, so sync
# helpers deep in the call tree speak the right language without threading
# a parameter through every signature. Falls back to the global setting.
# Context-local: never leaks across requests (or into unrelated code).
_request_lang: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "piSynapse_request_lang", default=None
)


def set_request_language(lang: str | None) -> None:
    """Pin the UI language for the current request context (or clear it)."""
    _request_lang.set((lang or "").strip().lower() or None)

_MESSAGES = {
    # Loop guard: finalize round still produced nothing (llm/utils.py).
    "llm_empty_reply": {
        "tr": "İşlem tamamlandı ancak özet oluşturulamadı. Lütfen isteğini tekrar dener misin?",
        "en": "Done, but I couldn't generate a summary. Could you try asking again?",
    },
    # Non-stream engine connection failure.
    "llm_unreachable": {
        "tr": "Motorla bağlantı kurulamadı. Lütfen tekrar deneyin.",
        "en": "Couldn't reach the engine. Please try again.",
    },
    # Non-stream engine returned an empty response.
    "llm_empty_response": {
        "tr": "Motor boş yanıt döndürdü. Lütfen tekrar deneyin.",
        "en": "The engine returned an empty response. Please try again.",
    },
}


def get_message(key: str) -> str:
    """Return ``key`` in the request's UI_LANGUAGE (default English)."""
    lang = _request_lang.get() or str(get("UI_LANGUAGE", "en") or "en").strip().lower()
    entry = _MESSAGES.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry["en"]
