"""Shared HTTP client, tool-leak detection, and text cleanup for LLM modules."""
import json
import logging
import re

import httpx

from config import get
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

# Literal leaked tool call the model may write as plain text instead of a
# structured tool_calls object, e.g. `<|tool_call|>call:read_email{id:5}<tool_call|>`.
# Tolerates Gemma's mangled channel-tag variants (`<|tool_call>` / `<tool_call|>`),
# doubled braces (`call:list_notes{{}}` — seen when the native call template leaks
# through think mode) and a missing argument payload entirely.
# Group 1 = tool name, group 2 = `key:value` argument payload (optional).
_TOOL_CALL_TAG_RE = re.compile(
    r'<\|?/?tool_call\|?>\s*call:(\w+)\s*(?:\{\{?([^{}]*)\}?\})?\s*<\|?/?tool_call\|?>',
    re.DOTALL,
)

# Tag-less residue: a leak whose channel tags were already stripped surfaces
# as a bare `call:name{{...}}` fragment (observed in saved history). Restricted
# to known tool names so ordinary prose containing "call:" is never touched.
# Closing braces are optional inside the payload so truncated-stream variants
# like `call:read_email{id:` (no closing brace/tag) are consumed entirely.
_TOOL_CALL_BARE_RE = re.compile(
    r'\bcall:(' + _TOOL_NAMES_ALTERNATION + r')\s*(?:\{\{?([^{}]*)(?:\}?\})?)?'
)


def parse_leaked_tool_call(text: str) -> dict | None:
    """Recover a tool call the model emitted as plain text.

    Some small models write `<|tool_call|>call:read_email{id:5}<tool_call|>`
    in the content channel instead of producing a real ``tool_calls`` object.
    Returns an OpenAI-style tool-call dict when found, else ``None``.
    """
    if not text:
        return None
    m = _TOOL_CALL_TAG_RE.search(text) or _TOOL_CALL_BARE_RE.search(text)
    if not m:
        return None
    name, args_src = m.group(1), m.group(2) or ""
    args: dict = {}
    for kq, ku, val in re.findall(r'(?:"(\w+)"|(\w+))\s*:\s*("(?:\\.|[^"])*"|[^,}\s]+)', args_src):
        key = kq or ku
        if val.startswith('"') and val.endswith('"'):
            try:
                val = json.loads(val)
            except (ValueError, TypeError):
                val = val[1:-1]
        elif val.isdigit():
            val = int(val)
        args[key] = val
    return {
        "id": f"leaked_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


_FENCE_RE = re.compile(r"(```.*?```)", re.DOTALL)


def _collapse_spaces_outside_fences(text: str) -> str:
    """Collapse runs of spaces/tabs, but never inside ``` code fences —
    collapsing there would corrupt indentation in code-containing replies.
    """
    parts = _FENCE_RE.split(text)
    return "".join(
        p if p.startswith("```") else re.sub(r"[ \t]{2,}", " ", p) for p in parts
    )


def strip_tool_leaks(text: str) -> str:
    """Remove leaked <|tool_call|> fragments from assistant text."""
    if not text:
        return text
    text = _TOOL_CALL_TAG_RE.sub("", text)
    text = _TOOL_CALL_BARE_RE.sub("", text)
    text = _TOOL_TAG_RE.sub("", text)
    return _collapse_spaces_outside_fences(text).strip()


def _get_client() -> httpx.AsyncClient:
    global _http_client
    timeout = float(get("LLM_TIMEOUT", 600))
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=timeout)
        return _http_client
    try:
        if _http_client.timeout.connect != timeout:
            _http_client.timeout = httpx.Timeout(timeout)
    except Exception:
        pass
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
