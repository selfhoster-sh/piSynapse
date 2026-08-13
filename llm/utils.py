"""Shared HTTP client, tool-leak detection, and text cleanup for LLM modules."""
import logging
import re

import httpx

from config import LLM_TIMEOUT
from tools import TOOL_NAMES

logger = logging.getLogger("piSynapse")

_http_client: httpx.AsyncClient | None = None

# Detect when the model emits a tool call within plain text (leak)
_TOOL_NAMES_ALTERNATION = "|".join(re.escape(n) for n in sorted(TOOL_NAMES, key=len, reverse=True))
_TOOL_LEAK_RE = re.compile(r'\b(' + _TOOL_NAMES_ALTERNATION + r')\s*[\{\(]')
_TOOL_CLEANUP_RE = re.compile(r'\b\w+\s*[\{\(].*$', re.DOTALL)
_THINKING_STRIP_RE = re.compile(r'<think>.*?</think>', re.DOTALL)

# Strip "piSynapse:" prefix the model may prepend to responses
_PREFIX_RE = re.compile(r'^(?:piSynapse|PiSynapse|pisynapse|PISYNAPSE)\s*:\s*', re.IGNORECASE)


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=LLM_TIMEOUT)
    return _http_client


def _check_tool_leak(text: str) -> bool:
    if not text:
        return False
    if "{" not in text and "(" not in text:
        return False
    return bool(_TOOL_LEAK_RE.search(text))


def strip_prefix(text: str) -> str:
    return _PREFIX_RE.sub('', text)
