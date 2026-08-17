"""piSynapse Tools — Tool Dispatcher
"""

import asyncio
import logging
from datetime import datetime

from .definitions import _as_bool, _safe_int

logger = logging.getLogger("piSynapse")


def _get_context_fn(name: str):
    """Return the context getter function for a given tool category."""
    from prompt import get_calendar_context, get_email_context, get_notes_context, get_tasks_context
    return {
        "email": get_email_context,
        "notes": get_notes_context,
        "tasks": get_tasks_context,
        "calendar": get_calendar_context,
    }[name]


def is_tool_success(result: str) -> bool:
    """Classify a tool result string for audit logging.

    Tool handlers contractually prefix genuine failures with "ERROR"; an
    empty result is never a success (a blank answer must not be counted as
    a successful tool call in the audit log).
    """
    return bool(result) and not result.startswith("ERROR")


async def _resolve_id(session_id: str, ref, context_fn, id_field: str = "uid", coerce: bool = False):
    """Resolve a 1-based list position to the real ID for this session.

    The model only ever sees numbered list items (never raw IDs). If ``ref``
    is a number that fits the persisted listing, map it to the stored ID.
    A numeric reference that does NOT fit the listing is refused (None):
    guessing a raw ID could silently affect the wrong record. Raw non-numeric
    IDs (legacy direct calls) pass through unchanged.

    Args:
        context_fn: async callable that returns the session's listing (e.g. get_email_context).
        id_field: key to extract from each listing item (default "uid").
        coerce: if True, try int(ref) for legacy raw-ID calls (e.g. Nextcloud note IDs).
    """
    items = await context_fn(session_id)
    is_num = isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit())
    if is_num:
        if items and 1 <= int(ref) <= len(items):
            return items[int(ref) - 1].get(id_field)
        return None
    if coerce:
        try:
            return int(ref)
        except (ValueError, TypeError):
            return None
    return ref


async def run_tool(name: str, params: dict, context: dict | None = None) -> str:
    """Route a tool call to the appropriate handler and return the result string."""
    context = context or {}

    if name == "get_datetime":
        return f"Current: {datetime.now().strftime('%d %B %Y, %A, %H:%M')}"

    if name == "get_weather":
        from weather import get_weather
        return await get_weather(params.get("city", ""))

    if name in {"create_calendar_event", "list_calendar_events", "update_calendar_event", "delete_calendar_event"}:
        session_id = context.get("session_id", "")
        from prompt import cache_calendar_context
        try:
            if name == "create_calendar_event":
                from calendar_ops import create_event
                st = params.get("start_time")
                if not st:
                    return "ERROR: start_time required."
                dur = _safe_int(params.get("duration_minutes", 60), 60, "duration_minutes", min_value=1)
                return await asyncio.to_thread(
                    create_event,
                    params.get("summary", "New Event"),
                    st,
                    dur,
                )
            elif name == "list_calendar_events":
                from calendar_ops import list_events
                days = _safe_int(params.get("days_ahead", 7), 7, "days_ahead", min_value=1)
                raw = await asyncio.to_thread(list_events, days)
                if not raw.startswith("ERROR") and session_id:
                    await cache_calendar_context(session_id, _parse_calendar_listing(raw))
                return raw
            elif name == "update_calendar_event":
                from calendar_ops import update_event
                s = params.get("summary", "")
                if not s:
                    return "ERROR: Event name required."
                new_s = params.get("new_summary", "")
                new_t = params.get("new_start_time", "")
                new_d = _safe_int(params.get("new_duration_minutes", 0), 0, "new_duration_minutes")
                uid = params.get("event_uid", "")
                if uid:
                    resolved = await _resolve_id(session_id, uid, _get_context_fn("calendar"))
                    if resolved is None:
                        return f"ERROR: Event '{uid}' not found. Run list_calendar_events first to see available events."
                    uid = resolved
                return await asyncio.to_thread(update_event, s, new_summary=new_s, new_start_time=new_t, new_duration_minutes=new_d, event_uid=uid)
            elif name == "delete_calendar_event":
                from calendar_ops import delete_event
                s = params.get("summary")
                if not s:
                    return "ERROR: Event name required."
                uid = params.get("event_uid", "")
                if uid:
                    resolved = await _resolve_id(session_id, uid, _get_context_fn("calendar"))
                    if resolved is None:
                        return f"ERROR: Event '{uid}' not found. Run list_calendar_events first to see available events."
                    uid = resolved
                return await asyncio.to_thread(delete_event, s, event_uid=uid)
        except ValueError as e:
            return f"ERROR: {e}"
        except Exception as e:
            logger.error(f"Nextcloud Error: {e}")
            return "ERROR: Calendar operation failed. Check server logs."

    if name in {"list_emails", "read_email", "send_email", "search_emails"}:
        return await _run_mail_tool(name, params, context.get("session_id", ""))

    if name == "save_memory":
        content = (params.get("content") or "").strip()
        if not content:
            return "ERROR: content required."
        from db import save_memory
        importance = params.get("importance", 5)
        try:
            importance = max(1, min(10, int(importance)))
        except (ValueError, TypeError):
            importance = 5
        await save_memory(
            content=content,
            category=params.get("category", "general"),
            importance=importance,
            user_id=context.get("user_id"),
        )
        return "Memory saved."

    if name in {"create_note", "list_notes", "read_note", "update_note", "delete_note", "search_notes"}:
        return await _run_notes_tool(name, params, context.get("session_id", ""))

    if name in {"create_task", "list_tasks", "complete_task", "delete_task", "search_tasks"}:
        return await _run_tasks_tool(name, params, context.get("session_id", ""))

    return "ERROR: Tool not found."


