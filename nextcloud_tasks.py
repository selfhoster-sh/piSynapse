"""piSynapse Nextcloud Tasks
CalDAV integration for Nextcloud Tasks (VTODO).
"""

import asyncio
import logging
import threading
import uuid
from datetime import date, datetime

from icalendar import Todo

from utils import retry

logger = logging.getLogger("piSynapse")

# Singleton — reuse client
_client = None
_task_calendar = None
# 30s TTL cache of fetched todos, keyed by the include_completed flag used:
# a pending-only fetch must never be served to show_completed=True (and vice
# versa), so the cached flag must match the request.
_todos_cache: tuple[bool, list] | None = None
_todos_cache_ts: float = 0
# Tasks run in worker threads (asyncio.to_thread); the lock makes the lazy
# singleton creation single-flight across concurrent requests.
_client_lock = threading.Lock()


def _get_dav_client():
    """Return cached CalDAV client."""
    global _client
    from config import NEXTCLOUD_PASSWORD, NEXTCLOUD_TIMEOUT, NEXTCLOUD_URL, NEXTCLOUD_USER
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None
    if _client is None:
        with _client_lock:
            if _client is None:
                import caldav
                caldav_url = f"{NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/"
                _client = caldav.DAVClient(
                    url=caldav_url,
                    username=NEXTCLOUD_USER,
                    password=NEXTCLOUD_PASSWORD,
                    timeout=NEXTCLOUD_TIMEOUT,
                )
    return _client


def _get_task_calendar():
    """Find the first calendar that supports VTODO (tasks)."""
    global _task_calendar
    if _task_calendar is not None:
        return _task_calendar

    client = _get_dav_client()
    if not client:
        return None

    try:
        principal = client.principal()
        calendars = principal.calendars()

        for cal in calendars:
            try:
                components = cal.get_supported_components()
                if "VTODO" in components:
                    _task_calendar = cal
                    return _task_calendar
            except Exception:
                continue

        if calendars:
            _task_calendar = calendars[0]
            return _task_calendar

        return None
    except Exception as e:
        logger.error(f"Failed to find task calendar: {e}")
        return None


def _todo_to_dict(todo) -> dict:
    """Extract a clean dict from a caldav Todo object."""
    try:
        component = getattr(todo, "icalendar_component", None) or todo.icalendar_instance
        # caldav may return the VCALENDAR wrapper — drill into the VTODO
        # child, otherwise every field reads as missing ('Untitled').
        if getattr(component, "name", "") == "VCALENDAR":
            vtodos = [sc for sc in component.subcomponents if sc.name == "VTODO"]
            if vtodos:
                component = vtodos[0]
        summary = str(component.get("SUMMARY", "Untitled"))
        uid = str(component.get("UID", ""))
        status = str(component.get("STATUS", "NEEDS-ACTION"))
        priority = int(component.get("PRIORITY", 0) or 0)
        percent = int(component.get("PERCENT-COMPLETE", 0) or 0)
        description = str(component.get("DESCRIPTION", "") or "")
        categories = component.get("CATEGORIES", "")
        if isinstance(categories, list):
            categories = ", ".join(categories)
        else:
            categories = str(categories) if categories else ""

        due = component.get("DUE")
        due_str = ""
        if due:
            due_val = due.dt if hasattr(due, "dt") else due
            if isinstance(due_val, datetime):
                due_str = due_val.strftime("%Y-%m-%d %H:%M")
            elif isinstance(due_val, date):
                due_str = due_val.strftime("%Y-%m-%d")

        return {
            "uid": uid,
            "summary": summary,
            "status": status,
            "priority": priority,
            "percent": percent,
            "description": description[:500],
            "categories": categories,
            "due": due_str,
            "completed": status == "COMPLETED",
        }
    except Exception as e:
        logger.error(f"Error parsing todo: {e}")
        return {"uid": "?", "summary": "Error parsing task", "status": "UNKNOWN"}


# -- Sync helpers (called via asyncio.to_thread) --

