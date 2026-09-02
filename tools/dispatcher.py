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


def is_tool_success(result: str | tuple) -> bool:
    """Classify a tool result for audit logging.

    Tool handlers contractually prefix genuine failures with "ERROR"; an
    empty result is never a success (a blank answer must not be counted as
    a successful tool call in the audit log). "CLARIFY_REQUIRED" outcomes —
    the chip/quick-action guard that makes the model ask the user for more
    details instead of executing — are likewise NOT a success: nothing was
    created or modified. A "NOOP" result — the target already absent, so the
    mutation was an idempotent no-op (e.g. deleting/updating a note that no
    longer exists) — is also NOT a success: nothing changed. Accepts either
    the raw result string or the ``(result_string, entity_id)`` tuple from
    ``run_tool``.
    """
    if isinstance(result, tuple):
        result = result[0]
    if not result:
        return False
    return not result.startswith("ERROR") and not result.startswith("CLARIFY_REQUIRED") \
        and not result.startswith("NOOP")


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


_SENSITIVE_PARAM_KEYS = ("password", "token", "secret", "credential", "authorization", "api_key")


def _mask_params_for_log(params: dict) -> str:
    """Redact credentials before writing tool params to INFO logs.

    E-mail/CalDAV/IMAP passwords, API tokens and secret keys are masked and
    long values truncated so the request log never persists secret material.
    """
    out = {}
    for k, v in params.items():
        if any(s in k.lower() for s in _SENSITIVE_PARAM_KEYS):
            out[k] = "[REDACTED]"
        else:
            out[k] = v
    return str(out)[:200]