async def _run_notes_tool(name: str, params: dict, session_id: str = "") -> str:
    """Dispatch note tool calls with session-aware ID resolution."""
    from nextcloud_notes import (
        create_note,
        delete_note,
        get_note,
        update_note,
    )
    from nextcloud_notes import (
        list_notes as _list_notes_raw,
    )
    from nextcloud_notes import (
        search_notes as _search_notes_raw,
    )

    try:
        if name == "create_note":
            title = params.get("title", "").strip()
            if not title:
                return "ERROR: title required."
            return await create_note(
                title=title,
                content=params.get("content", ""),
                category=params.get("category", ""),
            )
        elif name == "list_notes":
            raw = await _list_notes_raw()
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_notes_context
                await cache_notes_context(session_id, _parse_note_listing(raw))
            return raw
        elif name == "read_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            resolved = await _resolve_id(session_id, nid, _get_context_fn("notes"), id_field="id", coerce=True)
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes."
            return await get_note(resolved)
        elif name == "update_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            resolved = await _resolve_id(session_id, nid, _get_context_fn("notes"), id_field="id", coerce=True)
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes."
            return await update_note(
                resolved,
                title=params.get("title"),
                content=params.get("content"),
                category=params.get("category"),
                tags=params.get("tags"),
            )
        elif name == "delete_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            resolved = await _resolve_id(session_id, nid, _get_context_fn("notes"), id_field="id", coerce=True)
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes."
            return await delete_note(resolved)
        elif name == "search_notes":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required."
            raw = await _search_notes_raw(q)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_notes_context
                await cache_notes_context(session_id, _parse_note_listing(raw))
            return raw
    except Exception as e:
        logger.error(f"Notes Error: {e}")
        return "ERROR: Notes operation failed. Check server logs."

    return "ERROR: Tool not found."