def _calendar_or_config_error() -> str:
    """Explain why the task calendar is unavailable.

    ``_get_task_calendar`` returns None for two very different reasons:
    Nextcloud isn't configured at all (credentials missing) or it is
    configured but no VTODO-capable calendar exists. Reporting the latter
    for the former is misleading — the user would create a calendar they
    can't use.
    """
    if _get_dav_client() is None:
        return "ERROR: Nextcloud not configured. Set NEXTCLOUD_URL and NEXTCLOUD_PASSWORD in settings."
    return "ERROR: No task calendar found. Create a task list in Nextcloud Tasks app first."


@retry(attempts=2, delay=1.0)
def _create_task_sync(summary: str, due: str, priority: int, notes: str) -> str:
    global _todos_cache, _todos_cache_ts
    cal = _get_task_calendar()
    if not cal:
        return _calendar_or_config_error()

    todo = Todo()
    uid = f"{uuid.uuid4()}@pisynapse"
    todo.add("uid", uid)
    todo.add("summary", summary)
    todo.add("dtstart", datetime.now())
    todo.add("dtstamp", datetime.now())
    todo.add("status", "NEEDS-ACTION")
    todo.add("percent-complete", 0)

    if priority:
        todo.add("priority", min(max(priority, 1), 9))
    if notes:
        todo.add("description", notes)
    due_warning = ""
    if due:
        parsed = False
        try:
            due_dt = datetime.fromisoformat(due)
            todo.add("due", due_dt)
            parsed = True
        except ValueError:
            try:
                due_dt = datetime.strptime(due, "%Y-%m-%d")
                todo.add("due", due_dt)
                parsed = True
            except ValueError:
                pass
        if not parsed:
            due_warning = (
                f" Warning: could not parse due date '{due}' — the task was created WITHOUT a due date."
            )

    cal.save_todo(todo)
    # Drop the listing cache so the new task shows up immediately.
    _todos_cache = None
    _todos_cache_ts = 0
    return f"OK Task '{summary}' created.{due_warning}"


def _fetch_todos_cached(include_completed: bool) -> list:
    """Fetch todos via the 30s cache (flag-aware, see module docstring above).

    A failed fetch raises (NOT swallowed): retry fires via @retry and the
    async wrapper reports a real error instead of "No tasks found."
    """
    global _todos_cache, _todos_cache_ts
    import time
    now = time.time()
    if _todos_cache is None or _todos_cache[0] != include_completed or now - _todos_cache_ts > 30:
        _todos_cache = (include_completed, _get_task_calendar().todos(include_completed=include_completed))
        _todos_cache_ts = now
    return _todos_cache[1]


@retry(attempts=2, delay=1.0)
def _list_tasks_sync(show_completed: bool) -> tuple[str, list[dict]]:
    """Build the numbered task listing.

    Returns ``(display_text, items)`` where ``items`` are the task dicts in
    the exact order they are numbered in ``display_text`` (the model only
    sees list positions; real UIDs never appear in tool output).
    """
    global _todos_cache, _todos_cache_ts
    cal = _get_task_calendar()
    if not cal:
        return _calendar_or_config_error(), []

    todos = _fetch_todos_cached(show_completed)

    if not todos:
        return "No tasks found.", []

    tasks = []
    for t in todos:
        d = _todo_to_dict(t)
        if not show_completed and d.get("completed"):
            continue
        tasks.append(d)

    if not tasks:
        return "No pending tasks." if not show_completed else "No tasks found.", []

    lines = [" Tasks:\n"]
    for i, t in enumerate(tasks, 1):
        status_icon = "x" if t["completed"] else "o"
        lines.append(f"   {i}. [{status_icon}] {t['summary']}")
        meta = []
        if t["due"]:
            meta.append(f"Due: {t['due']}")
        if t["priority"]:
            meta.append(f"P: {t['priority']}")
        if t["categories"]:
            meta.append(f"Tags: {t['categories']}")
        if meta:
            lines.append(f"      {' | '.join(meta)}")
        desc = t.get("description", "")
        if desc:
            lines.append(f"      Notes: {desc[:120]}")
        lines.append("")

    return "\n".join(lines), tasks