async def run_tool(name: str, params: dict, context: dict | None = None) -> tuple[str, str | int | None]:
    """Route a tool call to the appropriate handler and return (result_string, entity_id)."""
    context = context or {}
    user_text = (context.get("_user_text") or "").strip()
    chip_origin = (context.get("_origin") == "chip")
    logger.info("Tool call: %s params=%s", name, _mask_params_for_log(params))

    if name == "get_datetime":
        return f"Current: {datetime.now().strftime('%d %B %Y, %A, %H:%M')}", None

    if name == "get_weather":
        from weather import get_weather
        return await get_weather(params.get("city", "")), None

    if name in {"create_calendar_event", "list_calendar_events", "update_calendar_event", "delete_calendar_event", "find_free_slots"}:
        session_id = context.get("session_id", "")
        from prompt import cache_calendar_context
        try:
            if name == "create_calendar_event":
                if chip_origin:
                    return ("CLARIFY_REQUIRED: Quick-action request without details. Ask the user "
                            "ONE short question (in their language): what is the event about, and "
                            "when does it start (date and time)? "
                            "Do not call create_calendar_event again until they answer."), None
                from calendar_ops import create_event
                st = params.get("start_time")
                summary = (params.get("summary") or "").strip()
                missing = [w for w, v in (("a title", summary), ("a start time", st)) if not v]
                if missing:
                    # Chip flow guard: never create "New Event" junk.
                    return ("CLARIFY_REQUIRED: The event request is missing "
                            + " and ".join(missing) + ". Ask the user ONE short question "
                            "(in their language) for exactly those details. "
                            "Do not call create_calendar_event again until they answer. "
                            f'The user\'s original message: "{user_text}"'), None
                dur = _safe_int(params.get("duration_minutes", 60), 60, "duration_minutes", min_value=1)
                result, uid = await asyncio.to_thread(
                    create_event,
                    summary,
                    st,
                    dur,
                    all_day=bool(params.get("all_day")),
                    rrule=params.get("rrule") or None,
                )
                # Attach UID to result for verification
                return result, uid
            elif name == "list_calendar_events":
                from calendar_ops import list_events
                days = _safe_int(params.get("days_ahead", 7), 7, "days_ahead", min_value=1)
                raw, events = await asyncio.to_thread(list_events, days)
                if not raw.startswith("ERROR") and session_id:
                    await cache_calendar_context(session_id, events)
                return raw, None
            elif name == "update_calendar_event":
                from calendar_ops import update_event
                s = params.get("summary", "")
                if not s:
                    return "ERROR: Event name required.", None
                new_s = params.get("new_summary", "")
                new_t = params.get("new_start_time", "")
                new_d = _safe_int(params.get("new_duration_minutes", 0), 0, "new_duration_minutes")
                uid_ref = params.get("event_uid", "")
                uid = ""
                if uid_ref:
                    uid = await _resolve_position(session_id, uid_ref, _get_context_fn("calendar"), id_field="uid")
                    if uid is None:
                        return f"ERROR: Event '{uid_ref}' not found. Run list_calendar_events first to see available events.", None
                return await asyncio.to_thread(update_event, s, new_summary=new_s, new_start_time=new_t, new_duration_minutes=new_d, event_uid=uid), uid
            elif name == "delete_calendar_event":
                from calendar_ops import delete_event
                s = params.get("summary")
                if not s:
                    return "ERROR: Event name required.", None
                uid_ref = params.get("event_uid", "")
                uid = ""
                if uid_ref:
                    uid = await _resolve_position(session_id, uid_ref, _get_context_fn("calendar"), id_field="uid")
                    if uid is None:
                        return f"ERROR: Event '{uid_ref}' not found. Run list_calendar_events first to see available events.", None
                return await asyncio.to_thread(delete_event, s, event_uid=uid), uid
            elif name == "find_free_slots":
                from calendar_ops import find_free_slots
                date_str = params.get("date", "")
                if not date_str:
                    return "ERROR: date required (YYYY-MM-DD).", None
                dur = _safe_int(params.get("duration_minutes", 60), 60, "duration_minutes", min_value=1)
                day_start = params.get("day_start", "09:00")
                day_end = params.get("day_end", "18:00")
                raw, _ = await asyncio.to_thread(find_free_slots, date_str, dur, day_start, day_end)
                return raw, None
        except ValueError as e:
            return f"ERROR: {e}", None
        except Exception as e:
            logger.error(f"Nextcloud Error: {e}")
            return "ERROR: Calendar operation failed. Check server logs.", None

    if name in {"list_emails", "read_email", "send_email", "search_emails"}:
        # _run_mail_tool already returns (result_string, entity_id)
        return await _run_mail_tool(name, params, context.get("session_id", ""), context.get("_user_text", ""), chip_origin)

    if name == "save_memory":
        content = (params.get("content") or "").strip()
        if not content:
            return "ERROR: content required.", None
        # Guard against meta-requests being stored as memories: a description
        # of what the user just asked ("user wants to see notes") is not a
        # durable fact about the user. Seen in the wild once; never again.
        import re as _re
        if _re.search(r"(?i)\b(iste\u011fi|istegi|istemi|talebi)\b|\brequest (to|for|that)\b|\b(ask(ed)?|wants?|trying) (him|her|them|us|me)? ?(to|that)\b", content):
            logger.warning(f"save_memory rejected meta-content: {content!r}")
            return ("ERROR: That describes a request, not a durable fact about the user. "
                    "Memories must outlive the conversation (preferences, habits, personal info). "
                    "Do not retry saving this; simply fulfill the user's actual request."), None
        from db import save_memory
        importance = params.get("importance", 5)
        try:
            importance = max(1, min(10, int(importance)))
        except (ValueError, TypeError):
            importance = 5
        result, rowid = await save_memory(
            content=content,
            category=params.get("category", "general"),
            importance=importance,
            user_id=context.get("user_id"),
        )
        return result, rowid

    if name in {"create_note", "list_notes", "read_note", "update_note", "delete_note", "search_notes"}:
        return await _run_notes_tool(name, params, context.get("session_id", ""), context.get("_user_text", ""), chip_origin)

    if name in {"create_task", "list_tasks", "complete_task", "delete_task", "search_tasks"}:
        # _run_tasks_tool already returns (result_string, entity_id)
        return await _run_tasks_tool(name, params, context.get("session_id", ""), context.get("_user_text", ""), chip_origin)

    return "ERROR: Tool not found.", None