def _parse_note_listing(text: str) -> list[dict]:
    """Extract note IDs from a numbered listing returned by list_notes/search_notes.

    Looks for lines like ``1. Title`` followed by ``ID: 284`` to build
    the same ordered list that the model sees, mapping positions to real IDs.
    """
    import re
    notes: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"\s*\*?\s*(\d+)\.\s+(.+)", lines[i])
        if m:
            title = m.group(2).strip()
            preview = ""
            category = ""
            note_id = 0
            for j in range(i + 1, min(i + 4, len(lines))):
                if "ID:" in lines[j]:
                    try:
                        note_id = int(lines[j].split("ID:")[-1].strip())
                    except (ValueError, TypeError):
                        pass
                elif "Category:" in lines[j]:
                    category = lines[j].split("Category:")[-1].strip()
                elif "Preview:" in lines[j]:
                    preview = lines[j].split("Preview:")[-1].strip()
            if note_id:
                notes.append({"id": note_id, "title": title, "category": category, "preview": preview})
        i += 1
    return notes


async def _run_tasks_tool(name: str, params: dict, session_id: str = "") -> str:
    """Dispatch task tool calls with session-aware UID resolution."""
    from nextcloud_tasks import (
        complete_task,
        create_task,
        delete_task,
    )
    from nextcloud_tasks import (
        list_tasks as _list_tasks_raw,
    )
    from nextcloud_tasks import (
        search_tasks as _search_tasks_raw,
    )

    try:
        if name == "create_task":
            summary = params.get("summary", "").strip()
            if not summary:
                return "ERROR: summary required."
            priority = _safe_int(params.get("priority", 0), 0, "priority")
            return await create_task(
                summary=summary,
                due=params.get("due", ""),
                priority=priority,
                notes=params.get("notes", ""),
            )
        elif name == "list_tasks":
            show_completed = _as_bool(params.get("show_completed", False))
            raw = await _list_tasks_raw(show_completed=show_completed)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_tasks_context
                await cache_tasks_context(session_id, _parse_task_listing(raw))
            return raw
        elif name == "complete_task":
            uid = params.get("uid", "").strip()
            if not uid:
                return "ERROR: uid required."
            resolved = await _resolve_id(session_id, uid, _get_context_fn("tasks"))
            if resolved is None:
                return f"ERROR: Task '{uid}' not found. Run list_tasks first to see available tasks."
            return await complete_task(resolved)
        elif name == "delete_task":
            uid = params.get("uid", "").strip()
            if not uid:
                return "ERROR: uid required."
            resolved = await _resolve_id(session_id, uid, _get_context_fn("tasks"))
            if resolved is None:
                return f"ERROR: Task '{uid}' not found. Run list_tasks first to see available tasks."
            return await delete_task(resolved)
        elif name == "search_tasks":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required."
            raw = await _search_tasks_raw(q)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_tasks_context
                await cache_tasks_context(session_id, _parse_task_listing(raw))
            return raw
    except ValueError as e:
        return f"ERROR: {e}"
    except Exception as e:
        logger.error(f"Task tool {name} failed: {e}")
        return f"ERROR: {name} failed"

    return "ERROR: Tool not found."


def _parse_task_listing(text: str) -> list[dict]:
    """Extract task UIDs from a numbered listing returned by list_tasks/search_tasks.

    Looks for lines like ``1. [o] Buy groceries`` followed by ``UID: abc123def012...``
    to build the same ordered list that the model sees, mapping positions to real UIDs.
    """
    import re
    tasks: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"\s*(\d+)\.\s+\[([ox])\]\s+(.+)", lines[i])
        if m:
            completed = m.group(2) == "x"
            summary = m.group(3).strip()
            uid = ""
            due = ""
            priority = 0
            for j in range(i + 1, min(i + 4, len(lines))):
                if "UID:" in lines[j]:
                    uid = lines[j].split("UID:")[-1].strip().rstrip(".")
                elif "Due:" in lines[j]:
                    due = lines[j].split("Due:")[-1].strip()
                elif "P:" in lines[j]:
                    try:
                        priority = int(lines[j].split("P:")[-1].strip())
                    except (ValueError, TypeError):
                        pass
            if uid:
                tasks.append({"uid": uid, "summary": summary, "due": due, "priority": priority, "completed": completed})
        i += 1
    return tasks


