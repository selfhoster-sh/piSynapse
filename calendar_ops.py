"""piSynapse Calendar
Nextcloud CalDAV integration for calendar operations.
"""

import logging
import threading
import time
from datetime import date, datetime, timedelta

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

# Short-lived cache for _find_events to avoid redundant CalDAV calls
_find_events_cache: tuple[float, list] | None = None
_FIND_EVENTS_CACHE_TTL = 5.0  # seconds

_cache_lock = threading.Lock()


def _invalidate_today_cache() -> None:
    """Drop cached today's events after a calendar write (create/update/delete)."""
    global _today_cache, _find_events_cache
    with _cache_lock:
        _today_cache = None
        _find_events_cache = None


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


def _get_calendar():
    """Return the primary CalDAV calendar, or raise if unavailable."""
    client = _get_nextcloud_client()
    if not client:
        raise Exception("Nextcloud credentials missing. Set NEXTCLOUD_URL and NEXTCLOUD_PASSWORD.")
    return _get_primary_calendar(client)


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
    """Return all events in the search window (cached for 5s to avoid redundant CalDAV calls)."""
    global _find_events_cache
    now = time.time()
    with _cache_lock:
        if _find_events_cache and (now - _find_events_cache[0]) < _FIND_EVENTS_CACHE_TTL:
            return _find_events_cache[1]
    try:
        calendar = _get_calendar()
        events = calendar.date_search(
            datetime.now() - timedelta(days=search_window_days_back),
            datetime.now() + timedelta(days=search_window_days_ahead),
        )
        with _cache_lock:
            _find_events_cache = (now, events)
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


def _parse_start(raw: str) -> datetime:
    """Accept an ISO datetime or a plain YYYY-MM-DD date string.

    ``create_event``'s ``start_time`` is ISO 8601 for timed events and a bare
    date for all-day events; this normalizes both to a datetime.
    """
    raw = (raw or "").strip()
    if "T" in raw:
        return datetime.fromisoformat(raw)
    return datetime.combine(date.fromisoformat(raw), datetime.min.time())


@retry(attempts=2, delay=1.0)
def create_event(
    summary: str,
    start_time_str: str,
    duration_minutes: int = 60,
    all_day: bool = False,
    rrule: str | None = None,
) -> tuple[str, str]:
    """Create a calendar event.

    Args:
        summary: Event title.
        start_time_str: ISO 8601 datetime (timed) or YYYY-MM-DD (all-day).
        duration_minutes: Duration in minutes (ignored for all-day).
        all_day: True for date-only event.
        rrule: Optional RFC 5545 RRULE string (e.g. "FREQ=WEEKLY;BYDAY=MO,WE,FR").

    Returns:
        Tuple of (result_message, uid). uid is empty string on error.
    """
    try:
        calendar = _get_calendar()
        if all_day:
            start_date = _parse_start(start_time_str).date()
            end_date = start_date + timedelta(days=1)
            dtstart = f"DTSTART;VALUE=DATE:{start_date:%Y%m%d}"
            dtend = f"DTEND;VALUE=DATE:{end_date:%Y%m%d}"
        else:
            start_dt = datetime.fromisoformat(start_time_str)
            end_dt = start_dt + timedelta(minutes=duration_minutes)
            dtstart = f"DTSTART;VALUE=DATE-TIME:{start_dt.strftime('%Y%m%dT%H%M%S')}"
            dtend = f"DTEND;VALUE=DATE-TIME:{end_dt.strftime('%Y%m%dT%H%M%S')}"

        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//piSynapse//EN",
            "BEGIN:VEVENT",
            f"SUMMARY:{_ical_escape_text(summary)}",
            dtstart,
            dtend,
        ]
        if rrule:
            lines.append(f"RRULE:{rrule}")
        lines.extend(["END:VEVENT", "END:VCALENDAR"])
        ical = "\r\n".join(lines) + "\r\n"

        event = calendar.add_event(ical)
        uid = event.id or ""
        _invalidate_today_cache()
        return f"OK '{summary}' added to calendar.", uid
    except Exception as e:
        logger.error("Failed to create calendar event '%s': %s", summary, e)
        return f"ERROR: Could not create event '{summary}'.", ""


@retry(attempts=2, delay=1.0)
def list_events(days_ahead: int = 7) -> tuple[str, list[dict]]:
    """List upcoming events.

    Returns ``(display_text, items)`` where ``items`` are
    ``{"uid": ..., "summary": ..., "start": ...}`` dicts in the exact order
    they are numbered in ``display_text`` (the model only sees list
    positions; real UIDs never appear in tool output).
    """
    try:
        calendar = _get_calendar()
        start = datetime.now()
        end = start + timedelta(days=days_ahead)
        events = calendar.date_search(start, end)
        if not events:
            return f"Next {days_ahead} days: no events.", []
        lines = []
        items: list[dict] = []
        for i, ev in enumerate(events, 1):
            d = ev.vobject_instance.vevent
            s = getattr(d, "summary", getattr(d, "description", "Untitled")).value
            st = d.dtstart.value
            ts = st.strftime("%Y-%m-%d %H:%M") if hasattr(st, "strftime") else str(st)
            uid = _get_uid(d)
            line = f"   {i}. {ts} | {s}"
            desc = getattr(d, "description", None)
            if desc and hasattr(desc, "value") and desc.value and desc.value != s:
                line += f"\n      {desc.value[:100]}"
            lines.append(line)
            items.append({"uid": uid, "summary": s, "start": ts})
        return "Events:\n" + "\n".join(lines), items
    except Exception as e:
        logger.error("Failed to list calendar events: %s", e)
        return "ERROR: Could not load calendar events.", []


