"""Tests for tools/dispatcher.py tool dispatch logic."""

from unittest.mock import AsyncMock, MagicMock, patch

from tools.dispatcher import run_tool


class TestDatetime:
    async def test_get_datetime_formats_current_time(self):
        result = await run_tool("get_datetime", {})
        assert result.startswith("Current: ")

    async def test_get_datetime_ignores_params(self):
        result = await run_tool("get_datetime", {"foo": "bar"})
        assert result.startswith("Current: ")


class TestWeather:
    async def test_get_weather_uses_city_param(self):
        with patch("weather.get_weather", new=AsyncMock(return_value="sunny 25C")):
            result = await run_tool("get_weather", {"city": "Istanbul"})
        assert result == "sunny 25C"

    async def test_get_weather_without_city(self):
        with patch("weather.get_weather", new=AsyncMock(return_value="cloudy")) as w:
            result = await run_tool("get_weather", {})
        w.assert_awaited_once_with("")
        assert result == "cloudy"


class TestCalendarTools:
    async def test_create_requires_start_time(self):
        result = await run_tool("create_calendar_event", {"summary": "Meet"})
        assert result == "ERROR: start_time required."

    async def test_create_calls_handler(self):
        with patch("calendar_ops.create_event", return_value="Created.") as ce:
            result = await run_tool(
                "create_calendar_event",
                {"summary": "Meet", "start_time": "2026-08-17T10:00:00", "duration_minutes": 30},
            )
        assert result == "Created."
        assert ce.call_args.args == ("Meet", "2026-08-17T10:00:00", 30)

    async def test_create_invalid_duration_returns_error(self):
        result = await run_tool(
            "create_calendar_event", {"start_time": "x", "duration_minutes": "abc"}
        )
        assert result == "ERROR: 'duration_minutes' must be a valid number, got: 'abc'"

    async def test_list_defaults_to_seven_days(self):
        with patch("calendar_ops.list_events", return_value="no events") as le:
            result = await run_tool("list_calendar_events", {})
        le.assert_called_once_with(7)
        assert result == "no events"

    async def test_update_requires_summary(self):
        result = await run_tool("update_calendar_event", {"new_summary": "X"})
        assert result == "ERROR: Event name required."

    async def test_update_passes_kwargs(self):
        with patch("calendar_ops.update_event", return_value="Updated.") as ue:
            result = await run_tool(
                "update_calendar_event",
                {"summary": "Meet", "new_summary": "Meet 2", "event_uid": "uid-1", "new_duration_minutes": 45},
            )
        assert result == "Updated."
        assert ue.call_args.args == ("Meet",)
        assert ue.call_args.kwargs == {
            "new_summary": "Meet 2",
            "new_start_time": "",
            "new_duration_minutes": 45,
            "event_uid": "uid-1",
        }

    async def test_delete_requires_summary(self):
        result = await run_tool("delete_calendar_event", {})
        assert result == "ERROR: Event name required."

    async def test_delete_passes_uid(self):
        with patch("calendar_ops.delete_event", return_value="Deleted.") as de:
            result = await run_tool("delete_calendar_event", {"summary": "Meet", "event_uid": "uid-1"})
        assert result == "Deleted."
        de.assert_called_once_with("Meet", event_uid="uid-1")

    async def test_calendar_exception_is_sanitized(self):
        with patch("calendar_ops.list_events", side_effect=RuntimeError("boom")):
            result = await run_tool("list_calendar_events", {})
        assert result == "ERROR: Calendar operation failed. Check server logs."


class TestMemory:
    async def test_save_memory_requires_content(self):
        result = await run_tool("save_memory", {})
        assert result == "ERROR: content required."

    async def test_save_memory_passes_context(self):
        with patch("db.save_memory", new=AsyncMock()) as sm:
            result = await run_tool(
                "save_memory",
                {"content": "  loves coffee  ", "category": "pref"},
                context={"user_id": 7},
            )
        sm.assert_awaited_once_with(content="loves coffee", category="pref", user_id=7)
        assert result == "Memory saved."


def _mail_client(messages=None, message=None, sent=True, results=None):
    mc = MagicMock()
    mc.get_messages = AsyncMock(return_value=messages or [])
    mc.get_message = AsyncMock(return_value=message)
    mc.send_message = AsyncMock(return_value=sent)
    mc.search_messages = AsyncMock(return_value=results or [])
    return mc