@retry(attempts=2, delay=1.0)
def _complete_task_sync(uid_prefix: str) -> str:
    global _todos_cache, _todos_cache_ts
    cal = _get_task_calendar()
    if not cal:
        return _calendar_or_config_error()

    # A failed fetch raises (NOT swallowed): retry fires via @retry and the
    # async wrapper reports a real error instead of "not found".
    todos = cal.todos()

    for t in todos:
        d = _todo_to_dict(t)
        if d["uid"].startswith(uid_prefix) and not d["completed"]:
            t.complete()
            _todos_cache = None
            _todos_cache_ts = 0
            return f"OK '{d['summary']}' marked as done."

    return f"Task with UID '{uid_prefix}' not found or already completed."


@retry(attempts=2, delay=1.0)
def _delete_task_sync(uid_prefix: str) -> str:
    global _todos_cache, _todos_cache_ts
    cal = _get_task_calendar()
    if not cal:
        return _calendar_or_config_error()

    # A failed fetch raises (NOT swallowed): retry fires via @retry and the
    # async wrapper reports a real error instead of "not found".
    todos = cal.todos()

    for t in todos:
        d = _todo_to_dict(t)
        if d["uid"].startswith(uid_prefix):
            t.delete()
            _todos_cache = None
            _todos_cache_ts = 0
            return f"OK '{d['summary']}' deleted."

    return f"Task with UID '{uid_prefix}' not found."


@retry(attempts=2, delay=1.0)
def _search_tasks_sync(query: str) -> tuple[str, list[dict]]:
    """Search tasks by summary/description — same contract as ``_list_tasks_sync``."""
    global _todos_cache, _todos_cache_ts
    cal = _get_task_calendar()
    if not cal:
        return _calendar_or_config_error(), []

    todos = _fetch_todos_cached(False)

    q = query.lower()
    matches = []
    for t in todos:
        d = _todo_to_dict(t)
        if q in d.get("summary", "").lower() or q in d.get("description", "").lower():
            matches.append(d)

    if not matches:
        return f"'{query}' not found in tasks.", []

    lines = [f" Search Results for '{query}':\n"]
    for i, t in enumerate(matches[:10], 1):
        status_icon = "x" if t["completed"] else "o"
        lines.append(f"   {i}. [{status_icon}] {t['summary']}")
        meta = []
        if t["due"]:
            meta.append(f"Due: {t['due']}")
        if meta:
            lines.append(f"      {' | '.join(meta)}")
        lines.append("")

    return "\n".join(lines), matches[:10]


# -- Async wrappers (for FastAPI / tool dispatcher) --

async def create_task(summary: str, due: str = "", priority: int = 0, notes: str = "") -> str:
    try:
        return await asyncio.to_thread(_create_task_sync, summary, due, priority, notes)
    except Exception as e:
        logger.error(f"Tasks Error: {e}")
        return "ERROR: Failed to create task."


async def list_tasks(show_completed: bool = False) -> tuple[str, list[dict]]:
    try:
        return await asyncio.to_thread(_list_tasks_sync, show_completed)
    except Exception as e:
        logger.error(f"Tasks Error: {e}")
        return "ERROR: Failed to list tasks.", []


async def complete_task(uid_prefix: str) -> str:
    try:
        return await asyncio.to_thread(_complete_task_sync, uid_prefix)
    except Exception as e:
        logger.error(f"Tasks Error: {e}")
        return "ERROR: Failed to complete task."


async def delete_task(uid_prefix: str) -> str:
    try:
        return await asyncio.to_thread(_delete_task_sync, uid_prefix)
    except Exception as e:
        logger.error(f"Tasks Error: {e}")
        return "ERROR: Failed to delete task."


async def search_tasks(query: str) -> tuple[str, list[dict]]:
    try:
        return await asyncio.to_thread(_search_tasks_sync, query)
    except Exception as e:
        logger.error(f"Tasks Error: {e}")
        return "ERROR: Failed to search tasks.", []
