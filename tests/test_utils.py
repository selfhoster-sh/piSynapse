"""Tests for piSynapse utility functions."""

from utils import clean_body_text, decode_email_header, sanitize_imap_query


def test_clean_body_text():
    assert clean_body_text("") == ""
    assert clean_body_text(None) == ""
    assert clean_body_text("hello world") == "hello world"
    assert clean_body_text("hello   world") == "hello world"
    assert clean_body_text("\nhello\nworld\n") == "hello world"


def test_sanitize_imap_query():
    assert sanitize_imap_query('hello "world"') == "hello world"
    assert sanitize_imap_query("no quotes here") == "no quotes here"
    assert sanitize_imap_query('test\\backslash') == "testbackslash"
    assert sanitize_imap_query("  spaced  ") == "spaced"


def test_decode_email_header_none():
    assert decode_email_header(None) == ""


def test_decode_email_header_plain():
    result = decode_email_header("Hello World")
    assert "Hello" in result


def test_decode_email_header_encoded():
    result = decode_email_header("=?UTF-8?B?VGXDn3Rrw7xyw6fDpQ==?=")
    assert isinstance(result, str)
