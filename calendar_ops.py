"""piSynapse Calendar
Nextcloud CalDAV integration for calendar operations.
"""

import logging
import threading
import time
from datetime import datetime, timedelta

from utils import retry

logger = logging.getLogger("piSynapse")

_dav_client = None
_dav_calendar = None
# Guard lazy singleton creation: calendar_ops runs in worker threads
# (asyncio.to_thread), so two concurrent calls could both build a client /
# fetch calendars. The lock makes creation single-flight.
_dav_lock = threading.Lock()

# TTL cache for the calendar widget (list_events_today). The sidebar polls the
# widget frequently while Nextcloud events change rarely; the cache is dropped
# on every calendar write so the widget never goes stale for long.
_TODAY_CACHE_TTL = 300.0  # seconds (~5 min)
_today_cache: tuple[float, list[dict]] | None = None


def _invalidate_today_cache() -> None:
    """Drop cached today's events after a calendar write (create/update/delete)."""
    global _today_cache
    _today_cache = None


def _get_nextcloud_client():
    global _dav_client
    from config import NEXTCLOUD_PASSWORD, NEXTCLOUD_TIMEOUT, NEXTCLOUD_URL, NEXTCLOUD_USER
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None
    if _dav_client is not None:
        return _dav_client
    with _dav_lock:
        if _dav_client is not None:
            return _dav_client
        import caldav
        caldav_url = f"{NEXTCLOUD_URL.rstrip('/')}/remote.php/dav/"
        try:
            _dav_client = caldav.DAVClient(
                url=caldav_url,
                username=NEXTCLOUD_USER,
                password=NEXTCLOUD_PASSWORD,
                timeout=NEXTCLOUD_TIMEOUT,
            )
        except Exception as e:
            logger.error("Failed to create CalDAV client: %s", e)
            raise
        return _dav_client


def _get_primary_calendar(client):
    global _dav_calendar
    if _dav_calendar is not None:
        return _dav_calendar
    with _dav_lock:
        if _dav_calendar is not None:
            return _dav_calendar
        try:
            principal = client.principal()
            calendars = principal.calendars()
        except Exception as e:
            logger.error("Failed to fetch CalDAV calendars: %s", e)
            raise
        if not calendars:
            raise Exception("No calendar found on Nextcloud.")
        _dav_calendar = calendars[0]
        return _dav_calendar


def _get_uid(d) -> str:
    uid = getattr(d, "uid", None)
    if uid and hasattr(uid, "value"):
        return str(uid.value)
    return ""


def _ical_escape_text(value: str) -> str:
    r"""Escape a TEXT value for embedding in an iCalendar (RFC 5545) property.

    Newlines become ``\\n`` (instead of a real line break, which would inject
    a fake property/VEVENT), and backslash/semicolon/comma are escaped so user
    text cannot break out of the field or alter the calendar structure.
    """
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r", "")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def _find_events(search_window_days_back: int = 30, search_window_days_ahead: int = 90):
    """Return all events in the search window."""
    try:
        client = _get_nextcloud_client()
        if not client:
            return None
        calendar = _get_primary_calendar(client)
        events = calendar.date_search(
            datetime.now() - timedelta(days=search_window_days_back),
            datetime.now() + timedelta(days=search_window_days_ahead),
        )
        return events
    except Exception as e:
        logger.error("Failed to search calendar events: %s", e)
        return None


def _match_event(events, summary: str, event_uid: str = "") -> tuple:
    """Find an event by UID (exact) or summary (substring).

    Returns ``(event, matched_summary, status)`` where status is ``""`` on a
    unique match, ``"not_found"``, ``"ambiguous"`` (more than one event
    matched — never auto-picks) or ``"error"``.
    """
    try:
        def _matches() -> list:
            found = []
            for ev in events:
                d = ev.vobject_instance.vevent
                if event_uid:
                    uid = _get_uid(d)
                    if uid == event_uid or uid.startswith(event_uid):
                        found.append((ev, getattr(d, "summary", "").value))
                else:
                    s = getattr(d, "summary", "").value
                    if summary.lower() in s.lower():
                        found.append((ev, s))
            return found

        matches = _matches()
        if not matches:
            return None, None, "not_found"
        if len(matches) > 1:
            labels = ", ".join(f"'{s}'" for _, s in matches[:5])
            logger.warning(
                "Ambiguous calendar match for %r (%d events: %s)",
                event_uid or summary, len(matches), labels,
            )
            return None, None, "ambiguous"
        ev, s = matches[0]
        return ev, s, ""
    except Exception as e:
        logger.error("Failed to match calendar event: %s", e)
        return None, None, "error"


