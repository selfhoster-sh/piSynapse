"""Tool verification hook.

Invoked after every completed tool call inside the tool-call loops
(llm/stream.py and llm/chat.py) and the manual routes (routers/chat.py).
For the create/update/delete tools in VERIFY_SCOPE, performs real backend
verification: the dispatcher carries a structured ``(result_string,
entity_id)`` tuple (UID / rowid returned by the create call, or the resolved
id used by the update/delete), and here the entity is re-read from the
backend to confirm the write actually landed (creates/updates) or the entity
actually disappeared (deletes — verification is inverted: absence proves
the deletion).

``verification_status`` values written to the audit log:
    "verified"              ID-based re-read confirmed the expected state
                            (entity present for creates/updates, absent for
                            deletes) — the authoritative signal.
    "verified_by_fallback"  ID unavailable -> content/summary match only
                            (low confidence; NOT a trustworthy positive).
    "unverified"            No ID and fallback match failed.
    "verification_failed"   ID present but backend re-read contradicts the
                            expected state (missing entity after create, or
                            still-present entity after delete).
    None                    Tool not in the verification scope, or the
                            tool call itself failed (nothing to verify).

Never raises: any failure inside verification is logged and swallowed so it
can never break or stall the tool-call loop.
"""
import asyncio
import logging

from db import log_tool_call

logger = logging.getLogger("piSynapse")

# Tools whose create/update/delete outcome is verified against the real
# backend. A tool only lands here when the dispatcher can hand out a
# structured entity id (or a reliable fallback exists).
VERIFY_SCOPE = {
    "create_task",
    "create_calendar_event",
    "save_memory",
    # D-2: notes trio (create_note/update_note/delete_note)
    "create_note",
    "update_note",
    "delete_note",
    # D-2: task mutations beyond create
    "complete_task",
    "delete_task",
    # D-2: calendar mutations beyond create (dispatcher already returned uid)
    "update_calendar_event",
    "delete_calendar_event",
}

# Delete verification is INVERTED: the desired post-state is the entity being
# absent from the backend, not present.
_DELETE_TOOLS = {"delete_note", "delete_task", "delete_calendar_event"}


async def run_verification(
    tool_name: str,
    params: dict,
    result: str,
    success: bool,
    *,
    entity_id: str | int | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
) -> tuple[int | None, str | None]:
    """Verify a completed tool call and record it in the audit log.

    Deliberately async: the loops are async, and verification may need
    non-blocking I/O (the SQLite audit write and the backend re-read).
    Awaited at the call site so verification runs in order, right after the
    tool completes.

    Never raises: any failure inside verification (including DB errors) is
    logged and swallowed so it can never break or stall the tool-call loop.

    Returns a ``(audit_id, verification_status)`` tuple: ``audit_id`` is the
    audit_log id the UI attaches its correction to, and
    ``verification_status`` is the computed status the frontend needs to
    distinguish a claimed success (the ``is_tool_success`` heuristic) from a
    backend-verified one. Both are None when the audit write failed or
    verification was not applicable.

    Args:
        tool_name: Name of the tool that ran (e.g. "create_task").
        params: The parsed arguments the tool received.
        result: The result string returned by the tool.
        success: True if the tool completed without an error, False otherwise.
        entity_id: Structured ID returned by the dispatcher (UID or rowid).
        duration_ms: Wall-clock duration of the tool call, in milliseconds.
        error: Error text when the tool failed (None when successful).
    """
    try:
        verification_status = await _verify(tool_name, params, result, success, entity_id)
        audit_id = await log_tool_call(
            tool_name,
            params,
            success,
            duration_ms=duration_ms,
            error=error,
            verification_status=verification_status,
        )
        return audit_id, verification_status
    except Exception as e:
        logger.warning(f"Verification hook failed for tool '{tool_name}': {e}")
        return None, None


async def _verify(
    tool_name: str,
    params: dict,
    result: str,
    success: bool,
    entity_id: str | int | None,
) -> str | None:
    """Compute the verification status for a finished tool call.

    Only tools in VERIFY_SCOPE are verified (other calls return None).
    A failed tool call has nothing to verify. When an ID is available it is
    authoritative; the content/summary fallback is used only when the ID is
    missing and is always marked ``verified_by_fallback``. For delete tools
    both paths check ABSENCE (the entity must no longer exist anywhere).
    """
    if tool_name not in VERIFY_SCOPE:
        return None
    if not success:
        return None
    try:
        if entity_id is not None and entity_id != "":
            confirmed = await _confirm_by_id(tool_name, entity_id, params)
            return "verified" if confirmed else "verification_failed"
        matched = await _fallback_match(tool_name, params)
        return "verified_by_fallback" if matched else "unverified"
    except Exception as e:
        logger.warning(f"Verification for tool '{tool_name}' failed: {e}")
        return "verification_failed" if (entity_id is not None and entity_id != "") else "unverified"


