"""piSynapse Tools — Tool Definitions
"""

import json


def _safe_int(value, default: int, param_name: str) -> int:
    """Try to cast value to int; raise ValueError on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        raise ValueError(f"'{param_name}' must be a valid number, got: {value!r}")

# -- Tool Definitions (Ollama native tool-calling schema) --

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name. Omit to use the user's default city."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date and time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Add a new event to the user's calendar. Call this when the user asks to schedule something.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start_time": {"type": "string", "description": "Start time in ISO 8601 format, e.g. 2026-06-20T14:00:00."},
                    "duration_minutes": {"type": "integer", "description": "Event length in minutes. Defaults to 60."},
                },
                "required": ["summary", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "List upcoming calendar events with date, time, title, and description preview. Call this when the user asks about their schedule.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "How many days ahead to look. Defaults to 7."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Delete a calendar event by its title (or part of it), or by its UID (from list_calendar_events). UID provides exact matching when multiple events share the same title.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Title (or part of it) of the event to delete."},
                    "event_uid": {"type": "string", "description": "Exact UID of the event (shown in list_calendar_events output). Use this for precise matching when summary alone is ambiguous."},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_calendar_event",
            "description": "Update an existing calendar event: change its title, time, and/or duration. Provide the current title (or part of it) to identify the event, plus the fields to change. If multiple events match, provide event_uid from list_calendar_events for precise matching.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Current title (or part of it) of the event to update."},
                    "new_summary": {"type": "string", "description": "New title. Leave empty to keep current."},
                    "new_start_time": {"type": "string", "description": "New start time in ISO 8601 format (e.g. 2026-07-29T18:40:00). Leave empty to keep current."},
                    "new_duration_minutes": {"type": "integer", "description": "New duration in minutes. Leave 0 to keep current."},
                    "event_uid": {"type": "string", "description": "Exact UID of the event (shown in list_calendar_events output). Use this for precise matching when summary alone matches multiple events."},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_emails",
            "description": "Show the user's recent inbox emails with sender, subject, date, and a preview. Returns a list you can use to answer questions or pick one to read in full.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max number of emails to return. Defaults to 10."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read the full content of one email by its ID from list_emails or search_emails results. Use this when the user asks about details of a specific email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The email's ID (shown in list_emails output under 'ID:')."},
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email. Requires user confirmation before sending.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body text."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search the user's emails by subject, sender, or body content. Returns matching emails with previews. Useful when the user mentions a specific topic or person.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term (matches subject, sender, and body)."},
                    "limit": {"type": "integer", "description": "Max number of results. Defaults to 10."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save a durable fact about the user — preferences, habits, personal info. "
                "Never save greetings or facts already shown in Core Memories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact to remember, written as a short standalone sentence."},
                    "category": {
                        "type": "string",
                        "enum": ["personal", "preference", "habit", "work", "general"],
                        "description": "Best-fitting category for this memory.",
                    },
                },
                "required": ["content"],
            },
        },
    },
    # -- Nextcloud Notes --
    {
        "type": "function",
        "function": {
            "name": "create_note",
            "description": "Create a new note in Nextcloud Notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Note title."},
                    "content": {"type": "string", "description": "Note content (markdown). Defaults to empty."},
                    "category": {"type": "string", "description": "Note category (e.g. 'work', 'personal')."},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "List the user's notes stored in Nextcloud Notes — shows title, category, tags, and a content preview. Call this first when the user mentions their notes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": "Read a note by its ID. The ID is the actual Nextcloud ID (e.g. 284), NOT the list order number.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "The note's actual ID from Nextcloud (e.g. 284), as shown in list_notes output."},
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_note",
            "description": "Update an existing note. Only provided fields are changed. The ID is the actual Nextcloud ID (e.g. 284).",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "The note's actual ID from Nextcloud (e.g. 284)."},
                    "title": {"type": "string", "description": "New title (leave empty to keep current)."},
                    "content": {"type": "string", "description": "New content (leave empty to keep current)."},
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_note",
            "description": "Delete a note by its ID. Requires user confirmation. The ID is the actual Nextcloud ID (e.g. 284).",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_id": {"type": "integer", "description": "The note's actual ID from Nextcloud (e.g. 284)."},
                },
                "required": ["note_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_notes",
            "description": "Search the user's notes by title or content. Use this when the user asks about something they might have noted down.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term."},
                },
                "required": ["query"],
            },
        },
    },
    # -- Nextcloud Tasks --
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a new task in Nextcloud Tasks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Task title."},
                    "due": {"type": "string", "description": "Due date in ISO 8601 (e.g. 2026-07-20 or 2026-07-20T14:00:00)."},
                    "priority": {"type": "integer", "description": "Priority 1 (highest) to 9 (lowest). 0 = none."},
                    "notes": {"type": "string", "description": "Task notes/description."},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Show the user's tasks from Nextcloud Tasks — title, due date, priority, and description preview. Call this when the user asks about their tasks or to-dos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "show_completed": {"type": "boolean", "description": "Include completed tasks. Defaults to false."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task as done. Find the UID from list_tasks output under 'UID:'. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uid": {"type": "string", "description": "Task UID (or unique prefix) from list_tasks output."},
                },
                "required": ["uid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_task",
            "description": "Delete a task permanently. Find the UID from list_tasks output under 'UID:'. Requires user confirmation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "uid": {"type": "string", "description": "Task UID (or unique prefix) from list_tasks output."},
                },
                "required": ["uid"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_tasks",
            "description": "Search the user's tasks by title or description. Use this when the user asks about a specific task they don't remember the name of.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term."},
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_NAMES = {t["function"]["name"] for t in TOOLS}

# -- Tool Groups (for small models: send only relevant tools) --
# Each group maps to a list of tool names. When the intent router identifies
# a domain, only that group's tools are sent to the model, reducing schema
# noise from ~2000 tokens to ~200-400 tokens.
# get_datetime is included in all groups — it's tiny (no params) and useful everywhere.
TOOL_GROUPS: dict[str, list[str]] = {
    "weather":  ["get_weather", "get_datetime"],
    "email":    ["list_emails", "read_email", "send_email", "search_emails", "get_datetime"],
    "calendar": ["create_calendar_event", "list_calendar_events", "update_calendar_event", "delete_calendar_event", "get_datetime"],
    "tasks":    ["create_task", "list_tasks", "complete_task", "delete_task", "search_tasks", "get_datetime"],
    "notes":    ["create_note", "list_notes", "read_note", "update_note", "delete_note", "search_notes", "get_datetime"],
    "memory":   ["save_memory", "get_datetime"],
}


def get_tools_for_group(group: str | None) -> list[dict]:
    """Return the full tool definitions for a group, or all tools if group is None."""
    if group is None:
        return TOOLS
    names = set(TOOL_GROUPS.get(group, []))
    return [t for t in TOOLS if t["function"]["name"] in names]


def get_combined_tools() -> list[dict]:
    """Return tools from all groups combined (deduplicated).
    Used as fallback when intent is 'action' but tool_group is unknown.
    """
    all_names: set[str] = set()
    for names in TOOL_GROUPS.values():
        all_names.update(names)
    return [t for t in TOOLS if t["function"]["name"] in all_names]


# Tools requiring user confirmation before execution
CONFIRM_TOOLS = {"send_email", "delete_calendar_event", "update_calendar_event", "delete_note", "complete_task", "delete_task"}

# Required params for confirm tools (checked before yielding confirm event)
CONFIRM_REQUIRED = {
    "send_email": ["to", "subject", "body"],
    "delete_calendar_event": ["summary"],
    "update_calendar_event": ["summary"],
    "delete_note": ["note_id"],
    "complete_task": ["uid"],
    "delete_task": ["uid"],
}


def validate_confirm_params(tool: str, params: dict) -> str | None:
    """Return error message if required params are missing, else None."""
    required = CONFIRM_REQUIRED.get(tool)
    if not required:
        return None
    missing = [k for k in required if not params.get(k)]
    if missing:
        return f"ERROR: '{tool}' requires: {', '.join(required)}. Missing: {', '.join(missing)}"
    return None


def parse_tool_args(raw) -> dict:
    """Tool call arguments normally arrive as a dict, but some models emit
    them as a JSON-encoded string -- handle both safely.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}
