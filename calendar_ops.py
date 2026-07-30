"""piSynapse Calendar
Nextcloud CalDAV integration for calendar operations.
"""

import logging
from datetime import datetime, timedelta
from utils import retry

logger = logging.getLogger("piSynapse")

_dav_client = None
_dav_calendar = None


def _get_nextcloud_client():
    global _dav_client
    from config import NEXTCLOUD_URL, NEXTCLOUD_USER, NEXTCLOUD_PASSWORD, NEXTCLOUD_TIMEOUT
    if not NEXTCLOUD_URL or not NEXTCLOUD_PASSWORD:
        return None
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
    
    Returns (event, matched_summary) or (None, None).
    UID match takes priority when event_uid is provided.
    """
    try:
        if event_uid:
            for ev in events:
                d = ev.vobject_instance.vevent
                uid = _get_uid(d)
                if uid == event_uid or uid.startswith(event_uid):
                    s = getattr(d, "summary", "").value
                    return ev, s
            return None, None

        for ev in events:
            d = ev.vobject_instance.vevent
            s = getattr(d, "summary", "").value
            if summary.lower() in s.lower():
                return ev, s
        return None, None
    except Exception as e:
        logger.error("Failed to match calendar event: %s", e)
        return None, None


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
            f"SUMMARY:{summary}",
            f"DTSTART;VALUE=DATE-TIME:{start_dt.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND;VALUE=DATE-TIME:{end_dt.strftime('%Y%m%dT%H%M%S')}",
            "END:VEVENT", "END:VCALENDAR",
        ]) + "\r\n"
        calendar.add_event(ical)
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
    """Structured today's events for the widget."""
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
        return sorted(result, key=lambda x: x["time"])
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
            return f"'{summary}' not found."
        ev, s = _match_event(events, summary, event_uid)
        if ev is None:
            return f"'{summary}' not found."
        ev.delete()
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
            return f"'{summary}' not found."
        ev, s = _match_event(events, summary, event_uid)
        if ev is None:
            return f"'{summary}' not found."
        d = ev.vobject_instance.vevent
        data = ev.data
        if new_summary:
            old_tag_line = f"SUMMARY:{s}"
            new_tag_line = f"SUMMARY:{new_summary}"
            data = data.replace(old_tag_line, new_tag_line)
        if new_start_time:
            old_dt = d.dtstart.value
            old_dt_str = old_dt.strftime('%Y%m%dT%H%M%S') if hasattr(old_dt, 'strftime') else str(old_dt)
            new_dt = datetime.fromisoformat(new_start_time)
            new_dt_str = new_dt.strftime('%Y%m%dT%H%M%S')
            data = data.replace(old_dt_str, new_dt_str)
            if new_duration_minutes and new_duration_minutes > 0:
                old_end = d.dtend.value if hasattr(d, 'dtend') else old_dt
                old_end_str = old_end.strftime('%Y%m%dT%H%M%S') if hasattr(old_end, 'strftime') else str(old_end)
                new_end = new_dt + timedelta(minutes=new_duration_minutes)
                new_end_str = new_end.strftime('%Y%m%dT%H%M%S')
                data = data.replace(old_end_str, new_end_str)
            elif new_start_time:
                old_end = d.dtend.value if hasattr(d, 'dtend') else old_dt
                old_end_str = old_end.strftime('%Y%m%dT%H%M%S') if hasattr(old_end, 'strftime') else str(old_end)
                duration = old_end - old_dt if hasattr(old_end, '-') else timedelta(hours=1)
                new_end = new_dt + duration
                new_end_str = new_end.strftime('%Y%m%dT%H%M%S')
                data = data.replace(old_end_str, new_end_str)
        elif new_duration_minutes > 0:
            old_dt = d.dtstart.value
            old_end = d.dtend.value if hasattr(d, 'dtend') else old_dt + timedelta(hours=1)
            old_end_str = old_end.strftime('%Y%m%dT%H%M%S') if hasattr(old_end, 'strftime') else str(old_end)
            new_end = old_dt + timedelta(minutes=new_duration_minutes)
            new_end_str = new_end.strftime('%Y%m%dT%H%M%S')
            data = data.replace(old_end_str, new_end_str)
        ev.data = data
        ev.save()
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