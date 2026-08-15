"""Shared HTTP client, tool-leak detection, and text cleanup for LLM modules."""
import logging
import re

import httpx

from config import LLM_TIMEOUT
from tools import TOOL_NAMES

logger = logging.getLogger("piSynapse")

_http_client: httpx.AsyncClient | None = None

# Detect when the model emits a tool call within plain text (leak).
# Historical failure mode (E4B server): the model emitted a literal
# <|tool_call|> tag (or echoed "name": "send_email" JSON) as plain text
# instead of producing a real tool_calls object. All three detectors below
# are OR'ed inside _check_tool_leak.
_TOOL_NAMES_ALTERNATION = "|".join(re.escape(n) for n in sorted(TOOL_NAMES, key=len, reverse=True))
# 1. Tool name followed by an argument payload, e.g. `get_datetime {"..."}` / `send_email(to=...)`
_TOOL_LEAK_RE = re.compile(r'\b(' + _TOOL_NAMES_ALTERNATION + r')\s*[\{\(]')
# 2. Literal tool-call tag the model may emit as text: <|tool_call|>, <tool_call>, </tool_call>
_TOOL_TAG_RE = re.compile(r'<\|?/?tool_call\|?>', re.IGNORECASE)
# 3. JSON echo of a tool_calls object: "name": "send_email" in the reply text
_TOOL_JSON_NAME_RE = re.compile(r'"name"\s*:\s*"(' + _TOOL_NAMES_ALTERNATION + r')"')
# Defensive strip: Qwen-style <think>...</think> and Gemma 4 channel tags.
# litert-lm already separates thinking into channels (never in content), but
# keep this in case the raw format ever leaks into a response.
_THINKING_STRIP_RE = re.compile(r'<think>.*?</think>|<\|channel>thought\n.*?<channel\|>', re.DOTALL)

# Strip "piSynapse:" prefix the model may prepend to responses
_PREFIX_RE = re.compile(r'^(?:piSynapse|PiSynapse|pisynapse|PISYNAPSE)\s*:\s*', re.IGNORECASE)

# Reasoning-channel wrapper tags that may surround thinking text
_REASONING_WRAP_RE = re.compile(r'<\|channel>.*?\n|<channel\|>|</?think>', re.DOTALL)


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=LLM_TIMEOUT)
    return _http_client


def _check_tool_leak(text: str) -> bool:
    if not text:
        return False
    if _TOOL_TAG_RE.search(text) or _TOOL_JSON_NAME_RE.search(text):
        return True
    if "{" not in text and "(" not in text:
        return False
    return bool(_TOOL_LEAK_RE.search(text))


def clean_reasoning(text: str) -> str:
    """Normalize raw thinking-channel text for display.

    Strips channel/tag wrappers and collapses excessive blank lines.
    """
    if not text:
        return ""
    cleaned = _REASONING_WRAP_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def strip_prefix(text: str) -> str:
    return _PREFIX_RE.sub('', text)