def _parse_calendar_listing(text: str) -> list[dict]:
    """Extract event UIDs from a numbered listing returned by list_calendar_events.

    Looks for lines like ``1. 2026-08-20 10:00 | Meeting`` followed by ``UID: abc123...``
    to build the same ordered list that the model sees, mapping positions to real UIDs.
    """
    import re
    events: list[dict] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"\s*(\d+)\.\s+(.+?\|.+)", lines[i])
        if m:
            rest = m.group(2).strip()
            parts = rest.split("|", 1)
            start_time = parts[0].strip() if len(parts) > 1 else ""
            summary = parts[1].strip() if len(parts) > 1 else rest
            uid = ""
            for j in range(i + 1, min(i + 4, len(lines))):
                if "UID:" in lines[j]:
                    uid = lines[j].split("UID:")[-1].strip().rstrip(".")
            if uid:
                events.append({"uid": uid, "summary": summary, "start": start_time})
        i += 1
    return events


async def _run_mail_tool(name: str, params: dict, session_id: str = "") -> str:
    """Dispatch email tool calls to the active mail client."""
    from mail import get_active_mail_client
    from prompt import cache_email_context

    mc = get_active_mail_client()
    if not mc:
        return "ERROR: Mail connection failed. Check .env configuration."

    account_id = 1
    mailbox_id = "INBOX"

    try:
        if name == "list_emails":
            limit = _safe_int(params.get("limit", 10), 10, "limit", min_value=1)
            msgs = await mc.get_messages(account_id, mailbox_id, limit)
            if not msgs:
                return "Inbox is empty."
            if session_id:
                await cache_email_context(session_id, msgs)
            lines = [f" Recent Emails (showing {len(msgs)}):"]
            for m in msgs:
                bp = (m.get("body", "") or "").replace("\n", " ")[:150]
                lines.append(
                    f"From: {m.get('from', '?')} | Subject: {m.get('subject', '(no subject)')} "
                    f"| Date: {m.get('date', '?')} | Preview: {bp}"
                )
            return "\n".join(lines)

        elif name == "read_email":
            mid = params.get("message_id") or params.get("id")
            if not mid:
                return "ERROR: message_id required."
            resolved = await _resolve_id(session_id, mid, _get_context_fn("email"), id_field="id")
            if resolved is None:
                return "ERROR: Email not found. Run list_emails first to get the current listing."
            m = await mc.get_message(account_id, mailbox_id, resolved)
            if not m:
                return "ERROR: Email not found."
            return (f"Email Details\n\nFrom: {m.get('from', '?')}\n"
                    f"Subject: {m.get('subject', '?')}\nDate: {m.get('date', '?')}\n\n"
                    f"Content:\n{m.get('body', '')[:1500]}")

        elif name == "send_email":
            to, subj, body = params.get("to"), params.get("subject"), params.get("body")
            if not all([to, subj, body]):
                return "ERROR: 'to', 'subject' and 'body' are required."
            ok = await mc.send_message(account_id, to, subj, body, params.get("cc", ""), params.get("bcc", ""))
            detail = f"To: {to}"
            if params.get("cc"):
                detail += f"\nCc: {params['cc']}"
            return f"Email sent!\n{detail}\nSubject: {subj}" if ok else "Failed to send."

        elif name == "search_emails":
            q = params.get("query")
            if not q:
                return "ERROR: 'query' required."
            limit = _safe_int(params.get("limit", 10), 10, "limit", min_value=1)
            results = await mc.search_messages(account_id, q, limit)
            if not results:
                return f"'{q}' no results found."
            if session_id:
                await cache_email_context(session_id, results)
            lines = [f"'{q}' Results ({len(results)}):"]
            for m in results:
                bp = (m.get("body", "") or "").replace("\n", " ")[:150]
                lines.append(
                    f"From: {m.get('from', '?')} | Subject: {m.get('subject', '(no subject)')} "
                    f"| Preview: {bp}"
                )
            return "\n".join(lines)

    except ValueError as e:
        return f"ERROR: {e}"
    except Exception as e:
        logger.error(f"Mail Error: {e}")
        return "ERROR: Mail operation failed. Check server logs."
    return "ERROR: Tool not found."
