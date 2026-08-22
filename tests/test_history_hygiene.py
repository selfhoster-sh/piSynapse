"""History-hygiene regression tests (2026-08-22 self-poisoning incident).

Leaked tool-call text must never reach the conversations table as an
assistant reply — the model imitates its own leaked syntax from history.
"""

import routers.chat as rc


def test_clean_assistant_reply_drops_pure_leak():
    assert rc._clean_assistant_reply("<|tool_call>call:list_notes{{}}<tool_call|>") == ""
    assert rc._clean_assistant_reply("<|tool_call|>call:read_email{id:5}<tool_call|>") == ""


def test_clean_assistant_reply_keeps_surrounding_text():
    assert rc._clean_assistant_reply("Merhaba <|tool_call|>call:read_email{id:5}<tool_call|> dünya") == "Merhaba dünya"


def test_clean_assistant_reply_strips_prefix():
    assert rc._clean_assistant_reply("piSynapse: normal cevap") == "normal cevap"


def test_clean_assistant_reply_handles_empty_and_none():
    assert rc._clean_assistant_reply("") == ""
    assert rc._clean_assistant_reply(None) == ""
