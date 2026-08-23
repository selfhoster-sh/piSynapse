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


def _as_position(ref) -> int | None:
    """Parse a tool parameter into a 1-based list position.

    Accepts an int, an integral float (litert/gemma routinely emits ``1.0``
    in tool-call JSON — a strict int check rejected valid references), or a
    numeric string (tolerating surrounding whitespace and a trailing dot,
    e.g. ``" 3."``). Anything else (raw IDs, truncated UIDs, garbage,
    fractional numbers) is rejected — the model is only ever allowed to
    reference items by their position in the latest listing.
    """
    if isinstance(ref, bool):
        return None
    if isinstance(ref, int):
        return ref
    if isinstance(ref, float):
        return int(ref) if ref.is_integer() else None
    if isinstance(ref, str):
        s = ref.strip().rstrip(".")
        if s.isdigit():
            return int(s)
        try:
            f = float(s)
        except ValueError:
            return None
        return int(f) if f.is_integer() else None
    return None


async def _resolve_position(session_id: str, ref, context_fn, id_field: str):
    """Map a 1-based list position to the real ID via the session's last listing.

    The model only ever sees numbered list items (never raw IDs), so every
    reference must be a number that fits the persisted listing. Out-of-range,
    non-numeric, or missing-listing references all resolve to None — guessing
    could silently affect the wrong record.
    """
    pos = _as_position(ref)
    if pos is None:
        return None
    items = await context_fn(session_id)
    if items and 1 <= pos <= len(items):
        return items[pos - 1].get(id_field)
    return None


