"""Shared HTTP client, tool-leak detection, and text cleanup for LLM modules."""
import json
import logging
import re

import httpx

from config import get
from tools import TOOL_NAMES

logger = logging.getLogger("piSynapse")

_http_client: httpx.AsyncClient | None = None

# Anti-loop guards (2026-08-22 notes tool-call loop incident): a small model
# may keep re-emitting the same tool call instead of summarizing its result.
# Shared by the streaming (llm/stream.py) and non-streaming (llm/chat.py) loops.
FINALIZE_NUDGE = (
    "[System note: your previous tool call was already executed and its full "
    "result is in the conversation above. Do NOT call any tool again — "
    "summarize that result for the user in plain text now.]"
)
EMPTY_ANSWER_FALLBACK = (
    "İşlem tamamlandı ancak özet oluşturulamadı. Lütfen isteğini tekrar dener misin?"
)

# -- Lookup-vs-mutation classification -------------------------------#
# Tools that only gather data. When a round calls nothing but lookups and the
# user's request asked for an action on what was found, a small model tends to
# stop and summarise instead of completing the mutation — the eval's dominant
# failure mode (cal-03/cal-05, task-04, note-03). These sets drive the
# deterministic continuation nudge in the tool loops.
LOOKUP_TOOLS = {
    "get_datetime", "get_weather",
    "list_emails", "read_email", "search_emails",
    "list_calendar_events", "list_notes", "read_note", "search_notes",
    "list_tasks", "search_tasks",
}

MUTATION_TOOLS = {
    "create_calendar_event", "create_note", "create_task",
    "update_calendar_event", "update_note",
    "delete_calendar_event", "delete_note", "delete_task",
    "complete_task", "send_email",
}


def is_lookup_tool(name: str) -> bool:
    return name in LOOKUP_TOOLS


def is_mutation_tool(name: str) -> bool:
    return name in MUTATION_TOOLS


# User-request cues that the message wants an ACTION on data the model must
# look up first. Turkish stems deliberately match with suffixes ("göndermem
# lazım"), other languages match whole words so "add" never fires on
# "address". Only feeds a nudge — misses are harmless, over-matching only
# appends one extra instruction to the context.
_ACTION_CUE_STEMS = (
    "hatırlat", "hatirlat", "kur", "oluştur", "olustur", "ekle", "kaydet",
    "sil", "kaldır", "kaldir", "düzenle", "duzenle", "güncelle", "guncelle",
    "değiştir", "degistir", "tamamla", "tamamlandı", "tamamlandi", "işaretle",
    "isaretle", "gönder", "gonder", "yolla", "hazırla", "ertele", "cevapla",
    "yeni etkinlik", "yeni görev", "yeni gorev", "yeni not", "yeni hatırlatıcı",
)
_ACTION_CUE_WORDS = (
    "create", "add", "make", "delete", "remove", "erase", "update", "edit",
    "change", "modify", "reschedule", "postpone", "complete", "mark as done",
    "send", "reply", "draft", "schedule", "set up", "remind",
    "löschen", "loeschen", "erstellen", "hinzufügen", "hinzufuegen", "ändern",
    "aendern", "verschieben", "erledigen", "senden", "schreiben", "beantworten",
    "erinnere", "supprime", "supprimer", "créer", "creer", "ajouter", "modifier",
    "changer", "déplacer", "deplacer", "envoyer", "répondre", "repondre",
    "terminer", "rappelle", "borrar", "crear", "agregar", "modificar",
    "cambiar", "mover", "enviar", "responder", "completar", "recordar",
    "recuérdame", "programar",
)
_ACTION_WORD_RE = re.compile(
    r"\b(" + "|".join(sorted(_ACTION_CUE_WORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def user_requested_action(user_text: str) -> bool:
    """True when the user's request clearly asks for an action on data
    (create/update/delete/complete/send/draft). Used only to decide whether
    to nudge the model to continue — never gates actual execution.
    """
    if not user_text:
        return False
    ml = user_text.lower()
    return any(stem in ml for stem in _ACTION_CUE_STEMS) or bool(_ACTION_WORD_RE.search(ml))


# Appended to the last tool result when a lookup-only round ends while the
# user's request still expects an action. Explicitly references the pattern
# the eval proved the model of record falls into (list -> stop).
CONTINUATION_NOTE = (
    "\n\n[Continuation required: the tools called so far only LOOKED information "
    "up, but the user's request asked for an action on it (create, update, "
    "delete, complete, mark done, or send). The details you need are in the "
    "results above — call the matching action tool NOW with the matching item. "
    "Do NOT write a final reply until that action has been performed.]"
)


def empty_answer_fallback() -> str:
    """User-facing fallback in the instance's UI_LANGUAGE.

    Kept as a function so setting changes apply live; the module constant
    above remains the canonical Turkish text for backwards compatibility.
    """
    from messages import get_message

    return get_message("llm_empty_reply")
MAX_IDENTICAL_EXECUTIONS = 2

# Detect when the model emits a tool call within plain text (leak).
# Historical failure mode (E4B server): the model emitted a literal
# <|tool_call|> tag (or echoed "name": "send_email" JSON) as plain text
# instead of producing a real tool_calls object. All three detectors below
# are OR'ed inside _check_tool_leak.
_TOOL_NAMES_ALTERNATION = "|".join(re.escape(n) for n in sorted(TOOL_NAMES, key=len, reverse=True))
# 1. Tool name followed by an argument payload, e.g. `get_datetime {"..."}` / `send_email(to=...)`
_TOOL_LEAK_RE = re.compile(r'\b(' + _TOOL_NAMES_ALTERNATION + r')\s*[\{\(]')
# 2. Literal tool-call tag the model may emit as text: <|tool_call|>, <tool_call>, </tool_call>
#    Tolerates pipe-vs-underscore mangling inside the tag itself (<tool|call>).
_TOOL_TAG_RE = re.compile(r'<\|?/?tool[|_]call\|?>', re.IGNORECASE)
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
    r'<\|?/?tool[|_]call\|?>\s*call:(\w+)\s*(?:\{\{?([^{}]*)\}?\})?\s*<\|?/?tool[|_]call\|?>',
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


def _is_tool_call_json(candidate: str) -> bool:
    """True when ``candidate`` parses as JSON and every item is a
    tool-call-shaped object referencing a KNOWN tool name.
    """
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError):
        return False
    items = data if isinstance(data, list) else [data]
    if not items:
        return False
    return all(
        isinstance(it, dict)
        and isinstance(it.get("name"), str)
        and it["name"] in TOOL_NAMES
        and "arguments" in it
        for it in items
    )


def _strip_json_tool_echo(text: str) -> str:
    """Remove standalone JSON echoes of tool_calls objects (per line).

    Only lines that are EXACTLY one JSON object/array of known tool calls
    are removed — JSON embedded inside prose or unknown tool names survive,
    so legitimate content is never touched. Pretty-printed multi-line echoes
    are deliberately left alone (conservative).
    """
    kept = []
    for line in text.splitlines():
        s = line.strip()
        if (
            len(s) > 1
            and s[0] in "[{"
            and s[-1] in "]}"
            and '"name"' in s
            and _is_tool_call_json(s)
        ):
            continue
        kept.append(line)
    return "\n".join(kept)


def strip_tool_leaks(text: str) -> str:
    """Remove leaked <|tool_call|> fragments from assistant text."""
    if not text:
        return text
    text = _TOOL_CALL_TAG_RE.sub("", text)
    text = _TOOL_CALL_BARE_RE.sub("", text)
    text = _TOOL_TAG_RE.sub("", text)
    text = _strip_json_tool_echo(text)
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
