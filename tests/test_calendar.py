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
        result, matched = _match_event(events, "Dentist", event_uid="uid-222")
        assert result is ev2
        assert matched == "Dentist Appointment"

    def test_uid_partial_match(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("abc-def-123", "Meeting")
        result, matched = _match_event([ev], "Meeting", event_uid="abc-def")
        assert result is ev
        assert matched == "Meeting"

    def test_uid_no_match_returns_none(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("uid-111", "Event A")
        result, matched = _match_event([ev], "Event A", event_uid="uid-999")
        assert result is None
        assert matched is None

    def test_summary_substring_fallback(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("uid-111", "Team Standup")
        result, matched = _match_event([ev], "standup")
        assert result is ev
        assert matched == "Team Standup"

    def test_summary_no_match_returns_none(self):
        from calendar_ops import _match_event
        ev = self._make_mock_event("uid-111", "Event A")
        result, matched = _match_event([ev], "Nonexistent")
        assert result is None
        assert matched is None


class TestRunTool:
    async def test_unknown_tool_returns_not_found(self):
        from tools.dispatcher import run_tool
        result = await run_tool("nonexistent_tool", {})
        assert result == "Tool not found."


class TestIntentFallback:
    async def test_embedding_failure_falls_to_keyword(self):
        with patch("llm.intent._get_tool_embeddings", side_effect=Exception("boom")):
            from llm.intent import _classify_intent
            intent, group = await _classify_intent("hava durumu nasıl")
            assert intent == "action"
            assert group == "weather"