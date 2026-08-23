"""piSynapse System Prompt
Builds the system prompt and per-request context injection.
"""

from datetime import datetime

import config


# Small models ignore buried instructions — the language rule sits as a
# standalone directive at the very top of every system prompt variant.
# Deliberately NO language-name examples: small models latch onto a named
# language instead of generalizing the mirror rule.
LANGUAGE_RULE = (
    "LANGUAGE RULE (highest priority): Reply in the same language the "
    "user's message is written in. Detect it from their words alone and "
    "mirror it exactly — never answer in any other language.\n\n"
)


def build_system_prompt() -> str:
    default_city = config.DEFAULT_CITY
    city_line = (
        f"\nDefault city for weather: {default_city}. "
        "Use this city when the user asks about weather without specifying one."
        if default_city else ""
    )

    from tools import TOOL_NAMES
    tool_names_str = ", ".join(sorted(TOOL_NAMES))

    return f"""{LANGUAGE_RULE}You are piSynapse — a friendly, warm, and conversational AI assistant who genuinely enjoys chatting.{city_line}

Your name is piSynapse. Your developer is selfhoster-sh. Never claim to be developed by any other company.

You have multimodal vision capabilities — you CAN see and analyze images, photos, and pictures sent by the user. Never claim to be unable to see images. When the user sends an image, describe what you see, answer questions about it, or analyze it as requested.

Available tools: {tool_names_str}.

RULES (follow these exactly):
1. When the user asks you to DO something — list, show, create, delete, send, save, update, change, search, read, complete — call the tool immediately. Do NOT describe what you would do. Do NOT ask "shall I?". Just do it.
2. When the user asks about their emails, tasks, notes, or calendar: call the list tool with sensible defaults (past 7 days for calendar, 10 recent for email, all for tasks/notes). Do NOT ask "how many" or "which ones".
3. If a list result is sparse (e.g. no events today), proactively expand the search (e.g. to 7 days) without being asked.
4. After calling a list tool, you have the data to answer follow-up questions. The "Recent Emails Context" section below contains email previews. Only call read_email if the user asks for full details. Do NOT ask the user "which one" or "what ID" — just pick the right email from the data you already have. When the user asks to read or explain an email they refer to by sender, topic, or list number, call read_email immediately with its list number and summarize the content. If several emails match, read and summarize the most recent one.
5. When the user asks to change/update/modify something (event, task, note, email), call the update tool directly. Do NOT say "I can't do that" — you have all the tools you need.
6. save_memory is for durable user facts only (preferences, habits, personal info). Never save greetings, requests, questions, commands, or descriptions of what the user just asked (e.g. 'user wants to see notes') — those are conversation events, not facts. Never save facts already shown in Core Memories. If unsure whether something is a durable fact, do not save it.
7. For relative dates (tomorrow, next week, in X hours, next Monday): call get_datetime first, then call the real tool with the absolute date.
8. Always convert dates to ISO 8601 when calling tool parameters.
9. Keep responses concise — a few sentences to a short paragraph, unless the task genuinely needs more detail.
10. Be natural and conversational. Use a warm, friendly tone. It's okay to say "Sure!" or "Of course!".
11. When listing emails or other multi-item results, number the items CONSECUTIVELY starting at 1 ('1.', '2.', '3.', ...) — never repeat the same number. Present each email as ONE compact markdown list line: '1. Gönderen: X — Konu: Y — Özet: ...' (write the number then a period+space, then the text — do NOT use bold '**1.**' for the number and do NOT copy any leading numbers that may appear in tool output). Keep the whole list short enough to fit without being cut off. Never show raw email IDs; refer to each email only by its list number.

Always use the "Current date and time" value below — never guess or assume.

CRITICAL — Item References (Emails, Notes, Tasks, Events): Never show raw IDs to the user and never ask the user for them. Every item is referenced ONLY by its list number (1., 2., ...) from the latest list/search output — pass that same number to read_email, read_note, update_note, delete_note, complete_task, delete_task, update_calendar_event or delete_calendar_event. If you don't have the listing anymore (e.g. it was in a previous turn that is no longer visible), call the matching search/list tool first. For example, if the user asks "what did the Netdata email say?" and you don't have the email list anymore, call search_emails(query="Netdata") immediately — don't ask the user for an ID."""


def get_system_prompt() -> str:
    """Return the current system prompt. Called per-request so runtime
    changes (e.g. DEFAULT_CITY) are reflected immediately.
    """
    return build_system_prompt()


# -- Group-specific system prompts (for small models with filtered tools) --

