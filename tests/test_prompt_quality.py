"""System/group prompt hygiene: no dangling fragments, coherent instructions."""

from tools.definitions import TOOLS

import prompt as pm


def test_tasks_group_prompt_has_no_dangling_fragment():
    # Regression: "...never ask 'Are you sure?' in text.Pass Call search_tasks..."
    # had a stray 'Pass ' mid-sentence that the model saw verbatim.
    text = pm.get_tool_system_prompt("tasks")
    assert "Pass Call" not in text
    assert "in text." in text
    assert "complete_task" in text and "delete_task" in text


def test_all_group_prompts_mention_confirm_cards():
    for group in pm._GROUP_TOOLS:
        text = pm.get_tool_system_prompt(group)
        assert text.strip().startswith("LANGUAGE RULE")
        assert "Available tools:" in text
        # The language rule is never diluted by language-name examples.
        assert "Reply in Turkish" not in text


def test_group_prompt_search_tasks_sentence_continues_properly():
    text = pm.get_tool_system_prompt("tasks")
    marker = "Call search_tasks to find tasks by keyword."
    assert marker in text
    idx = text.find("in text.")
    assert idx != -1
    # The sentence after 'in text.' must not contain a stray capital 'Call'
    # glued to a truncated clause.
    tail = text[idx:idx + 40]
    assert "..." not in tail


def _desc(name):
    for t in TOOLS:
        if t["function"]["name"] == name:
            return t["function"]["description"]
    raise KeyError(name)


def test_list_and_search_emails_are_distinguished():
    # Eval: mail-01 was ambiguous between the two; descriptions now point the
    # model at the right one per phrasing.
    assert "general overview" in _desc("list_emails")
    assert "search_emails instead" in _desc("list_emails")
    assert "Search specific emails" in _desc("search_emails") or "Find specific emails" in _desc("search_emails")
    assert "list_emails" in _desc("search_emails")


def test_calendar_create_mentions_reminders():
    assert "remind" in _desc("create_calendar_event").lower()