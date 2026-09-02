"""Tests for tools/dispatcher.py tool dispatch logic."""

from unittest.mock import AsyncMock, MagicMock, patch

from tools.dispatcher import run_tool


class TestDatetime:
    async def test_get_datetime_formats_current_time(self):
        result = await run_tool("get_datetime", {})
        assert result[0].startswith("Current: ")

    async def test_get_datetime_ignores_params(self):
        result = await run_tool("get_datetime", {"foo": "bar"})
        assert result[0].startswith("Current: ")


class TestWeather:
    async def test_get_weather_uses_city_param(self):
        with patch("weather.get_weather", new=AsyncMock(return_value="sunny 25C")):
            result = await run_tool("get_weather", {"city": "Istanbul"})
        assert result[0] == "sunny 25C"

    async def test_get_weather_without_city(self):
        with patch("weather.get_weather", new=AsyncMock(return_value="cloudy")) as w:
            result = await run_tool("get_weather", {})
        w.assert_awaited_once_with("")
        assert result[0] == "cloudy"


class TestCalendarTools:
    async def test_create_requires_start_time(self):
        # Chip-flow guard: missing essentials -> CLARIFY, not a hard error.
        result = await run_tool("create_calendar_event", {"summary": "Meet"})
        assert "CLARIFY_REQUIRED" in result[0] and "start time" in result[0]

    async def test_create_missing_summary_clarifies(self):
        result = await run_tool("create_calendar_event", {"start_time": "2026-08-17T10:00:00"})
        assert "CLARIFY_REQUIRED" in result[0] and "title" in result[0]

    async def test_create_calls_handler(self):
        with patch("calendar_ops.create_event", return_value=("Created.", "test-uid")) as ce:
            result = await run_tool(
                "create_calendar_event",
                {"summary": "Meet", "start_time": "2026-08-17T10:00:00", "duration_minutes": 30},
            )
        assert result[0] == "Created."
        assert ce.call_args.args == ("Meet", "2026-08-17T10:00:00", 30)
        assert ce.call_args.kwargs == {"all_day": False, "rrule": None}

    async def test_create_all_day_passes_through(self):
        # Date-only (no clock hour) -> all-day event per industry convention.
        with patch("calendar_ops.create_event", return_value=("Created.", "test-uid")) as ce:
            result = await run_tool(
                "create_calendar_event",
                {"summary": "Water plants", "start_time": "2026-08-31", "all_day": True},
            )
        assert result[0] == "Created."
        assert ce.call_args.args == ("Water plants", "2026-08-31", 60)
        assert ce.call_args.kwargs == {"all_day": True, "rrule": None}

    async def test_create_invalid_duration_returns_error(self):
        result = await run_tool(
            "create_calendar_event",
            {"summary": "Meet", "start_time": "x", "duration_minutes": "abc"},
        )
        assert result[0] == "ERROR: 'duration_minutes' must be a valid number, got: 'abc'"

    async def test_list_defaults_to_seven_days(self):
        with patch("calendar_ops.list_events", return_value=("no events", [])) as le:
            result = await run_tool("list_calendar_events", {})
        le.assert_called_once_with(7)
        assert result[0] == "no events"

    async def test_update_requires_summary(self):
        result = await run_tool("update_calendar_event", {"new_summary": "X"})
        assert result[0] == "ERROR: Event name required."

    async def test_update_resolves_list_number_to_uid(self):
        cached = [{"uid": "uid-real-1", "summary": "Meet", "start": "2026-08-17 10:00"}]
        with patch("calendar_ops.update_event", return_value="Updated.") as ue, \
             patch("prompt.get_calendar_context", new=AsyncMock(return_value=cached)):
            result = await run_tool(
                "update_calendar_event",
                {"summary": "Meet", "new_summary": "Meet 2", "event_uid": "1"},
                context={"session_id": "s9"},
            )
        assert result[0] == "Updated."
        assert ue.call_args.kwargs["event_uid"] == "uid-real-1"

    async def test_update_rejects_out_of_range_number(self):
        cached = [{"uid": "uid-real-1", "summary": "Meet", "start": ""}]
        with patch("calendar_ops.update_event", return_value="Updated.") as ue, \
             patch("prompt.get_calendar_context", new=AsyncMock(return_value=cached)):
            result = await run_tool(
                "update_calendar_event",
                {"summary": "Meet", "event_uid": "5"},
                context={"session_id": "s9"},
            )
        assert result[0].startswith("ERROR: Event '5' not found")
        ue.assert_not_called()

    async def test_delete_requires_summary(self):
        result = await run_tool("delete_calendar_event", {})
        assert result[0] == "ERROR: Event name required."

    async def test_delete_resolves_list_number_to_uid(self):
        cached = [{"uid": "uid-real-2", "summary": "Meet", "start": ""}]
        with patch("calendar_ops.delete_event", return_value="Deleted.") as de, \
             patch("prompt.get_calendar_context", new=AsyncMock(return_value=cached)):
            result = await run_tool(
                "delete_calendar_event",
                {"summary": "Meet", "event_uid": "1"},
                context={"session_id": "s9"},
            )
        assert result[0] == "Deleted."
        de.assert_called_once_with("Meet", event_uid="uid-real-2")

    async def test_calendar_exception_is_sanitized(self):
        with patch("calendar_ops.list_events", side_effect=RuntimeError("boom")):
            result = await run_tool("list_calendar_events", {})
        assert result[0] == "ERROR: Calendar operation failed. Check server logs."

    async def test_find_free_slots_requires_date(self):
        result = await run_tool("find_free_slots", {})
        assert result[0] == "ERROR: date required (YYYY-MM-DD)."

    async def test_find_free_slots_calls_handler(self):
        # Regression: find_free_slots was missing from the calendar dispatch
        # membership set since 0c9c49a, so it answered "Tool not found." and
        # its handlers could never run. Must now reach calendar_ops.
        with patch("calendar_ops.find_free_slots", return_value=("09:00 - 12:00", [{"start": "09:00", "end": "12:00"}])) as fs:
            result = await run_tool(
                "find_free_slots",
                {"date": "2026-09-05", "duration_minutes": 45},
                context={"session_id": "s1"},
            )
        fs.assert_called_once_with("2026-09-05", 45, "09:00", "18:00")
        assert result[0] == "09:00 - 12:00"
        assert result[1] is None

    async def test_find_free_slots_custom_window(self):
        with patch("calendar_ops.find_free_slots", return_value=("10:00 - 11:00", [])) as fs:
            result = await run_tool(
                "find_free_slots",
                {"date": "2026-09-05", "duration_minutes": 60, "day_start": "08:00", "day_end": "17:00"},
            )
        fs.assert_called_once_with("2026-09-05", 60, "08:00", "17:00")
        assert result[0] == "10:00 - 11:00"

    async def test_find_free_slots_invalid_duration(self):
        result = await run_tool(
            "find_free_slots",
            {"date": "2026-09-05", "duration_minutes": "abc"},
        )
        assert result[0] == "ERROR: 'duration_minutes' must be a valid number, got: 'abc'"