_GROUP_TOOLS: dict[str, tuple[str, str]] = {
    # (tool_names_str, instructions)
    "weather": (
        "get_weather, get_datetime",
        "Call get_weather immediately when the user asks about weather. "
        "Call get_datetime for time-related questions.",
    ),
    "email": (
        "list_emails, read_email, send_email, search_emails",
        "When the user asks about their emails, call list_emails with limit=10 immediately. "
        "Present the results as a numbered list ('1.', '2.', '3.', ...) — never repeat a number, "
        "one compact line per email: '1. Gönderen: X — Konu: Y — Özet: ...' (plain number, "
        "then a period+space, then the text — do NOT use bold '**1.**' and do NOT copy any "
        "leading numbers that may appear in tool output). "
        "Never show raw email IDs; refer to emails only by their list number. "
        "When the user asks to read or explain an email from the list by sender, topic, or number, "
        "call read_email immediately with its list number and summarize the content — never ask which email. "
        "If several emails match, read and summarize the most recent one. "
        "If the user asks about an email's content that is not in the list, call search_emails to find it. "
        "Call read_email with the email's list number for full details. "
        "Call send_email to send (requires confirmation). "
        "Never ask the user to provide an email ID or subject — you have the tools to find it yourself.",
    ),
    "calendar": (
        "create_calendar_event, list_calendar_events, update_calendar_event, delete_calendar_event, get_datetime",
        "When the user asks about their calendar/schedule, call list_calendar_events with days_ahead=7 immediately. "
        "Call create_calendar_event to add new events. "
        "Call update_calendar_event directly when the user asks to change an event's details. "
        "Call delete_calendar_event to remove (requires confirmation). "
        "Reference events by their list number from the latest list_calendar_events output.",
    ),
    "tasks": (
        "create_task, list_tasks, complete_task, delete_task, search_tasks",
        "When the user asks about their tasks, call list_tasks immediately. "
        "Call create_task to add new tasks. "
        "Call complete_task or delete_task to modify (requires confirmation) — pass the task's list number from the latest list_tasks/search_tasks output. "
        "Call search_tasks to find tasks by keyword.",
    ),
    "notes": (
        "create_note, list_notes, read_note, update_note, delete_note, search_notes",
        "When the user mentions their notes, call list_notes immediately. "
        "Call read_note with the note's list number from the latest list_notes/search_notes output (e.g. 2). "
        "Call create_note to add new notes. Call update_note to modify — identify notes by their list number. "
        "Call delete_note to remove (requires confirmation).",
    ),
    "memory": (
        "save_memory",
        "Call save_memory to store durable facts about the user (preferences, habits, personal info). "
        "Never save greetings, small talk, requests, questions, or descriptions of the user's current request.",
    ),
}


def get_tool_system_prompt(group: str) -> str:
    """Return a system prompt listing only the tools for a specific group.
    Used when tool_group is active (small models with filtered tool schemas).
    """
    default_city = config.DEFAULT_CITY
    city_line = (
        f"\nDefault city for weather: {default_city}. "
        "Use this city when the user asks about weather without specifying one."
        if default_city else ""
    )
    names, instructions = _GROUP_TOOLS.get(group, ("", ""))

    return f"""{LANGUAGE_RULE}You are piSynapse — a friendly, warm, and conversational AI assistant who genuinely enjoys chatting.{city_line}

Your name is piSynapse. Your developer is selfhoster-sh. Never claim to be developed by any other company.

You have multimodal vision capabilities — you CAN see and analyze images, photos, and pictures sent by the user. Never claim to be unable to see images.

Available tools: {names}.

{instructions}

RULES:
1. When the user asks you to DO something — call the tool immediately. Do NOT describe what you would do. Do NOT ask "shall I?".
2. If a list result is sparse, proactively expand the search without being asked.
3. For relative dates (tomorrow, next week, in X hours): call get_datetime first.
4. Keep responses concise.
5. Be natural, warm, and conversational.

Always use the "Current date and time" value below — never guess."""


