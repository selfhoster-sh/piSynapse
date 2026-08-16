"""piSynapse Tools — Tool Dispatcher
"""

import asyncio
import logging
from datetime import datetime

from .definitions import _as_bool, _safe_int

logger = logging.getLogger("piSynapse")


def is_tool_success(result: str) -> bool:
    """Classify a tool result string for audit logging.

    Tool handlers contractually prefix genuine failures with "ERROR"; an
    empty result is never a success (a blank answer must not be counted as
    a successful tool call in the audit log).
    """
    return bool(result) and not result.startswith("ERROR")


async def _resolve_email_id(session_id: str, ref) -> str | None:
    """Resolve a 1-based list position to the real email ID for this session.

    The model only ever sees numbered list items (never raw IDs). If ``ref``
    is a number that fits the persisted listing, map it to the stored ID.
    A numeric reference that does NOT fit the listing is refused (None):
    guessing a raw IMAP UID could silently read the wrong message. Raw
    non-numeric IDs (legacy direct calls) pass through unchanged.
    """
    from prompt import get_email_context

    emails = await get_email_context(session_id)
    is_num = isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit())
    if is_num:
        if emails and 1 <= int(ref) <= len(emails):
            return emails[int(ref) - 1].get("id")
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
                return await asyncio.to_thread(list_events, days)
            elif name == "update_calendar_event":
                from calendar_ops import update_event
                s = params.get("summary", "")
                if not s:
                    return "ERROR: Event name required."
                new_s = params.get("new_summary", "")
                new_t = params.get("new_start_time", "")
                new_d = _safe_int(params.get("new_duration_minutes", 0), 0, "new_duration_minutes")
                uid = params.get("event_uid", "")
                return await asyncio.to_thread(update_event, s, new_summary=new_s, new_start_time=new_t, new_duration_minutes=new_d, event_uid=uid)
            elif name == "delete_calendar_event":
                from calendar_ops import delete_event
                s = params.get("summary")
                if not s:
                    return "ERROR: Event name required."
                uid = params.get("event_uid", "")
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
        await save_memory(
            content=content,
            category=params.get("category", "general"),
            user_id=context.get("user_id"),
        )
        return "Memory saved."

    if name in {"create_note", "list_notes", "read_note", "update_note", "delete_note", "search_notes"}:
        return await _run_notes_tool(name, params)

    if name in {"create_task", "list_tasks", "complete_task", "delete_task", "search_tasks"}:
        return await _run_tasks_tool(name, params)

    return "ERROR: Tool not found."


async def _run_notes_tool(name: str, params: dict) -> str:
    """Dispatch note tool calls."""
    from nextcloud_notes import create_note, delete_note, get_note, list_notes, search_notes, update_note

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
            return await list_notes()
        elif name == "read_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            try:
                nid = int(nid)
            except (ValueError, TypeError):
                return f"ERROR: Invalid note_id '{nid}'. Must be a number (e.g. 284)."
            return await get_note(nid)
        elif name == "update_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            try:
                nid = int(nid)
            except (ValueError, TypeError):
                return f"ERROR: Invalid note_id '{nid}'. Must be a number (e.g. 284)."
            return await update_note(
                nid,
                title=params.get("title"),
                content=params.get("content"),
            )
        elif name == "delete_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required."
            try:
                nid = int(nid)
            except (ValueError, TypeError):
                return f"ERROR: Invalid note_id '{nid}'. Must be a number (e.g. 284)."
            return await delete_note(nid)
        elif name == "search_notes":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required."
            return await search_notes(q)
    except Exception as e:
        logger.error(f"Notes Error: {e}")
        return "ERROR: Notes operation failed. Check server logs."

    return "ERROR: Tool not found."


async def _run_tasks_tool(name: str, params: dict) -> str:
    """Dispatch task tool calls."""
    from nextcloud_tasks import complete_task, create_task, delete_task, list_tasks, search_tasks

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
            return await list_tasks(show_completed=show_completed)
        elif name == "complete_task":
            uid = params.get("uid", "").strip()
            if not uid:
                return "ERROR: uid required."
            return await complete_task(uid)
        elif name == "delete_task":
            uid = params.get("uid", "").strip()
            if not uid:
                return "ERROR: uid required."
            return await delete_task(uid)
        elif name == "search_tasks":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required."
            return await search_tasks(q)
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
            resolved = await _resolve_email_id(session_id, mid)
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