class TestMemory:
    async def test_save_memory_requires_content(self):
        result = await run_tool("save_memory", {})
        assert result[0] == "ERROR: content required."

    async def test_save_memory_passes_context(self):
        with patch("db.save_memory", new=AsyncMock(return_value=("Memory saved.", 42))) as sm:
            result = await run_tool(
                "save_memory",
                {"content": "  loves coffee  ", "category": "pref"},
                context={"user_id": 7},
            )
        sm.assert_awaited_once_with(content="loves coffee", category="pref", importance=5, user_id=7)
        assert result[0] == "Memory saved."
        assert result[1] == 42

    async def test_save_memory_rejects_meta_requests(self):
        """Descriptions of the user's request are conversation events, not facts."""
        with patch("db.save_memory", new=AsyncMock()) as sm:
            for content in (
                "Kullanıcının notlarını gösterme isteği.",
                "The user's request to list notes",
                "User wants to see their notes",
                "User asked that we remember his coffee order",
            ):
                result = await run_tool("save_memory", {"content": content})
            assert "ERROR" in result[0]
            assert "Do not retry" in result[0]
        sm.assert_not_awaited()

    async def test_save_memory_allows_real_facts(self):
        with patch("db.save_memory", new=AsyncMock(return_value=("Memory saved.", 1))) as sm:
            for content in ("Kullanıcı Python sever", "Sabah kahve içmeyi tercih ediyor"):
                result = await run_tool("save_memory", {"content": content})
            assert result[0] == "Memory saved."
        assert sm.await_count == 2


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
        assert result[0] == "ERROR: Mail connection failed. Check .env configuration."

    async def test_list_emails_empty_inbox(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("list_emails", {})
        assert result[0] == "Inbox is empty."

    async def test_list_emails_formats_and_caches(self):
        msgs = [{"from": "a@x.com", "subject": "Hi", "date": "Mon", "id": 5, "body": "hello world"}]
        mc = _mail_client(messages=msgs)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.cache_email_context", new=AsyncMock()) as cache:
            result = await run_tool("list_emails", {"limit": 3}, context={"session_id": "s1"})
        mc.get_messages.assert_awaited_once_with(1, "INBOX", 3)
        cache.assert_awaited_once_with("s1", msgs)
        assert "From: a@x.com" in result[0]
        assert "Subject: Hi" in result[0]
        assert "ID:" not in result[0]
        assert "\n1." not in result[0]
        assert "Preview: hello world" in result[0]

    async def test_list_emails_does_not_cache_without_session(self):
        msgs = [{"from": "a@x.com", "subject": "Hi", "date": "Mon", "id": 5}]
        mc = _mail_client(messages=msgs)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.cache_email_context") as cache:
            result = await run_tool("list_emails", {})
        cache.assert_not_called()
        assert "showing 1" in result[0]

    async def test_list_emails_invalid_limit(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("list_emails", {"limit": "abc"})
        assert result[0] == "ERROR: 'limit' must be a valid number, got: 'abc'"

    async def test_read_email_requires_id(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("read_email", {})
        assert result[0] == "ERROR: message_id required."

    async def test_read_email_not_found(self):
        mc = _mail_client(message=None)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("read_email", {"message_id": 42})
        assert result[0] == "ERROR: Email not found. Run list_emails first to get the current listing."

    async def test_read_email_returns_details(self):
        msg = {"from": "a@x.com", "subject": "Hi", "date": "Mon", "body": "content here"}
        mc = _mail_client(message=msg)
        cached = [{"id": "42", "from": "a@x.com", "subject": "Hi", "preview": "content here"}]
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", new=AsyncMock(return_value=cached)):
            result = await run_tool("read_email", {"message_id": "1"}, context={"session_id": "s1"})
        mc.get_message.assert_awaited_once_with(1, "INBOX", "42")
        assert "From: a@x.com" in result[0]
        assert "content here" in result[0]

    async def test_read_email_resolves_list_number_to_id(self):
        msg = {"from": "a@x.com", "subject": "Hi", "date": "Mon", "body": "content here"}
        mc = _mail_client(message=msg)
        cached = [{"id": "999", "from": "a@x.com", "subject": "Hi", "preview": "content here"}]
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", new=AsyncMock(return_value=cached)):
            result = await run_tool("read_email", {"message_id": "1"}, context={"session_id": "s1"})
        mc.get_message.assert_awaited_once_with(1, "INBOX", "999")
        assert "content here" in result[0]

    async def test_read_email_accepts_id_param_alias(self):
        msg = {"from": "a@x.com", "subject": "Hi", "date": "Mon", "body": "content here"}
        mc = _mail_client(message=msg)
        cached = [{"id": "999", "from": "a@x.com", "subject": "Hi", "preview": "content here"}]
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", new=AsyncMock(return_value=cached)):
            result = await run_tool("read_email", {"id": "1"}, context={"session_id": "s1"})
        mc.get_message.assert_awaited_once_with(1, "INBOX", "999")
        assert "content here" in result[0]

    async def test_read_email_list_number_out_of_range_refused(self):
        """An out-of-range list number must be refused, not passed to IMAP as
        a raw UID (which could silently read the wrong message).
        """
        cached = [{"id": "999", "from": "a@x.com", "subject": "Hi", "preview": "content here"}]
        mc = _mail_client(message=None)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", new=AsyncMock(return_value=cached)):
            result = await run_tool("read_email", {"message_id": "5"}, context={"session_id": "s1"})
        mc.get_message.assert_not_awaited()
        assert result[0] == "ERROR: Email not found. Run list_emails first to get the current listing."

    async def test_read_email_refused_without_listing(self):
        """A numeric reference with no cached listing must not hit IMAP."""
        mc = _mail_client(message=None)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", new=AsyncMock(return_value=[])):
            result = await run_tool("read_email", {"message_id": "42"}, context={"session_id": "s1"})
        mc.get_message.assert_not_awaited()
        assert result[0].startswith("ERROR: Email not found.")

    async def test_read_email_rejects_non_numeric_reference(self):
        """Raw IMAP IDs / garbage strings are refused — positions only."""
        mc = _mail_client(message={"from": "a@x.com", "body": "secret"})
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.get_email_context", new=AsyncMock(return_value=[{"id": "77", "from": "a@x.com"}])):
            result = await run_tool("read_email", {"message_id": "77"}, context={"session_id": "s1"})
        mc.get_message.assert_not_awaited()
        assert result[0] == "ERROR: Email not found. Run list_emails first to get the current listing."

    async def test_send_requires_all_fields(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("send_email", {"to": "a@x.com"})
        assert "CLARIFY_REQUIRED" in result[0] and "subject" in result[0] and "body" in result[0]

    async def test_send_ok(self):
        mc = _mail_client(sent=True)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("send_email", {"to": "a@x.com", "subject": "S", "body": "B", "cc": "c@x.com"})
        mc.send_message.assert_awaited_once_with(1, "a@x.com", "S", "B", "c@x.com", "")
        assert result[0].startswith("Email sent!")

    async def test_send_failure(self):
        mc = _mail_client(sent=False)
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("send_email", {"to": "a@x.com", "subject": "S", "body": "B"})
        assert result[0] == "ERROR: Failed to send."
        from tools.dispatcher import is_tool_success
        assert not is_tool_success(result)

    async def test_search_requires_query(self):
        with patch("mail.get_active_mail_client", return_value=_mail_client()):
            result = await run_tool("search_emails", {})
        assert result[0] == "ERROR: 'query' required."

    async def test_search_no_results(self):
        mc = _mail_client(results=[])
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("search_emails", {"query": "x"})
        assert result[0] == "'x' no results found."

    async def test_search_formats_and_caches(self):
        msgs = [{"from": "a@x.com", "subject": "Match", "id": 2, "body": "preview"}]
        mc = _mail_client(results=msgs)
        with patch("mail.get_active_mail_client", return_value=mc), patch("prompt.cache_email_context") as cache:
            result = await run_tool("search_emails", {"query": "Match"}, context={"session_id": "s2"})
        mc.search_messages.assert_awaited_once_with(1, "Match", 10, "INBOX")
        cache.assert_called_once_with("s2", msgs)
        assert "'Match' Results (1):" in result[0]
        assert "ID:" not in result[0]

    async def test_mail_exception_is_sanitized(self):
        mc = _mail_client()
        mc.get_messages.side_effect = RuntimeError("boom")
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("list_emails", {})
        assert result[0] == "ERROR: Mail operation failed. Check server logs."


class TestNotesTools:
    async def test_create_note_requires_title(self):
        result = await run_tool("create_note", {})
        assert result[0] == "ERROR: title required."

    async def test_create_note_calls_handler(self):
        with patch("nextcloud_notes.create_note", new=AsyncMock(return_value="created")) as cn:
            result = await run_tool("create_note", {"title": "T", "content": "C", "category": "work"})
        cn.assert_awaited_once_with(title="T", content="C", category="work")
        assert result[0] == "created"

    async def test_list_notes(self):
        with patch("nextcloud_notes.list_notes", new=AsyncMock(return_value=("[]", []))) as ln:
            result = await run_tool("list_notes", {})
        ln.assert_awaited_once()
        assert result[0] == "[]"

    async def test_list_notes_caches_structured_items_not_parsed_text(self):
        """The session map is built from the structured items returned by the
        listing function — real IDs never appear in the displayed text.
        """
        items = [{"id": 42, "title": "T", "category": "", "preview": ""}]
        with patch("nextcloud_notes.list_notes", new=AsyncMock(return_value=(" Notes:\n\n   1. T\n", items))), \
             patch("prompt.cache_notes_context", new=AsyncMock()) as cache:
            result = await run_tool("list_notes", {}, context={"session_id": "s1"})
        cache.assert_awaited_once_with("s1", items)
        assert "ID:" not in result[0]
        assert "42" not in result[0]

    async def test_read_note_requires_id(self):
        result = await run_tool("read_note", {})
        assert result[0] == "ERROR: note_id required."

    async def test_read_note_invalid_id(self):
        result = await run_tool("read_note", {"note_id": "abc"})
        assert "ERROR: Note 'abc' not found" in result[0]

    async def test_read_note_calls_handler(self):
        with patch("prompt.get_notes_context", new=AsyncMock(return_value=[{"id": 42, "title": "T"}])):
            with patch("nextcloud_notes.get_note", new=AsyncMock(return_value="note")) as gn:
                result = await run_tool("read_note", {"note_id": "1"})
        gn.assert_awaited_once_with(42)
        assert result[0] == "note"

    async def test_read_note_unlisted_id(self):
        result = await run_tool("read_note", {"note_id": "999"})
        assert "ERROR: Note '999' not found" in result[0]

    async def test_update_note_requires_id(self):
        result = await run_tool("update_note", {"title": "T"})
        assert result[0] == "ERROR: note_id required."

    async def test_update_note_invalid_id(self):
        result = await run_tool("update_note", {"note_id": "x", "title": "T"})
        assert "ERROR: Note 'x' not found" in result[0]

    async def test_delete_note_resolves_list_number(self):
        cached = [{"id": 7, "title": "Old"}]
        with patch("prompt.get_notes_context", new=AsyncMock(return_value=cached)), \
             patch("nextcloud_notes.delete_note", new=AsyncMock(return_value="OK Note deleted.")) as dn:
            result = await run_tool("delete_note", {"note_id": 1}, context={"session_id": "s1"})
        dn.assert_awaited_once_with(7)
        assert result[0] == "OK Note deleted."

    async def test_delete_note_out_of_range_refused(self):
        cached = [{"id": 7, "title": "Old"}]
        with patch("prompt.get_notes_context", new=AsyncMock(return_value=cached)), \
             patch("nextcloud_notes.delete_note", new=AsyncMock()) as dn:
            result = await run_tool("delete_note", {"note_id": "3"}, context={"session_id": "s1"})
        assert "ERROR: Note '3' not found" in result[0]
        dn.assert_not_awaited()

    async def test_delete_note_requires_id(self):
        result = await run_tool("delete_note", {})
        assert result[0] == "ERROR: note_id required."

    async def test_search_notes_requires_query(self):
        result = await run_tool("search_notes", {})
        assert result[0] == "ERROR: query required."

    async def test_search_notes_calls_handler(self):
        with patch("nextcloud_notes.search_notes", new=AsyncMock(return_value=("found", []))) as sn:
            result = await run_tool("search_notes", {"query": "  travel  "})
        sn.assert_awaited_once_with("travel")
        assert result[0] == "found"

    async def test_notes_exception_is_sanitized(self):
        with patch("nextcloud_notes.list_notes", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await run_tool("list_notes", {})
        assert result[0] == "ERROR: Notes operation failed. Check server logs."


class TestTasksTools:
    async def test_create_task_requires_summary(self):
        result = await run_tool("create_task", {})
        assert "CLARIFY_REQUIRED" in result[0]

    async def test_create_task_calls_handler(self):
        with patch("nextcloud_tasks.create_task", new=AsyncMock(return_value=("created", "test-uid"))) as ct:
            result = await run_tool("create_task", {"summary": "Buy milk", "due": "2026-08-17", "priority": 2, "notes": "n"})
        ct.assert_awaited_once_with(summary="Buy milk", due="2026-08-17", priority=2, notes="n")
        assert result[0] == "created"

    async def test_create_task_invalid_priority(self):
        result = await run_tool("create_task", {"summary": "X", "priority": "high"})
        assert result[0] == "ERROR: 'priority' must be a valid number, got: 'high'"

    async def test_list_tasks_show_completed_flag(self):
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("[]", []))) as lt:
            result = await run_tool("list_tasks", {"show_completed": True})
        lt.assert_awaited_once_with(show_completed=True)
        assert result[0] == "[]"

    async def test_list_tasks_string_false_is_false(self):
        """bool('false') would wrongly enable show_completed."""
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(return_value=("[]", []))) as lt:
            result = await run_tool("list_tasks", {"show_completed": "false"})
        lt.assert_awaited_once_with(show_completed=False)
        assert result[0] == "[]"

    async def test_complete_task_resolves_list_number_to_uid(self):
        cached = [{"uid": "uid-abc-123", "summary": "Buy milk"}]
        with patch("prompt.get_tasks_context", new=AsyncMock(return_value=cached)), \
             patch("nextcloud_tasks.complete_task", new=AsyncMock(return_value="OK 'Buy milk' marked as done.")) as ct:
            result = await run_tool("complete_task", {"uid": "1"}, context={"session_id": "s1"})
        ct.assert_awaited_once_with("uid-abc-123")
        assert result[0].startswith("OK")

    async def test_complete_task_rejects_truncated_uid_string(self):
        """A truncated UID copied from old-style output must be refused."""
        cached = [{"uid": "uid-abc-123", "summary": "Buy milk"}]
        with patch("prompt.get_tasks_context", new=AsyncMock(return_value=cached)), \
             patch("nextcloud_tasks.complete_task", new=AsyncMock()) as ct:
            result = await run_tool("complete_task", {"uid": "uid-abc-123..."}, context={"session_id": "s1"})
        assert "ERROR: Task 'uid-abc-123...' not found" in result[0]
        ct.assert_not_awaited()

    async def test_delete_task_requires_uid(self):
        result = await run_tool("delete_task", {})
        assert result[0] == "ERROR: uid required."

    async def test_delete_task_out_of_range_refused(self):
        cached = [{"uid": "uid-abc-123", "summary": "Buy milk"}]
        with patch("prompt.get_tasks_context", new=AsyncMock(return_value=cached)), \
             patch("nextcloud_tasks.delete_task", new=AsyncMock()) as dt:
            result = await run_tool("delete_task", {"uid": 4}, context={"session_id": "s1"})
        assert "ERROR: Task '4' not found" in result[0]
        dt.assert_not_awaited()

    async def test_list_emails_negative_limit_rejected(self):
        mc = _mail_client()
        with patch("mail.get_active_mail_client", return_value=mc):
            result = await run_tool("list_emails", {"limit": -5})
        assert result[0].startswith("ERROR: 'limit' must be >= 1")
        mc.get_messages.assert_not_awaited()

    async def test_complete_task_requires_uid(self):
        result = await run_tool("complete_task", {})
        assert result[0] == "ERROR: uid required."

    async def test_search_tasks_requires_query(self):
        result = await run_tool("search_tasks", {})
        assert result[0] == "ERROR: query required."

    async def test_search_tasks_calls_handler(self):
        with patch("nextcloud_tasks.search_tasks", new=AsyncMock(return_value=("found", []))) as st:
            result = await run_tool("search_tasks", {"query": "milk"})
        st.assert_awaited_once_with("milk")
        assert result[0] == "found"

    async def test_tasks_exception_returns_tool_name(self):
        with patch("nextcloud_tasks.list_tasks", new=AsyncMock(side_effect=RuntimeError("boom"))):
            result = await run_tool("list_tasks", {})
        assert result[0] == "ERROR: list_tasks failed"


class TestUpdateNoteRealPath:
    """A1 regression: update_note must forward category/tags through the REAL
    async wrapper to the API client instead of raising TypeError.
    """

    def _fake_client(self):
        client = MagicMock()
        client.update_note = MagicMock(return_value={"id": 42, "title": "T"})
        return client

    async def test_wrapper_accepts_category_and_tags(self):
        import nextcloud_notes as nn
        client = self._fake_client()
        with patch.object(nn, "_get_client", return_value=client):
            result = await nn.update_note(42, title="T", content="C", category="work", tags=["a"])
        assert result == "OK Note updated."
        client.update_note.assert_called_once_with(42, "T", "C", "work", ["a"])

    async def test_wrapper_not_found(self):
        import nextcloud_notes as nn
        client = self._fake_client()
        client.update_note = MagicMock(return_value=None)
        with patch.object(nn, "_get_client", return_value=client):
            result = await nn.update_note(42, title="T")
        assert result == "ERROR: Note not found."

    async def test_dispatcher_end_to_end_passes_category_tags(self):
        """Full chain: run_tool → positional resolution → wrapper → client."""
        import nextcloud_notes as nn
        client = self._fake_client()
        cached = [{"id": 42, "title": "Old"}]
        with patch.object(nn, "_get_client", return_value=client), \
             patch("prompt.get_notes_context", new=AsyncMock(return_value=cached)):
            result = await run_tool(
                "update_note",
                {"note_id": 1, "title": "Yeni", "category": "kişisel", "tags": ["a", "b"]},
                context={"session_id": "s1"},
            )
        assert result[0] == "OK Note updated."
        client.update_note.assert_called_once_with(42, "Yeni", None, "kişisel", ["a", "b"])


class TestAsPosition:
    """_as_position must tolerate the float positions litert emits (1.0)."""

    def test_int_passes(self):
        assert _as_position(2) == 2

    def test_integral_float_accepted(self):
        # Regression: gemma emitted note_id=1.0 -> strict int check failed
        assert _as_position(1.0) == 1
        assert _as_position(3.0) == 3

    def test_fractional_float_rejected(self):
        assert _as_position(1.5) is None

    def test_numeric_string_variants(self):
        assert _as_position(" 3.") == 3
        assert _as_position("2.0") == 2
        assert _as_position("1") == 1

    def test_garbage_rejected(self):
        assert _as_position("abc") is None
        assert _as_position(True) is None
        assert _as_position(None) is None


from tools.dispatcher import _as_position  # noqa: E402


class TestIsToolSuccess:
    """Audit success classification: ERROR and CLARIFY_REQUIRED are failures."""

    def test_error_prefix_is_failure(self):
        from tools.dispatcher import is_tool_success

        assert not is_tool_success("ERROR: failed")

    def test_empty_is_failure(self):
        from tools.dispatcher import is_tool_success

        assert not is_tool_success("")
        assert not is_tool_success(("", None))

    def test_clarify_string_is_not_success(self):
        from tools.dispatcher import is_tool_success

        assert not is_tool_success(
            "CLARIFY_REQUIRED: The task has no text. Ask the user ONE short question."
        )

    def test_clarify_tuple_is_not_success(self):
        from tools.dispatcher import is_tool_success

        assert not is_tool_success(("CLARIFY_REQUIRED: missing start time", None))

    def test_normal_result_is_success(self):
        from tools.dispatcher import is_tool_success

        assert is_tool_success("OK Note created.")
        assert is_tool_success(("created", "test-uid"))


class TestChipOrigin:
    """Chip-sourced create/send requests must clarify, never execute."""

    async def test_create_task_clarifies_even_with_summary(self):
        with patch("nextcloud_tasks.create_task", new=AsyncMock(return_value=("created", "test-uid"))) as ct:
            result = await run_tool("create_task", {"summary": "yeni görev"},
                                    context={"session_id": "s1", "_origin": "chip"})
        ct.assert_not_awaited()
        assert "CLARIFY_REQUIRED" in result[0]

    async def test_create_note_clarifies_even_with_content(self):
        with patch("nextcloud_notes.create_note", new=AsyncMock(return_value="OK")) as cn:
            result = await run_tool("create_note", {"title": "T", "content": "C"},
                                    context={"session_id": "s1", "_origin": "chip"})
        cn.assert_not_awaited()
        assert "CLARIFY_REQUIRED" in result[0]

    async def test_non_chip_flow_unaffected(self):
        with patch("nextcloud_tasks.create_task", new=AsyncMock(return_value=("created", "test-uid"))) as ct:
            result = await run_tool("create_task", {"summary": "süt al"},
                                    context={"session_id": "s1"})
        ct.assert_awaited_once()
        assert result[0] == "created"
