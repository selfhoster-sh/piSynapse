"""Instance-level message localization (UI_LANGUAGE setting).

Backend user-facing strings must follow the instance language; model-facing
prompts stay English by design.
"""

import llm.utils as llm_utils
from messages import get_message


def test_default_language_is_turkish():
    assert get_message("llm_empty_reply") == llm_utils.EMPTY_ANSWER_FALLBACK
    assert get_message("llm_unreachable").startswith("Motorla")


def test_english_selected_via_setting(monkeypatch):
    monkeypatch.setattr("messages.get", lambda key, default=None: "en")
    assert get_message("llm_empty_reply") == (
        "Done, but I couldn't generate a summary. Could you try asking again?"
    )
    assert get_message("llm_unreachable") == "Couldn't reach the engine. Please try again."


def test_unknown_key_returns_key_itself():
    assert get_message("no_such_key") == "no_such_key"


def test_utils_fallback_helper_tracks_setting(monkeypatch):
    monkeypatch.setattr("messages.get", lambda key, default=None: "en")
    assert llm_utils.empty_answer_fallback().startswith("Done, but")
