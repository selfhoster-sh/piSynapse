"""User-facing message catalog with instance-level localization.

Backend-generated replies that land in chat history (fallbacks, engine
errors) are picked from here using the UI_LANGUAGE setting so a single
self-hosted instance speaks its owner's language consistently.

Model-facing prompts are intentionally NOT localized — small models follow
English instructions best and users never see them (see llm/utils.py).
"""

from config import get

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
    """Return ``key`` in the instance's UI_LANGUAGE (default Turkish)."""
    lang = str(get("UI_LANGUAGE", "tr") or "tr").strip().lower()
    entry = _MESSAGES.get(key)
    if not entry:
        return key
    return entry.get(lang) or entry["tr"]
