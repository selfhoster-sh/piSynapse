"""Tests for tool definitions and helpers."""

from tools import (
    TOOL_GROUPS,
    TOOL_NAMES,
    TOOLS,
    _safe_int,
    get_combined_tools,
    get_tools_for_group,
    parse_tool_args,
    validate_confirm_params,
)


class TestSafeInt:
    def test_valid_int(self):
        assert _safe_int("42", 0, "test") == 42
        assert _safe_int(42, 0, "test") == 42

    def test_default_on_none(self):
        assert _safe_int(None, 10, "test") == 10

    def test_raises_on_invalid(self):
        import pytest
        with pytest.raises(ValueError, match="test"):
            _safe_int("abc", 0, "test")


class TestToolDefinitions:
    def test_all_tools_have_names(self):
        for t in TOOLS:
            assert "function" in t
            assert "name" in t["function"]

    def test_tool_names_match(self):
        defined = {t["function"]["name"] for t in TOOLS}
        assert defined == TOOL_NAMES
        assert len(TOOLS) == 22

    def test_tool_groups(self):
        for group, names in TOOL_GROUPS.items():
            for name in names:
                assert name in TOOL_NAMES, f"{name} in group {group} not in TOOL_NAMES"

    def test_get_tools_for_group(self):
        weather_tools = get_tools_for_group("weather")
        names = {t["function"]["name"] for t in weather_tools}
        assert "get_weather" in names
        assert "get_datetime" in names
        assert "create_calendar_event" not in names

    def test_get_combined_tools(self):
        combined = get_combined_tools()
        assert len(combined) > 0
        all_names = {t["function"]["name"] for t in combined}
        for names in TOOL_GROUPS.values():
            for n in names:
                assert n in all_names


class TestParseToolArgs:
    def test_dict_passthrough(self):
        assert parse_tool_args({"key": "val"}) == {"key": "val"}

    def test_json_string(self):
        assert parse_tool_args('{"key": "val"}') == {"key": "val"}

    def test_invalid_string(self):
        assert parse_tool_args("not json") == {}

    def test_none(self):
        assert parse_tool_args(None) == {}


class TestValidateConfirmParams:
    def test_send_email_missing(self):
        err = validate_confirm_params("send_email", {})
        assert err is not None
        assert "to" in err

    def test_send_email_valid(self):
        err = validate_confirm_params("send_email", {"to": "a", "subject": "b", "body": "c"})
        assert err is None

    def test_unknown_tool(self):
        assert validate_confirm_params("get_weather", {}) is None
