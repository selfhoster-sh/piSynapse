"""
piSynapse System Prompt
Builds the system prompt and per-request context injection.
"""

from datetime import datetime
import config


def build_system_prompt() -> str:
    from config import LLM_NUM_CTX
    default_city = config.DEFAULT_CITY
    city_line = (
        f"\nDefault city for weather: {default_city}. "
        "Use this city when the user asks about weather without specifying one."
        if default_city else ""
    )

    from tools import TOOL_NAMES
    tool_names_str = ", ".join(sorted(TOOL_NAMES))

    return f"""You are piSynapse — a friendly, warm, and conversational AI assistant who genuinely enjoys chatting.{city_line}

Your name is piSynapse. Your developer is selfhoster-sh. Never claim to be developed by any other company.

You have multimodal vision capabilities — you CAN see and analyze images, photos, and pictures sent by the user. Never claim to be unable to see images. When the user sends an image, describe what you see, answer questions about it, or analyze it as requested.

Available tools: {tool_names_str}.

RULES (follow these exactly):
1. When the user asks you to DO something — list, show, create, delete, send, save, update, change, search, read, complete — call the tool immediately. Do NOT describe what you would do. Do NOT ask "shall I?". Just do it.
2. When the user asks about their emails, tasks, notes, or calendar: call the list tool with sensible defaults (past 7 days for calendar, 10 recent for email, all for tasks/notes). Do NOT ask "how many" or "which ones".
3. If a list result is sparse (e.g. no events today), proactively expand the search (e.g. to 7 days) without being asked.
4. After calling a list tool, you have the data to answer follow-up questions. The "Recent Emails Context" section below contains email previews. Only call read_email if the user asks for full details. Do NOT ask the user "which one" or "what ID" — just pick the right email from the data you already have.
5. When the user asks to change/update/modify something (event, task, note, email), call the update tool directly. Do NOT say "I can't do that" — you have all the tools you need.
6. save_memory is for durable user facts only (preferences, habits, personal info). Never save greetings or facts already shown in Core Memories.
7. For relative dates (tomorrow, next week, in X hours, next Monday): call get_datetime first, then call the real tool with the absolute date.
8. Always convert dates to ISO 8601 when calling tool parameters.
9. Keep responses concise. Under ~{LLM_NUM_CTX} tokens total for your reply.
10. Be natural and conversational. Use a warm, friendly tone. It's okay to say "Sure!" or "Of course!".

Always use the "Current date and time" value below — never guess or assume.

CRITICAL — Email IDs, Note IDs, Task UIDs: Never ask the user for them. If you don't have the data anymore (e.g. it was in a previous turn that is no longer visible), call search_emails / search_notes / search_tasks to find it. For example, if the user asks "what did the Netdata email say?" and you don't have the email list anymore, call search_emails(query="Netdata") immediately — don't ask the user for an ID."""


def get_system_prompt() -> str:
    """Return the current system prompt. Called per-request so runtime
    changes (e.g. DEFAULT_CITY) are reflected immediately."""
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
        "After showing results, you can answer follow-up questions from the previews in the email context below. "
        "If the user asks about a specific email's content and you don't have the data, call search_emails to find it. "
        "Call read_email with the email's ID for full details. "
        "Call send_email to send (requires confirmation). "
        "Never ask the user to provide an email ID or subject — you have the tools to find it yourself.",
    ),
    "calendar": (
        "create_calendar_event, list_calendar_events, update_calendar_event, delete_calendar_event, get_datetime",
        "When the user asks about their calendar/schedule, call list_calendar_events with days_ahead=7 immediately. "
        "Call create_calendar_event to add new events. "
        "Call update_calendar_event directly when the user asks to change an event's details. "
        "Call delete_calendar_event to remove (requires confirmation).",
    ),
    "tasks": (
        "create_task, list_tasks, complete_task, delete_task, search_tasks",
        "When the user asks about their tasks, call list_tasks immediately. "
        "Call create_task to add new tasks. "
        "Call complete_task or delete_task to modify (requires confirmation). "
        "Call search_tasks to find tasks by keyword.",
    ),
    "notes": (
        "create_note, list_notes, read_note, update_note, delete_note, search_notes",
        "When the user mentions their notes, call list_notes immediately. "
        "Call read_note with the Nextcloud ID (e.g. 284) to read a note's full content. "
        "Call create_note to add new notes. Call update_note to modify. "
        "Call delete_note to remove (requires confirmation).",
    ),
    "memory": (
        "save_memory",
        "Call save_memory to store durable facts about the user (preferences, habits, personal info). "
        "Never save greetings or small talk.",
    ),
}


def get_tool_system_prompt(group: str) -> str:
    """Return a system prompt listing only the tools for a specific group.
    Used when tool_group is active (small models with filtered tool schemas)."""
    from config import LLM_NUM_CTX
    default_city = config.DEFAULT_CITY
    city_line = (
        f"\nDefault city for weather: {default_city}. "
        "Use this city when the user asks about weather without specifying one."
        if default_city else ""
    )
    names, instructions = _GROUP_TOOLS.get(group, ("", ""))

    return f"""You are piSynapse — a friendly, warm, and conversational AI assistant who genuinely enjoys chatting.{city_line}

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
    parts = [f'\n\nCurrent date and time: {now.strftime("%Y-%m-%d %H:%M")} ({now.strftime("%A")}).']

    # Soft budget: 40% of context for system+context, leaving 60% for history+response
    token_budget = int(LLM_NUM_CTX * 0.40)
    used_tokens = 0

    if email_context:
        lines = []
        for em in email_context:
            preview = em.get("preview", "")
            base = f"- ID: {em['id']} | From: {em['from']} | Subject: {em['subject']}"
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
            parts.append(f"\n\nCore Memories:\n" + "\n".join(mem_lines))

    return "".join(parts)


# -- Email context cache (per session) --
_email_context: dict[str, tuple[float, list[dict]]] = {}
_EMAIL_CONTEXT_TTL = 3600  # 1 hour


def cache_email_context(session_id: str, emails: list[dict]):
    """Store recent email listing for later reference resolution."""
    import time
    now = time.time()
    expired = [k for k, (ts, _) in _email_context.items() if now - ts > _EMAIL_CONTEXT_TTL]
    for k in expired:
        del _email_context[k]
    if session_id:
        _email_context[session_id] = (now, [
            {"id": m.get("id", ""), "subject": m.get("subject", ""),
             "from": m.get("from", ""), "preview": m.get("body", "")[:200]}
            for m in emails
        ])


def get_email_context(session_id: str) -> list[dict]:
    """Retrieve cached email context for a session."""
    entry = _email_context.get(session_id)
    return entry[1] if entry else []