class TestMailTools:
    async def test_no_client_returns_config_error(self):
        with patch("mail.get_active_mail_client", return_value=None):
            result = await run_tool("list_emails", {})
        assert result == "ERROR: Mail connection failed. Check .env configuration."

    async def test_list_emails_empty_inbox(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("list_emails", {})
        assert result == "Inbox is empty."

    async def test_list_emails_formats_and_caches(self):
        msgs = [{"from": "a@x.com", "subject": "Hi", "date": "Mon", "id": 5, "body": "hello world"}]
        mc = _mail_client(messages=msgs)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.cache_email_context") as cache:
            result = await run_tool("list_emails", {"limit": 3}, context={"session_id": "s1"})
        mc.get_messages.assert_awaited_once_with(1, "INBOX", 3)
        cache.assert_called_once_with("s1", msgs)
        assert "From: a@x.com" in result
        assert "Subject: Hi" in result
        assert "ID:" not in result
        assert "1." in result
        assert "Preview: hello world" in result

    async def test_list_emails_does_not_cache_without_session(self):
        msgs = [{"from": "a@x.com", "subject": "Hi", "date": "Mon", "id": 5}]
        mc = _mail_client(messages=msgs)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.cache_email_context") as cache:
            result = await run_tool("list_emails", {})
        cache.assert_not_called()
        assert "showing 1" in result

    async def test_list_emails_invalid_limit(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("list_emails", {"limit": "abc"})
        assert result == "ERROR: 'limit' must be a valid number, got: 'abc'"

    async def test_read_email_requires_id(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("read_email", {})
        assert result == "ERROR: message_id required."

    async def test_read_email_not_found(self):
        mc = _mail_client(message=None)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("read_email", {"message_id": 42})
        assert result == "Email not found."

    async def test_read_email_returns_details(self):
        msg = {"from": "a@x.com", "subject": "Hi", "date": "Mon", "body": "content here"}
        mc = _mail_client(message=msg)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("read_email", {"message_id": 42})
        mc.get_message.assert_awaited_once_with(1, "INBOX", 42)
        assert "From: a@x.com" in result
        assert "content here" in result

    async def test_read_email_resolves_list_number_to_id(self):
        msg = {"from": "a@x.com", "subject": "Hi", "date": "Mon", "body": "content here"}
        mc = _mail_client(message=msg)
        cached = [{"id": "999", "from": "a@x.com", "subject": "Hi", "preview": "content here"}]
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", return_value=cached):
            result = await run_tool("read_email", {"message_id": "1"}, context={"session_id": "s1"})
        mc.get_message.assert_awaited_once_with(1, "INBOX", "999")
        assert "content here" in result

    async def test_read_email_list_number_out_of_range_falls_back(self):
        cached = [{"id": "999", "from": "a@x.com", "subject": "Hi", "preview": "content here"}]
        mc = _mail_client(message=None)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", return_value=cached):
            result = await run_tool("read_email", {"message_id": "5"}, context={"session_id": "s1"})
        mc.get_message.assert_awaited_once_with(1, "INBOX", "5")
        assert result == "Email not found."

    async def test_send_requires_all_fields(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("send_email", {"to": "a@x.com"})
        assert result == "ERROR: 'to', 'subject' and 'body' are required."

    async def test_send_ok(self):
        mc = _mail_client(sent=True)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("send_email", {"to": "a@x.com", "subject": "S", "body": "B", "cc": "c@x.com"})
        mc.send_message.assert_awaited_once_with(1, "a@x.com", "S", "B", "c@x.com", "")
        assert result.startswith("Email sent!")

    async def test_send_failure(self):
        mc = _mail_client(sent=False)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("send_email", {"to": "a@x.com", "subject": "S", "body": "B"})
        assert result == "Failed to send."

    async def test_search_requires_query(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("search_emails", {})
        assert result == "ERROR: 'query' required."

    async def test_search_no_results(self):
        mc = _mail_client(results=[])
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("search_emails", {"query": "x"})
        assert result == "'x' no results found."

    async def test_search_formats_and_caches(self):
        msgs = [{"from": "a@x.com", "subject": "Match", "id": 2, "body": "preview"}]
        mc = _mail_client(results=msgs)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.cache_email_context") as cache:
            result = await run_tool("search_emails", {"query": "Match"}, context={"session_id": "s2"})
        mc.search_messages.assert_awaited_once_with(1, "Match", 10)
        cache.assert_called_once_with("s2", msgs)
        assert "'Match' Results (1):" in result
        assert "ID:" not in result

    async def test_mail_exception_is_sanitized(self):
        mc = _mail_client()
        mc.get_messages.side_effect = RuntimeError("boom")
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("list_emails", {})
        assert result == "ERROR: Mail operation failed. Check server logs."


class TestNotesTools:
    async def test_create_note_requires_title(self):
        result = await run_tool("create_note", {})
        assert result == "ERROR: title required."

    async def test_create_note_calls_handler(self):
        with patch("nextcloud_notes.create_note", new=AsyncMock(return_value="created")) as cn:
            result = await run_tool("create_note", {"title": "T", "content": "C", "category": "work"})
        cn.assert_awaited_once_with(title="T", content="C", category="work")
        assert result == "created"

    async def test_list_notes(self):
        with patch("nextcloud_notes.list_notes", new=AsyncMock(return_value="[]")) as ln:
            result = await run_tool("list_notes", {})
        ln.assert_awaited_once()
        assert result == "[]"

    async def test_read_note_requires_id(self):
        result = await run_tool("read_note", {})
        assert result == "ERROR: note_id required."

    async def test_read_note_invalid_id(self):
        result = await run_tool("read_note", {"note_id": "abc"})
        assert result == "ERROR: Invalid note_id 'abc'. Must be a number (e.g. 284)."

    async def test_read_note_calls_handler(self):
        with patch("nextcloud_notes.get_note", new=AsyncMock(return_value="note")) as gn:
            result = await run_tool("read_note", {"note_id": "42"})
        gn.assert_awaited_once_with(42)
        assert result == "note"

    async def test_update_note_requires_id(self):
        result = await run_tool("update_note", {"title": "T"})
        assert result == "ERROR: note_id required."

    async def test_update_note_invalid_id(self):
        result = await run_tool("update_note", {"note_id": "x", "title": "T"})
        assert "ERROR: Invalid note_id 'x'" in result

    async def test_delete_note_requires_id(self):
        result = await run_tool("delete_note", {})
        assert result == "ERROR: note_id required."

    async def test_search_notes_requires_query(self):
        result = await run_tool("search_notes", {})
        assert result == "ERROR: query required."

    async def test_search_notes_calls_handler(self):
        with patch("nextcloud_notes.search_notes", new=AsyncMock(return_value="found")) as sn:
            result = await run_tool("search_notes", {"query": "  travel  "})
        sn.assert_awaited_once_with("travel")
        assert result == "found"

    async def test_notes_exception_is_sanitized(self):
        with patch("nextcloud_notes.list_notes", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await run_tool("list_notes", {})
        assert result == "ERROR: Notes operation failed. Check server logs."


class TestTasksTools:
    async def test_create_task_requires_summary(self):
        result = await run_tool("create_task", {})
        assert result == "ERROR: summary required."

    async def test_create_task_calls_handler(self):
        with patch("nextcloud_tasks.create_task", new=AsyncMock(return_value="created")) as ct:
            result = await run_tool("create_task", {"summary": "Buy milk", "due": "2026-08-17", "priority": 2, "notes": "n"})
        ct.assert_awaited_once_with(summary="Buy milk", due="2026-08-17", priority=2, notes="n")
        assert result == "created"

    async def test_create_task_invalid_priority(self):
        result = await run_tool("create_task", {"summary": "X", "priority": "high"})
        assert result == "ERROR: 'priority' must be a valid number, got: 'high'"

    async def test_list_tasks_show_completed_flag(self):
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value="[]")) as lt:
            result = await run_tool("list_tasks", {"show_completed": True})
        lt.assert_awaited_once_with(show_completed=True)
        assert result == "[]"

    async def test_complete_task_requires_uid(self):
        result = await run_tool("complete_task", {})
        assert result == "ERROR: uid required."

    async def test_delete_task_requires_uid(self):
        result = await run_tool("delete_task", {})
        assert result == "ERROR: uid required."

    async def test_search_tasks_requires_query(self):
        result = await run_tool("search_tasks", {})
        assert result == "ERROR: query required."

    async def test_search_tasks_calls_handler(self):
        with patch("nextcloud_tasks.search_tasks", new=AsyncMock(return_value="found")) as st:
            result = await run_tool("search_tasks", {"query": "milk"})
        st.assert_awaited_once_with("milk")
        assert result == "found"

    async def test_tasks_exception_returns_tool_name(self):
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await run_tool("list_tasks", {})
        assert result == "ERROR: list_tasks failed"