async def _run_notes_tool(name: str, params: dict, session_id: str = "", user_text: str = "", chip_origin: bool = False) -> tuple[str, int | None]:
    """Dispatch note tool calls with session-aware ID resolution.

    Returns the ``(result_text, entity_id)`` tuple the verification hook
    expects: create/update/delete all produce their note id so the backend can
    re-read (or, for deletes, confirm absence of) the entity.
    """
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
            if chip_origin:
                return ("CLARIFY_REQUIRED: Quick-action request without details. Ask the user "
                        "ONE short question (in their language): what should the note say? "
                        "Do not call create_note again until they answer."), None
            title = params.get("title", "").strip()
            content = (params.get("content") or "").strip()
            if not title:
                return "ERROR: title required.", None
            if not content:
                # Chip flow guard: never save an empty/placeholder note —
                # the model must ask the user for the content first.
                return ("CLARIFY_REQUIRED: The note has no content. Ask the user ONE short "
                        "question (in their language) about what to write in the note. "
                        "Do not call create_note again until they answer. "
                        f'The user\'s original message: "{user_text}"'), None
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
            return raw, None
        elif name == "read_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required.", None
            resolved = await _resolve_position(session_id, nid, _get_context_fn("notes"), id_field="id")
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes.", None
            return await get_note(resolved), None
        elif name == "update_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required.", None
            resolved = await _resolve_position(session_id, nid, _get_context_fn("notes"), id_field="id")
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes.", None
            result = await update_note(
                resolved,
                title=params.get("title"),
                content=params.get("content"),
                category=params.get("category"),
                tags=params.get("tags"),
            )
            return result, resolved
        elif name == "delete_note":
            nid = params.get("note_id")
            if not nid:
                return "ERROR: note_id required.", None
            resolved = await _resolve_position(session_id, nid, _get_context_fn("notes"), id_field="id")
            if resolved is None:
                return f"ERROR: Note '{nid}' not found. Run list_notes first to see available notes.", None
            result = await delete_note(resolved)
            return result, resolved
        elif name == "search_notes":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required.", None
            raw, items = await _search_notes_raw(q)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_notes_context
                await cache_notes_context(session_id, items)
            return raw, None
    except Exception as e:
        logger.error(f"Notes Error: {e}")
        return "ERROR: Notes operation failed. Check server logs.", None

    return "ERROR: Tool not found.", None


async def _run_tasks_tool(name: str, params: dict, session_id: str = "", user_text: str = "", chip_origin: bool = False) -> tuple[str, str | int | None]:
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
            if chip_origin:
                return ("CLARIFY_REQUIRED: Quick-action request without details. Ask the user "
                        "ONE short question (in their language): what is the task, and when is it due? "
                        "Do not call create_task again until they answer."), None
            summary = params.get("summary", "").strip()
            if not summary:
                # Chip flow guard: no empty/placeholder tasks.
                return ("CLARIFY_REQUIRED: The task has no text. Ask the user ONE short "
                        "question (in their language) about what the task should be. "
                        "Do not call create_task again until they answer. "
                        f'The user\'s original message: "{user_text}"'), None
            priority = _safe_int(params.get("priority", 0), 0, "priority")
            result, uid = await create_task(
                summary=summary,
                due=params.get("due", ""),
                priority=priority,
                notes=params.get("notes", ""),
            )
            return result, uid
        elif name == "list_tasks":
            show_completed = _as_bool(params.get("show_completed", False))
            raw, items = await _list_tasks_raw(show_completed=show_completed)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_tasks_context
                await cache_tasks_context(session_id, items)
            return raw, None
        elif name == "complete_task":
            uid = params.get("uid")
            uid = str(uid).strip() if uid is not None else ""
            if not uid:
                return "ERROR: uid required.", None
            resolved = await _resolve_position(session_id, uid, _get_context_fn("tasks"), id_field="uid")
            if resolved is None:
                return f"ERROR: Task '{uid}' not found. Run list_tasks first to see available tasks.", None
            result = await complete_task(resolved)
            return result, resolved
        elif name == "delete_task":
            uid = params.get("uid")
            uid = str(uid).strip() if uid is not None else ""
            if not uid:
                return "ERROR: uid required.", None
            resolved = await _resolve_position(session_id, uid, _get_context_fn("tasks"), id_field="uid")
            if resolved is None:
                return f"ERROR: Task '{uid}' not found. Run list_tasks first to see available tasks.", None
            result = await delete_task(resolved)
            return result, resolved
        elif name == "search_tasks":
            q = params.get("query", "").strip()
            if not q:
                return "ERROR: query required.", None
            raw, items = await _search_tasks_raw(q)
            if not raw.startswith("ERROR") and session_id:
                from prompt import cache_tasks_context
                await cache_tasks_context(session_id, items)
            return raw, None
    except ValueError as e:
        return f"ERROR: {e}", None
    except Exception as e:
        logger.error(f"Task tool {name} failed: {e}")
        return f"ERROR: {name} failed", None

    return "ERROR: Tool not found.", None