async def _confirm_by_id(tool_name: str, entity_id: str | int, params: dict) -> bool:
    """Re-read the mutated entity and match on ID.

    Returns True when the backend holds the state the tool claimed to produce:
    creates/updates → entity present; deletes → entity absent (inverted).
    """
    if tool_name == "create_task":
        from nextcloud_tasks import list_tasks

        _, items = await list_tasks(show_completed=True)
        return any(str(item.get("uid")) == str(entity_id) for item in items)

    if tool_name == "complete_task":
        from nextcloud_tasks import list_tasks

        _, items = await list_tasks(show_completed=True)
        # The completion must have landed: the task is still present AND
        # reported as completed.
        return any(
            str(item.get("uid")) == str(entity_id) and bool(item.get("completed"))
            for item in items
        )

    if tool_name == "delete_task":
        from nextcloud_tasks import list_tasks

        _, items = await list_tasks(show_completed=True)
        return not any(str(item.get("uid")) == str(entity_id) for item in items)

    if tool_name in ("create_calendar_event", "update_calendar_event"):
        from calendar_ops import list_events

        _, items = await asyncio.to_thread(list_events, 30)
        return any(str(item.get("uid")) == str(entity_id) for item in items)

    if tool_name == "delete_calendar_event":
        from calendar_ops import list_events

        _, items = await asyncio.to_thread(list_events, 30)
        return not any(str(item.get("uid")) == str(entity_id) for item in items)

    if tool_name == "save_memory":
        from db import get_db

        db = await get_db()
        async with db.execute("SELECT id FROM memories WHERE id = ?", (entity_id,)) as cur:
            return await cur.fetchone() is not None

    if tool_name in ("create_note", "update_note"):
        from nextcloud_notes import list_notes

        _, items = await list_notes()
        return any(str(item.get("id")) == str(entity_id) for item in items)

    if tool_name == "delete_note":
        from nextcloud_notes import list_notes

        _, items = await list_notes()
        return not any(str(item.get("id")) == str(entity_id) for item in items)

    return False


async def _fallback_match(tool_name: str, params: dict) -> bool:
    """Content/summary match used only when the ID is unavailable."""
    if tool_name == "create_task":
        from nextcloud_tasks import search_tasks

        summary = (params.get("summary") or "").strip()
        if not summary:
            return False
        _, items = await search_tasks(summary)
        return bool(items)

    if tool_name == "complete_task":
        from nextcloud_tasks import list_tasks

        _, items = await list_tasks(show_completed=True)
        uid = str(params.get("uid") or "").strip()
        if not uid:
            return False
        return any(str(item.get("uid")) == uid and bool(item.get("completed")) for item in items)

    if tool_name == "delete_task":
        from nextcloud_tasks import list_tasks

        _, items = await list_tasks(show_completed=True)
        uid = str(params.get("uid") or "").strip()
        if not uid:
            return False
        return not any(str(item.get("uid")) == uid for item in items)

    if tool_name in ("create_calendar_event", "update_calendar_event"):
        from calendar_ops import list_events

        summary = (params.get("new_summary") or params.get("summary") or "").strip().lower()
        if not summary:
            return False
        _, items = await asyncio.to_thread(list_events, 30)
        return any(item.get("summary", "").strip().lower() == summary for item in items)

    if tool_name == "delete_calendar_event":
        from calendar_ops import list_events

        summary = (params.get("summary") or "").strip().lower()
        if not summary:
            return False
        _, items = await asyncio.to_thread(list_events, 30)
        return not any(item.get("summary", "").strip().lower() == summary for item in items)

    if tool_name == "save_memory":
        from db import get_db

        content = (params.get("content") or "").strip()
        if not content:
            return False
        db = await get_db()
        async with db.execute(
            "SELECT COUNT(*) FROM memories WHERE content = ?", (content,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row[0] > 0)

    if tool_name == "create_note":
        from nextcloud_notes import list_notes

        title = (params.get("title") or "").strip()
        content = (params.get("content") or "").strip()
        if not title:
            return False
        _, items = await list_notes()
        for item in items:
            if (item.get("title") or "").strip().lower() == title.lower():
                return True
        return bool(content) and any(
            (item.get("content") or "").strip() == content for item in items
        )

    if tool_name == "update_note":
        from nextcloud_notes import list_notes

        title = (params.get("title") or "").strip()
        content = (params.get("content") or "").strip()
        if not content and not title:
            return False
        _, items = await list_notes()
        for item in items:
            if content and (item.get("content") or "").strip() == content:
                return True
            if not content and title and (item.get("title") or "").strip().lower() == title.lower():
                return True
        return False

    if tool_name == "delete_note":
        from nextcloud_notes import list_notes

        title = (params.get("title") or "").strip()
        content = (params.get("content") or "").strip()
        _, items = await list_notes()
        for item in items:
            if content and (item.get("content") or "").strip() == content:
                return False
            if title and (item.get("title") or "").strip().lower() == title.lower():
                return False
        return True  # nothing matches the deleted note → gone

    return False
