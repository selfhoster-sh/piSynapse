"""Tests for calendar operations and tool dispatch."""

from unittest.mock import MagicMock, patch


class TestMatchEvent:
    def _make_mock_event(self, uid: str, summary: str):
        """Create a mock CalDAV event with given uid and summary."""
        mock_vevent = MagicMock()
        mock_uid = MagicMock()
        mock_uid.value = uid
        mock_summary = MagicMock()
        mock_summary.value = summary
        mock_vevent.uid = mock_uid
        mock_vevent.summary = mock_summary
        mock_event = MagicMock()
        mock_event.vobject_instance.vevent = mock_vevent
        return mock_event

    def test_uid_match_takes_priority(self):
        from calendar_ops import _match_event
        ev1 = self._make_mock_event("uid-111", "Dentist Appointment")
        ev2 = self._make_mock_event("uid-222", "Dentist Appointment")
        events = [ev1, ev2]
        result, matched, status = _match_event(events, "Dentist", event_uid="uid-222")
        assert result is ev2
        assert matched == "Dentist Appointment"
        assert status == ""

    def test_uid_partial_match(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("abc-def-123", "Meeting")
        result, matched, status = _match_event([ev], "Meeting", event_uid="abc-def")
        assert result is ev
        assert matched == "Meeting"
        assert status == ""

    def test_uid_no_match_returns_not_found(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("uid-111", "Event A")
        result, matched, status = _match_event([ev], "Event A", event_uid="uid-999")
        assert result is None
        assert matched is None
        assert status == "not_found"

    def test_summary_substring_fallback(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("uid-111", "Team Standup")
        result, matched, status = _match_event([ev], "standup")
        assert result is ev
        assert matched == "Team Standup"
        assert status == ""

    def test_summary_no_match_returns_not_found(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("uid-111", "Event A")
        result, matched, status = _match_event([ev], "Nonexistent")
        assert result is None
        assert matched is None
        assert status == "not_found"

    def test_ambiguous_summary_never_auto_picks(self):
        from calendar_ops import _match_event
        ev1 = self._make_mock_event("uid-111", "Dentist Appointment")
        ev2 = self._make_mock_event("uid-222", "Dentist Appointment")
        result, matched, status = _match_event([ev1, ev2], "dentist")
        assert result is None
        assert matched is None
        assert status == "ambiguous"

    def test_ambiguous_uid_never_auto_picks(self):
        from calendar_ops import _match_event
        ev1 = self._make_mock_event("uid-111", "Dentist Appointment")
        ev2 = self._make_mock_event("uid-111-extra", "Dentist Follow-up")
        result, matched, status = _match_event([ev1, ev2], "Dentist", event_uid="uid-111")
        assert result is None
        assert status == "ambiguous"

    def test_ical_escape_text_blocks_injection(self):
        from calendar_ops import _ical_escape_text
        assert _ical_escape_text("foo") == "foo"
        assert _ical_escape_text("a\r\nb") == "a\\nb"
        assert _ical_escape_text("a,b;c") == "a\\,b\\;c"
        assert _ical_escape_text("back\\slash") == "back\\\\slash"


class TestCreateEventSerialization:
    def test_create_all_day_uses_date_dtstart_next_day_end(self):
        from calendar_ops import create_event
        fake_cal = MagicMock()
        with patch("calendar_ops._get_calendar", return_value=fake_cal):
            result = create_event("Water plants", _DAY_ALLDAY, all_day=True)
        assert result[0] == "OK 'Water plants' added to calendar."
        ical = fake_cal.add_event.call_args.args[0]
        assert f"DTSTART;VALUE=DATE:{_DAY_ALLDAY_IC}" in ical
        assert f"DTEND;VALUE=DATE:{_DAY_ALLDAY_NEXT_IC}" in ical

    def test_create_timed_uses_datetime_dtstart(self):
        from calendar_ops import create_event
        fake_cal = MagicMock()
        with patch("calendar_ops._get_calendar", return_value=fake_cal):
            result = create_event("Meet", _DT_MEET, 30)
        assert result[0] == "OK 'Meet' added to calendar."
        ical = fake_cal.add_event.call_args.args[0]
        assert f"DTSTART;VALUE=DATE-TIME:{_DT_MEET_IC}" in ical
        assert f"DTEND;VALUE=DATE-TIME:{_DT_MEET_DTEND_IC}" in ical


class TestRunTool:
    async def test_unknown_tool_returns_not_found(self):
        from tools.dispatcher import run_tool
        result = await run_tool("nonexistent_tool", {})
        assert result[0] == "ERROR: Tool not found."


class TestIntentFallback:
    async def test_embedding_failure_falls_to_keyword(self):
        with patch("llm.intent._get_tool_embeddings", side_effect=Exception("boom")):
            from llm.intent import _classify_intent
            intent, group = await _classify_intent("hava durumu nasıl")
            assert intent == "action"
            assert group == "weather"


class TestListSanitizesDescriptions:
    def test_list_strips_markup_from_descriptions(self):
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import MagicMock, patch

        from calendar_ops import list_events

        def _vevent(summary, desc):
            return SimpleNamespace(
                vobject_instance=SimpleNamespace(vevent=SimpleNamespace(
                    summary=SimpleNamespace(value=summary),
                    dtstart=SimpleNamespace(value=datetime(2026, 8, 17, 10, 0)),
                    description=SimpleNamespace(value=desc),
                    uid=SimpleNamespace(value="u1"),
                ))
            )

        fake_cal = MagicMock()
        fake_cal.date_search.return_value = [
            _vevent("Standup", '<script>alert(1)</script><img src=x onerror=steal()>Team sync at 10'),
        ]
        with patch("calendar_ops._get_calendar", return_value=fake_cal):
            text, items = list_events(7)
        assert "<script>" not in text
        assert "<img" not in text
        assert "onerror" not in text
        assert "Team sync at 10" in text
        assert items[0]["summary"] == "Standup"


# Determinism rule (2026-11-16): no absolute date literals in test code.
from datetime import datetime, timedelta, timezone

_DAY_ALLDAY = (datetime.now(timezone.utc) - timedelta(days=16)).strftime("%Y-%m-%d")
_DT_MEET = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT14:00:00")


_DAY_ALLDAY_IC = _DAY_ALLDAY.replace("-", "")
_DAY_ALLDAY_NEXT_IC = (datetime.now(timezone.utc) - timedelta(days=15)).strftime("%Y%m%d")
_DT_MEET_IC = _DT_MEET.replace("-", "").replace(":", "")


from datetime import datetime, timedelta

_DT_MEET_DTEND_IC = (datetime.strptime(_DT_MEET, "%Y-%m-%dT%H:%M:%S") + timedelta(minutes=30)).strftime("%Y%m%dT%H%M%S")