async def _run_mail_tool(name: str, params: dict, session_id: str = "", user_text: str = "", chip_origin: bool = False) -> tuple[str, str | int | None]:
    """Dispatch email tool calls to the active mail client."""
    from mail import get_active_mail_client
    from prompt import cache_email_context

    mc = get_active_mail_client()
    if not mc:
        return "ERROR: Mail connection failed. Check .env configuration.", None

    account_id = 1
    mailbox_id = params.get("mailbox", "INBOX")

    try:
        if name == "list_emails":
            limit = _safe_int(params.get("limit", 10), 10, "limit", min_value=1)
            msgs = await mc.get_messages(account_id, mailbox_id, limit)
            if not msgs:
                return "Inbox is empty.", None
            if session_id:
                await cache_email_context(session_id, msgs)
            lines = [f" Recent Emails (showing {len(msgs)}):"]
            for m in msgs:
                bp = (m.get("body", "") or "").replace("\n", " ")[:150]
                lines.append(
                    f"From: {m.get('from', '?')} | Subject: {m.get('subject', '(no subject)')} "
                    f"| Date: {m.get('date', '?')} | Preview: {bp}"
                )
            return "\n".join(lines), None

        elif name == "read_email":
            mid = params.get("message_id") or params.get("id")
            if not mid:
                return "ERROR: message_id required.", None
            resolved = await _resolve_position(session_id, mid, _get_context_fn("email"), id_field="id")
            if resolved is None:
                return "ERROR: Email not found. Run list_emails first to get the current listing.", None
            m = await mc.get_message(account_id, mailbox_id, resolved)
            if not m:
                return "ERROR: Email not found.", None
            return (f"Email Details\n\nFrom: {m.get('from', '?')}\n"
                    f"Subject: {m.get('subject', '?')}\nDate: {m.get('date', '?')}\n\n"
                    f"Content:\n{m.get('body', '')[:1500]}"), None

        elif name == "send_email":
            if chip_origin:
                return ("CLARIFY_REQUIRED: Quick-action request without details. Ask the user ONE "
                        "short question (in their language) covering: recipient address, subject, "
                        "and message. Do not call send_email again until they answer all three."), None
            to, subj, body = params.get("to"), params.get("subject"), params.get("body")
            missing = [w for w, v in (("the recipient", to), ("a subject", subj), ("the message body", body)) if not v]
            if missing:
                # Chip flow guard: never send or half-fill an email.
                return ("CLARIFY_REQUIRED: The email request is missing "
                        + " and ".join(missing) + ". Ask the user ONE short question "
                        "(in their language) for exactly those parts. "
                        "Do not call send_email again until they answer. "
                        f'The user\'s original message: "{user_text}"'), None
            ok = await mc.send_message(account_id, to, subj, body, params.get("cc", ""), params.get("bcc", ""))
            detail = f"To: {to}"
            if params.get("cc"):
                detail += f"\nCc: {params['cc']}"
            return (f"Email sent!\n{detail}\nSubject: {subj}" if ok else "ERROR: Failed to send."), None

        elif name == "search_emails":
            q = params.get("query")
            if not q:
                return "ERROR: 'query' required.", None
            limit = _safe_int(params.get("limit", 10), 10, "limit", min_value=1)
            results = await mc.search_messages(account_id, q, limit, mailbox_id)
            if not results:
                return f"'{q}' no results found.", None
            if session_id:
                await cache_email_context(session_id, results)
            lines = [f"'{q}' Results ({len(results)}):"]
            for m in results:
                bp = (m.get("body", "") or "").replace("\n", " ")[:150]
                lines.append(
                    f"From: {m.get('from', '?')} | Subject: {m.get('subject', '(no subject)')} "
                    f"| Preview: {bp}"
                )
            return "\n".join(lines), None

        # Unknown mail tool
        return "ERROR: Tool not found.", None

    except ValueError as e:
        return f"ERROR: {e}", None
    except Exception as e:
        logger.error(f"Mail Error: {e}")
        return "ERROR: Mail operation failed. Check server logs.", None