@retry(attempts=2, delay=1.0)
def create_event(summary: str, start_time_str: str, duration_minutes: int = 60) -> str:
    try:
        client = _get_nextcloud_client()
        if not client:
            return "ERROR: Nextcloud credentials missing."
        calendar = _get_primary_calendar(client)
        start_dt = datetime.fromisoformat(start_time_str)
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        ical = "\r\n".join([
            "BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//piSynapse//EN",
            "BEGIN:VEVENT",
            f"SUMMARY:{_ical_escape_text(summary)}",
            f"DTSTART;VALUE=DATE-TIME:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;VALUE=DATE-TIME:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            "END:VEVENT", "END:VCALENDAR",
        ]) + "\r\n"
        calendar.add_event(ical)
        _invalidate_today_cache()
        return f"OK '{summary}' added to calendar."
    except Exception as e:
        logger.error("Failed to create calendar event '%s': %s", summary, e)
        return f"ERROR: Could not create event '{summary}'."


@retry(attempts=2, delay=1.0)
def list_events(days_ahead: int = 7) -> str:
    try:
        client = _get_nextcloud_client()
        if not client:
            return "ERROR: Nextcloud credentials missing."
        calendar = _get_primary_calendar(client)
        start = datetime.now()
        end = start + timedelta(days=days_ahead)
        events = calendar.date_search(start, end)
        if not events:
            return f"Next {days_ahead} days: no events."
        lines = []
        for ev in events:
            d = ev.vobject_instance.vevent
            s = getattr(d, "summary", getattr(d, "description", "Untitled")).value
            st = d.dtstart.value
            ts = st.strftime("%Y-%m-%d %H:%M") if hasattr(st, "strftime") else str(st)
            uid = _get_uid(d)
            line = f"- {ts} | {s}"
            if uid:
                line += f"\n     UID: {uid[:20]}..."
            desc = getattr(d, "description", None)
            if desc and hasattr(desc, "value") and desc.value and desc.value != s:
                line += f"\n     {desc.value[:100]}"
            lines.append(line)
        return "Events:\n" + "\n".join(lines)
    except Exception as e:
        logger.error("Failed to list calendar events: %s", e)
        return "ERROR: Could not load calendar events."


@retry(attempts=2, delay=1.0)
def list_events_today() -> list[dict]:
    """Structured today's events for the widget (TTL-cached, see ``_TODAY_CACHE_TTL``)."""
    global _today_cache
    if _today_cache is not None:
        cached_at, cached = _today_cache
        if time.monotonic() - cached_at < _TODAY_CACHE_TTL:
            return cached
    try:
        from datetime import date
        client = _get_nextcloud_client()
        if not client:
            return []
        calendar = _get_primary_calendar(client)
        today = datetime.combine(date.today(), datetime.min.time())
        tomorrow = today + timedelta(days=1)
        events = calendar.date_search(today, tomorrow)
        result = []
        for ev in events:
            d = ev.vobject_instance.vevent
            s = getattr(d, "summary", "Untitled").value
            st = d.dtstart.value
            ts = st.strftime("%H:%M") if hasattr(st, "strftime") else str(st)
            uid = _get_uid(d)
            result.append({"time": ts, "title": s, "uid": uid})
        result = sorted(result, key=lambda x: x["time"])
        _today_cache = (time.monotonic(), result)
        return result
    except Exception as e:
        logger.error("Failed to list today's events: %s", e)
        return []