async def run_tool(name: str, params: dict, context: dict | None = None) -> str:
    """Route a tool call to the appropriate handler and return the result string."""
    context = context or {}
    logger.info("Tool call: %s params=%s", name, str(params)[:200])

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
                summary = (params.get("summary") or "").strip()
                missing = [w for w, v in (("a title", summary), ("a start time", st)) if not v]
                if missing:
                    # Chip flow guard: never create "New Event" junk.
                    return ("CLARIFY_REQUIRED: The event request is missing "
                            + " and ".join(missing) + ". Ask the user ONE short question "
                            "(in their language) for exactly those details. "
                            "Do not call create_calendar_event again until they answer.")
                dur = _safe_int(params.get("duration_minutes", 60), 60, "duration_minutes", min_value=1)
                return await asyncio.to_thread(
                    create_event,
                    summary,
                    st,
                    dur,
                )
            elif name == "list_calendar_events":
                from calendar_ops import list_events
                days = _safe_int(params.get("days_ahead", 7), 7, "days_ahead", min_value=1)
                raw, events = await asyncio.to_thread(list_events, days)
                if not raw.startswith("ERROR") and session_id:
                    await cache_calendar_context(session_id, events)
                return raw
            elif name == "update_calendar_event":
                from calendar_ops import update_event
                s = params.get("summary", "")
                if not s:
                    return "ERROR: Event name required."
                new_s = params.get("new_summary", "")
                new_t = params.get("new_start_time", "")
                new_d = _safe_int(params.get("new_duration_minutes", 0), 0, "new_duration_minutes")
                uid_ref = params.get("event_uid", "")
                uid = ""
                if uid_ref:
                    uid = await _resolve_position(session_id, uid_ref, _get_context_fn("calendar"), id_field="uid")
                    if uid is None:
                        return f"ERROR: Event '{uid_ref}' not found. Run list_calendar_events first to see available events."
                return await asyncio.to_thread(update_event, s, new_summary=new_s, new_start_time=new_t, new_duration_minutes=new_d, event_uid=uid)
            elif name == "delete_calendar_event":
                from calendar_ops import delete_event
                s = params.get("summary")
                if not s:
                    return "ERROR: Event name required."
                uid_ref = params.get("event_uid", "")
                uid = ""
                if uid_ref:
                    uid = await _resolve_position(session_id, uid_ref, _get_context_fn("calendar"), id_field="uid")
                    if uid is None:
                        return f"ERROR: Event '{uid_ref}' not found. Run list_calendar_events first to see available events."
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
        # Guard against meta-requests being stored as memories: a description
        # of what the user just asked ("user wants to see notes") is not a
        # durable fact about the user. Seen in the wild once; never again.
        import re as _re
        if _re.search(r"(?i)\b(iste\u011fi|istegi|istemi|talebi)\b|\brequest (to|for|that)\b|\b(ask(ed)?|wants?|trying) (him|her|them|us|me)? ?(to|that)\b", content):
            logger.warning(f"save_memory rejected meta-content: {content!r}")
            return ("ERROR: That describes a request, not a durable fact about the user. "
                    "Memories must outlive the conversation (preferences, habits, personal info). "
                    "Do not retry saving this; simply fulfill the user's actual request.")
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
            content = (params.get("content") or "").strip()
            if not title:
                return "ERROR: title required."
            if not content:
                # Chip flow guard: never save an empty/placeholder note —
                # the model must ask the user for the content first.
                return ("CLARIFY_REQUIRED: The note has no content. Ask the user ONE short "
                        "question (in their language) about what to write in the note. "
                        "Do not call create_note again until they answer.")
            return await create_note(
                title=title,
                content=content,
                category=params.get("category", ""),
            )
        elif name == "list_notes":
            raw, items = await _list_notes_raw()
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_notes_context
                await cache_notes_context(session_id, items)
            return raw
        elif name == "read_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            resolved = await _resolve_position(session_id, nid, _get_context_fn("notes"), id_field="id")
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes."
            return await get_note(resolved)
        elif name == "update_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            resolved = await _resolve_position(session_id, nid, _get_context_fn("notes"), id_field="id")
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
            resolved = await _resolve_position(session_id, nid, _get_context_fn("notes"), id_field="id")
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes."
            return await delete_note(resolved)
        elif name == "search_notes":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required."
            raw, items = await _search_notes_raw(q)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_notes_context
                await cache_notes_context(session_id, items)
            return raw
    except Exception as e:
        logger.error(f"Notes Error: {e}")
        return "ERROR: Notes operation failed. Check server logs."

    return "ERROR: Tool not found."


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
                # Chip flow guard: no empty/placeholder tasks.
                return ("CLARIFY_REQUIRED: The task has no text. Ask the user ONE short "
                        "question (in their language) about what the task should be. "
                        "Do not call create_task again until they answer.")
            priority = _safe_int(params.get("priority", 0), 0, "priority")
            return await create_task(
                summary=summary,
                due=params.get("due", ""),
                priority=priority,
                notes=params.get("notes", ""),
            )
        elif name == "list_tasks":
            show_completed = _as_bool(params.get("show_completed", False))
            raw, items = await _list_tasks_raw(show_completed=show_completed)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_tasks_context
                await cache_tasks_context(session_id, items)
            return raw
        elif name == "complete_task":
            uid = params.get("uid")
            uid = str(uid).strip() if uid is not None else ""
            if not uid:
                return "ERROR: uid required."
            resolved = await _resolve_position(session_id, uid, _get_context_fn("tasks"), id_field="uid")
            if resolved is None:
                return f"ERROR: Task '{uid}' not found. Run list_tasks first to see available tasks."
            return await complete_task(resolved)
        elif name == "delete_task":
            uid = params.get("uid")
            uid = str(uid).strip() if uid is not None else ""
            if not uid:
                return "ERROR: uid required."
            resolved = await _resolve_position(session_id, uid, _get_context_fn("tasks"), id_field="uid")
            if resolved is None:
                return f"ERROR: Task '{uid}' not found. Run list_tasks first to see available tasks."
            return await delete_task(resolved)
        elif name == "search_tasks":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required."
            raw, items = await _search_tasks_raw(q)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_tasks_context
                await cache_tasks_context(session_id, items)
            return raw
    except ValueError as e:
        return f"ERROR: {e}"
    except Exception as e:
        logger.error(f"Task tool {name} failed: {e}")
        return f"ERROR: {name} failed"

    return "ERROR: Tool not found."


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
            resolved = await _resolve_position(session_id, mid, _get_context_fn("email"), id_field="id")
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
            missing = [w for w, v in (("the recipient", to), ("a subject", subj), ("the message body", body)) if not v]
            if missing:
                # Chip flow guard: never send or half-fill an email.
                return ("CLARIFY_REQUIRED: The email request is missing "
                        + " and ".join(missing) + ". Ask the user ONE short question "
                        "(in their language) for exactly those parts. "
                        "Do not call send_email again until they answer.")
            ok = await mc.send_message(account_id, to, subj, body, params.get("cc", ""), params.get("bcc", ""))
            detail = f"To: {to}"
            if params.get("cc"):
                detail += f"\nCc: {params['cc']}"
            return f"Email sent!\n{detail}\nSubject: {subj}" if ok else "ERROR: Failed to send."

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