@retry(attempts=2, delay=1.0)
def list_events_today() -> list[dict]:
    """Structured today's events for the widget (TTL-cached, see ``_TODAY_CACHE_TTL``)."""
    global _today_cache
    with _cache_lock:
        if _today_cache is not None:
            cached_at, cached = _today_cache
            if time.monotonic() - cached_at < _TODAY_CACHE_TTL:
                return cached
    try:
        from datetime import date
        try:
            calendar = _get_calendar()
        except Exception:
            return []
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
        with _cache_lock:
            _today_cache = (time.monotonic(), result)
        return result
    except Exception as e:
        logger.error("Failed to list today's events: %s", e)
        return []


def find_events_by_summary(summary: str, days_back: int = 30, days_ahead: int = 90) -> list[dict]:
    """Find calendar events matching summary substring. Returns list of {summary, start, uid} dicts."""
    try:
        try:
            calendar = _get_calendar()
        except Exception:
            return []
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
def find_free_slots(date_str: str, duration_minutes: int = 60, day_start: str = "09:00", day_end: str = "18:00") -> tuple[str, list[dict]]:
    """Find free time slots on a given day.

    Args:
        date_str: Date in YYYY-MM-DD format.
        duration_minutes: Minimum slot length in minutes (default 60).
        day_start: Day start time HH:MM (default 09:00).
        day_end: Day end time HH:MM (default 18:00).

    Returns:
        (display_text, slots) where slots are {"start": "HH:MM", "end": "HH:MM"} dicts.
    """
    try:
        calendar = _get_calendar()
        day_date = datetime.fromisoformat(date_str).date()
        day_start_dt = datetime.combine(day_date, datetime.strptime(day_start, "%H:%M").time())
        day_end_dt = datetime.combine(day_date, datetime.strptime(day_end, "%H:%M").time())

        # Fetch events for that day
        events = calendar.date_search(day_start_dt, day_end_dt)

        # Build busy intervals (start, end) in minutes from day_start
        busy = []
        for ev in events:
            d = ev.vobject_instance.vevent
            st = d.dtstart.value
            et = d.dtend.value if hasattr(d, "dtend") else st
            if hasattr(st, "strftime"):
                ev_start = st
                ev_end = et if hasattr(et, "strftime") else ev_start + timedelta(hours=1)
                # Only consider events within day bounds
                if ev_end <= day_start_dt or ev_start >= day_end_dt:
                    continue
                ev_start = max(ev_start, day_start_dt)
                ev_end = min(ev_end, day_end_dt)
                start_min = int((ev_start - day_start_dt).total_seconds() / 60)
                end_min = int((ev_end - day_start_dt).total_seconds() / 60)
                busy.append((start_min, end_min))

        # Merge overlapping busy intervals
        busy.sort()
        merged = []
        for s, e in busy:
            if not merged or s > merged[-1][1]:
                merged.append([s, e])
            else:
                merged[-1][1] = max(merged[-1][1], e)

        # Find free slots >= duration_minutes
        total_min = int((day_end_dt - day_start_dt).total_seconds() / 60)
        slots = []
        cursor = 0
        for s, e in merged:
            if s - cursor >= duration_minutes:
                slot_start = day_start_dt + timedelta(minutes=cursor)
                slot_end = day_start_dt + timedelta(minutes=s)
                slots.append({"start": slot_start.strftime("%H:%M"), "end": slot_end.strftime("%H:%M")})
            cursor = max(cursor, e)
        if total_min - cursor >= duration_minutes:
            slot_start = day_start_dt + timedelta(minutes=cursor)
            slot_end = day_start_dt + timedelta(minutes=total_min)
            slots.append({"start": slot_start.strftime("%H:%M"), "end": slot_end.strftime("%H:%M")})

        if not slots:
            return f"No free slots of {duration_minutes}min on {date_str} between {day_start}-{day_end}.", []

        lines = [f"Free slots on {date_str} ({duration_minutes}min min, {day_start}-{day_end}):"]
        for i, sl in enumerate(slots, 1):
            lines.append(f"  {i}. {sl['start']} - {sl['end']}")
        return "\n".join(lines), slots

    except Exception as e:
        logger.error("Failed to find free slots for %s: %s", date_str, e)
        return f"ERROR: Could not find free slots for {date_str}.", []


@retry(attempts=2, delay=1.0)
def delete_event(summary: str, event_uid: str = "") -> str:
    try:
        _get_nextcloud_client()  # fail fast if no credentials
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
        _get_nextcloud_client()  # fail fast if no credentials
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
                # All-day event: DTEND is always next day (RFC 5545), ignore duration_minutes
                d.dtend.value = new_dt.date() + timedelta(days=1)
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
                d.dtend.value = new_end
        elif new_duration_minutes > 0:
            old_dt = d.dtstart.value
            all_day = _is_date(old_dt)
            if all_day:
                # All-day: duration_minutes ignored, keep DTEND as next day
                pass
            else:
                old_end = d.dtend.value if hasattr(d, "dtend") else old_dt + timedelta(hours=1)
                new_end = old_dt + timedelta(minutes=new_duration_minutes)
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