def find_events_by_summary(summary: str, days_back: int = 30, days_ahead: int = 90) -> list[dict]:
    """Find calendar events matching summary substring. Returns list of {summary, start, uid} dicts."""
    try:
        client = _get_nextcloud_client()
        if not client:
            return []
        calendar = _get_primary_calendar(client)
        events = calendar.date_search(
            datetime.now() - timedelta(days=days_back),
            datetime.now() + timedelta(days=days_ahead),
        )
        results = []
        for ev in events:
            d = ev.vobject_instance.vevent
            s = getattr(d, "summary", "").value
            if summary.lower() in s.lower():
                st = d.dtstart.value
                ts = st.strftime("%Y-%m-%d %H:%M") if hasattr(st, "strftime") else str(st)
                results.append({"summary": s, "start": ts, "uid": _get_uid(d)})
        return results
    except Exception as e:
        logger.error("Failed to search calendar events for '%s': %s", summary, e)
        return []


@retry(attempts=2, delay=1.0)
def delete_event(summary: str, event_uid: str = "") -> str:
    try:
        client = _get_nextcloud_client()
        if not client:
            return "ERROR: Nextcloud credentials missing."
        events = _find_events()
        if not events:
            return f"ERROR: '{summary}' not found."
        ev, s, status = _match_event(events, summary, event_uid)
        if status == "ambiguous":
            return f"'{summary}' matches multiple events — use a more specific title or the event UID."
        if status == "error":
            return "ERROR: Could not match event."
        if ev is None:
            return f"ERROR: '{summary}' not found."
        ev.delete()
        _invalidate_today_cache()
        return f"OK '{s}' deleted from calendar."
    except Exception as e:
        logger.error("Failed to delete calendar event '%s': %s", summary, e)
        return "ERROR: Could not delete event."


@retry(attempts=2, delay=1.0)
def update_event(summary: str, new_summary: str = "", new_start_time: str = "", new_duration_minutes: int = 0, event_uid: str = "") -> str:
    try:
        client = _get_nextcloud_client()
        if not client:
            return "ERROR: Nextcloud credentials missing."
        events = _find_events()
        if not events:
            return f"ERROR: '{summary}' not found."
        ev, s, status = _match_event(events, summary, event_uid)
        if status == "ambiguous":
            return f"'{summary}' matches multiple events — use a more specific title or the event UID."
        if status == "error":
            return "ERROR: Could not match event."
        if ev is None:
            return f"ERROR: '{summary}' not found."
        d = ev.vobject_instance.vevent

        def _is_date(v) -> bool:
            return isinstance(v, datetime.date) and not isinstance(v, datetime)

        if new_summary:
            d.summary.value = new_summary

        if new_start_time:
            new_dt = datetime.fromisoformat(new_start_time)
            old_dt = d.dtstart.value
            all_day = _is_date(old_dt)
            if all_day:
                d.dtstart.value = new_dt.date()
            else:
                d.dtstart.value = new_dt

            if new_duration_minutes and new_duration_minutes > 0:
                new_end = new_dt + timedelta(minutes=new_duration_minutes)
            else:
                old_end = d.dtend.value if hasattr(d, "dtend") else old_dt
                try:
                    duration = old_end - old_dt
                except TypeError:
                    duration = timedelta(hours=1)
                new_end = new_dt + duration
            if all_day:
                d.dtend.value = new_end.date()
            else:
                d.dtend.value = new_end
        elif new_duration_minutes > 0:
            old_dt = d.dtstart.value
            old_end = d.dtend.value if hasattr(d, "dtend") else old_dt + timedelta(hours=1)
            new_end = old_dt + timedelta(minutes=new_duration_minutes)
            if _is_date(old_dt) and _is_date(old_end):
                d.dtend.value = new_end.date()
            else:
                d.dtend.value = new_end

        ev.data = ev.vobject_instance.serialize()
        ev.save()
        _invalidate_today_cache()
        parts = []
        if new_summary:
            parts.append(f"title '{s}' → '{new_summary}'")
        if new_start_time:
            parts.append(f"time → {new_start_time}")
        if new_duration_minutes > 0:
            parts.append(f"duration → {new_duration_minutes}min")
        return f"OK '{s}' updated ({', '.join(parts)})."
    except Exception as e:
        logger.error("Failed to update calendar event '%s': %s", summary, e)
        return "ERROR: Could not update event."
