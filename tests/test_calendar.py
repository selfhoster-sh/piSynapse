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
            result = create_event("Water plants", "2026-08-31", all_day=True)
        assert "OK 'Water plants' added to calendar." == result
        ical = fake_cal.add_event.call_args.args[0]
        assert "DTSTART;VALUE=DATE:20260831" in ical
        assert "DTEND;VALUE=DATE:20260901" in ical

    def test_create_timed_uses_datetime_dtstart(self):
        from calendar_ops import create_event
        fake_cal = MagicMock()
        with patch("calendar_ops._get_calendar", return_value=fake_cal):
            result = create_event("Meet", "2026-08-17T14:00:00", 30)
        assert result == "OK 'Meet' added to calendar."
        ical = fake_cal.add_event.call_args.args[0]
        assert "DTSTART;VALUE=DATE-TIME:20260817T140000" in ical
        assert "DTEND;VALUE=DATE-TIME:20260817T143000" in ical


class TestRunTool:
    async def test_unknown_tool_returns_not_found(self):
        from tools.dispatcher import run_tool
        result = await run_tool("nonexistent_tool", {})
        assert result == "ERROR: Tool not found."


class TestIntentFallback:
    async def test_embedding_failure_falls_to_keyword(self):
        with patch("llm.intent._get_tool_embeddings", side_effect=Exception("boom")):
            from llm.intent import _classify_intent
            intent, group = await _classify_intent("hava durumu nasıl")
            assert intent == "action"
            assert group == "weather"