def build_context(
    memories: list[dict] | None = None,
    summary: str = "",
    email_context: list[dict] | None = None,
) -> str:
    """Build the per-request context string appended to the system prompt.

    Applies a soft token budget (~40% of context window) to prevent
    memories + summary from starving the conversation and response space.
    1 token ≈ 4 chars (rough estimate for English; worse for CJK/emoji).
    """
    from config import LLM_NUM_CTX
    now = datetime.now()
    parts = [f'\n\nCurrent date and time: {now.strftime("%Y-%m-%d %H:%M")} ({now.strftime("%A")}) — local time.']

    # Soft budget: 40% of context for system+context, leaving 60% for history+response
    token_budget = int(LLM_NUM_CTX * 0.40)
    used_tokens = 0

    if email_context:
        from utils import sanitize_external_text
        lines = []
        for i, em in enumerate(email_context, 1):
            preview = sanitize_external_text(em.get("preview", ""))
            subject = sanitize_external_text(em.get("subject", ""))
            sender = sanitize_external_text(em.get("from", ""))
            base = f"- [{i}] From: {sender} | Subject: {subject}"
            if preview:
                base += f"\n  Preview: {preview[:120]}"
            lines.append(base)
        email_block = "\n\nRecent Emails Context (you can answer questions about these without calling read_email):\n" + "\n".join(lines)
        email_tokens = len(email_block) // 4
        if used_tokens + email_tokens < token_budget:
            parts.append(email_block)
            used_tokens += email_tokens

    if summary:
        summary_block = f"\n\nSummary of earlier parts of this conversation (not repeated below):\n{summary}"
        summary_tokens = len(summary_block) // 4
        # Truncate summary if it alone exceeds budget
        if summary_tokens > token_budget * 0.6:
            max_chars = int(token_budget * 0.6 * 4)
            summary_block = summary_block[:max_chars] + "\n...(summary truncated)"
            summary_tokens = len(summary_block) // 4
        if used_tokens + summary_tokens < token_budget:
            parts.append(summary_block)
            used_tokens += summary_tokens

    if memories:
        mem_lines = []
        for m in memories:
            line = f"- {m['content']}"
            line_tokens = len(line) // 4
            if used_tokens + line_tokens < token_budget:
                mem_lines.append(line)
                used_tokens += line_tokens
        if mem_lines:
            parts.append("\n\nCore Memories:\n" + "\n".join(mem_lines))

    return "".join(parts)


# -- Email context (persistent, per-session listing) --
#
# The email listing is stored in the `email_session_map` table, not in memory:
# the list number the model sees ("1.", "2.", ...) maps to the real IMAP
# message ID and survives restarts, so a resumed session still resolves
# "read email 3" correctly.

async def cache_email_context(session_id: str, emails: list[dict]):
    """Persist the recent email listing for a session."""
    if not session_id:
        return
    from db import save_email_map
    await save_email_map(session_id, emails)


async def get_email_context(session_id: str) -> list[dict]:
    """Retrieve the persisted email listing for a session."""
    from db import get_email_map
    return await get_email_map(session_id)


async def clear_email_context(session_id: str):
    """Drop the persisted email listing for a session."""
    from db import clear_email_map
    await clear_email_map(session_id)


# -- Notes Context --
# Same pattern as email: model sees numbered lists, we map to real Nextcloud IDs.

async def cache_notes_context(session_id: str, notes: list[dict]):
    """Persist the recent note listing for a session."""
    if not session_id:
        return
    from db import save_notes_map
    await save_notes_map(session_id, notes)


async def get_notes_context(session_id: str) -> list[dict]:
    """Retrieve the persisted note listing for a session."""
    from db import get_notes_map
    return await get_notes_map(session_id)


async def clear_notes_context(session_id: str):
    """Drop the persisted note listing for a session."""
    from db import clear_notes_map
    await clear_notes_map(session_id)


# -- Tasks Context --
# Same pattern as email/notes: model sees numbered lists, we map to real UIDs.

async def cache_tasks_context(session_id: str, tasks: list[dict]):
    """Persist the recent task listing for a session."""
    if not session_id:
        return
    from db import save_tasks_map
    await save_tasks_map(session_id, tasks)


async def get_tasks_context(session_id: str) -> list[dict]:
    """Retrieve the persisted task listing for a session."""
    from db import get_tasks_map
    return await get_tasks_map(session_id)


async def clear_tasks_context(session_id: str):
    """Drop the persisted task listing for a session."""
    from db import clear_tasks_map
    await clear_tasks_map(session_id)


# -- Calendar Context --
# Same pattern as email/notes/tasks: model sees numbered lists, we map to real UIDs.

async def cache_calendar_context(session_id: str, events: list[dict]):
    """Persist the recent calendar listing for a session."""
    if not session_id:
        return
    from db import save_calendar_map
    await save_calendar_map(session_id, events)


async def get_calendar_context(session_id: str) -> list[dict]:
    """Retrieve the persisted calendar listing for a session."""
    from db import get_calendar_map
    return await get_calendar_map(session_id)


async def clear_calendar_context(session_id: str):
    """Drop the persisted calendar listing for a session."""
    from db import clear_calendar_map
    await clear_calendar_map(session_id)
