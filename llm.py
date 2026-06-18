#!/usr/bin/env python3
"""
piSynapse LLM Bridge
Handles Ollama communication via native tool calling, and external
integrations (Nextcloud CalDAV, Gmail, Weather).
"""

import httpx
import json
import os
import asyncio
import logging
from datetime import datetime, timedelta
from nextcloud_auth import get_nextcloud_client
from gmail import get_mail_client
from memory import save_memory

logger = logging.getLogger("piSynapse")

OLLAMA_BASE_URL         = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL               = os.getenv("LLM_MODEL",        "gemma4:e2b")
LLM_NUM_CTX             = int(os.getenv("LLM_NUM_CTX",    "4096"))
LLM_NUM_THREAD          = int(os.getenv("LLM_NUM_THREAD", "4"))
LLM_NUM_BATCH           = int(os.getenv("LLM_NUM_BATCH",  "256"))
LLM_MAX_TOOL_ITERATIONS = int(os.getenv("LLM_MAX_TOOL_ITERATIONS", "5"))
DEFAULT_CITY            = os.getenv("DEFAULT_CITY", "")

# Tools requiring user confirmation before execution
CONFIRM_TOOLS = {"send_email", "delete_calendar_event"}

# Reusable async HTTP client
_http_client: httpx.AsyncClient | None = None

# In-memory geocoding cache (lat/lon by city name)
_geo_cache: dict[str, tuple[str, str]] = {}


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=int(os.getenv("LLM_TIMEOUT", 120)))
    return _http_client


def _build_system_prompt() -> str:
    city_line = (
        f"\nDefault city for weather: {DEFAULT_CITY}. "
        "Use this city when the user asks about weather without specifying one."
        if DEFAULT_CITY else ""
    )
    return f"""You are piSynapse, a personal AI assistant. Be honest, helpful, and conversational. Always respond in the same language the user is writing in.{city_line}

You have tools available for weather, calendar, email, and saving long-term memories about the user. If the user explicitly asks you to do something — add/save/remember/send/delete/check something — you MUST actually call the matching tool; describing the action in your reply without calling the tool is never acceptable, even as a quick acknowledgement. Never claim you performed an action before its tool result confirms it. If a request needs several tool calls, make all of them before writing your final answer.

You are not aware of the real-world date or time on your own — always use the "Current date and time" value given to you below (never your own guess) whenever you need today's date or compute a relative date like tomorrow, this week, or next Monday. When a tool needs a date/time, convert it to ISO 8601 yourself — never ask the user to provide ISO-formatted input themselves.

When a tool parameter is optional and the user hasn't specified it, use the sensible default described for that parameter and proceed — only ask a clarifying question when a REQUIRED parameter is missing and can't reasonably be inferred.

Use the save_memory tool when the user shares — or explicitly asks you to save — a durable fact worth recalling later: a preference, a habit, a personal detail, something work-related. Do NOT call save_memory for greetings, small talk, or anything already listed under Core Memories below. If a known fact has simply changed, save just the updated detail instead of restating the whole thing. When in doubt about an unprompted save, don't save it — but if the user explicitly asks you to remember or save something, always call the tool."""


SYSTEM_PROMPT = _build_system_prompt()


def _current_datetime_context() -> str:
    """Fresh date/time context injected into every request — the model
    should never have to guess or call a tool just to know what day it is."""
    now = datetime.now()
    return f'\n\nCurrent date and time: {now.strftime("%Y-%m-%d %H:%M")} ({now.strftime("%A")}).'

# ── Tool Definitions (Ollama native tool-calling schema) ─────────────────────
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "City name. Omit to use the user's default city."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_datetime",
            "description": "Get the current date and time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Add a new event to the user's calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title."},
                    "start_time": {"type": "string", "description": "Start time in ISO 8601 format, e.g. 2026-06-20T14:00:00."},
                    "duration_minutes": {"type": "integer", "description": "Event length in minutes. Defaults to 60."},
                },
                "required": ["summary", "start_time"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar_events",
            "description": "List upcoming calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "How many days ahead to look. Defaults to 7."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Delete a calendar event by its title. Requires user confirmation before running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Title (or part of it) of the event to delete."},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_emails",
            "description": "List recent emails from the inbox.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max number of emails to return. Defaults to 10."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_email",
            "description": "Read the full content of one email by its ID (from list_emails or search_emails results).",
            "parameters": {
                "type": "object",
                "properties": {
                    "message_id": {"type": "string", "description": "The email's ID."},
                },
                "required": ["message_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email. Requires user confirmation before running.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient email address."},
                    "subject": {"type": "string", "description": "Email subject."},
                    "body": {"type": "string", "description": "Email body text."},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails",
            "description": "Search emails by subject or sender keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term."},
                    "limit": {"type": "integer", "description": "Max number of results. Defaults to 10."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": (
                "Save a durable, long-term fact about the user for future conversations. "
                "Only call this for genuinely new information — never for greetings, small "
                "talk, or facts already shown under Core Memories."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact to remember, written as a short standalone sentence."},
                    "category": {
                        "type": "string",
                        "enum": ["personal", "preference", "habit", "work", "general"],
                        "description": "Best-fitting category for this memory.",
                    },
                },
                "required": ["content"],
            },
        },
    },
]


def _parse_tool_args(raw) -> dict:
    """Tool call arguments normally arrive as a dict, but some model
    templates emit them as a JSON-encoded string — handle both safely."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


# ── Nextcloud CalDAV Integration ─────────────────────────────────────────────

def _get_primary_calendar(client):
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        raise Exception("No calendar found on Nextcloud.")
    return calendars[0]

def _nc_create_event(client, summary, start_time_str, duration_minutes):
    calendar = _get_primary_calendar(client)
    start_dt = datetime.fromisoformat(start_time_str)
    end_dt   = start_dt + timedelta(minutes=duration_minutes)
    ical = "\r\n".join([
        "BEGIN:VCALENDAR", "VERSION:2.0",
        "PRODID:-//piSynapse//EN",
        "BEGIN:VEVENT",
        f"SUMMARY:{summary}",
        f"DTSTART;VALUE=DATE-TIME:{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;VALUE=DATE-TIME:{end_dt.strftime('%Y%m%dT%H%M%S')}",
        "END:VEVENT", "END:VCALENDAR",
    ]) + "\r\n"
    calendar.add_event(ical)
    return f"✅ '{summary}' added to calendar."

def _nc_list_events(client, days_ahead):
    calendar = _get_primary_calendar(client)
    start  = datetime.now()
    end    = start + timedelta(days=days_ahead)
    events = calendar.date_search(start, end)
    if not events:
        return f"Next {days_ahead} days: no events."
    lines = []
    for ev in events:
        d   = ev.vobject_instance.vevent
        s   = getattr(d, "summary", getattr(d, "description", "Untitled")).value
        st  = d.dtstart.value
        ts  = st.strftime("%Y-%m-%d %H:%M") if hasattr(st, "strftime") else str(st)
        lines.append(f"- {ts} | {s}")
    return "📅 Events:\n" + "\n".join(lines)

def _nc_list_events_today(client) -> list[dict]:
    """Structured today's events for the widget."""
    from datetime import date
    calendar = _get_primary_calendar(client)
    today    = datetime.combine(date.today(), datetime.min.time())
    tomorrow = today + timedelta(days=1)
    events   = calendar.date_search(today, tomorrow)
    result   = []
    for ev in events:
        d  = ev.vobject_instance.vevent
        s  = getattr(d, "summary", "Untitled").value
        st = d.dtstart.value
        ts = st.strftime("%H:%M") if hasattr(st, "strftime") else str(st)
        result.append({"time": ts, "title": s})
    return sorted(result, key=lambda x: x["time"])

def _nc_delete_event(client, summary):
    calendar = _get_primary_calendar(client)
    events   = calendar.date_search(
        datetime.now() - timedelta(days=30),
        datetime.now() + timedelta(days=90)
    )
    for ev in events:
        d = ev.vobject_instance.vevent
        s = getattr(d, "summary", "").value
        if summary.lower() in s.lower():
            ev.delete()
            return f"✅ '{s}' deleted from calendar."
    return f"'{summary}' not found."

# ── Gmail (IMAP/SMTP) Integration ────────────────────────────────────────────

async def _run_mail_tool(name: str, params: dict) -> str:
    mc = get_mail_client()
    if not mc:
        return "ERROR: Gmail connection failed. Check .env configuration."
    ACCOUNT_ID = 1
    MAILBOX_ID = "INBOX"
    try:
        if name == "list_emails":
            limit = params.get("limit", 10)
            msgs  = await mc.get_messages(ACCOUNT_ID, MAILBOX_ID, limit)
            if not msgs:
                return "Inbox is empty."
            lines = ["📬 Recent Emails:\n"]
            for i, m in enumerate(msgs, 1):
                lines += [
                    f"{i}. 📧 From: {m.get('from','?')}",
                    f"   📝 Subject: {m.get('subject','(no subject)')}",
                    f"   📅 Date: {m.get('date','?')}",
                    f"   🆔 ID: {m.get('id')}",
                ]
                bp = m.get("body","")
                if bp:
                    lines.append(f"   📄 Preview: {bp[:200]}…")
                lines.append("")
            return "\n".join(lines)

        elif name == "read_email":
            mid = params.get("message_id")
            if not mid:
                return "ERROR: message_id required."
            m = await mc.get_message(ACCOUNT_ID, MAILBOX_ID, mid)
            if not m:
                return "Email not found."
            return (f"📧 Email Details\n\nFrom: {m.get('from','?')}\n"
                    f"Subject: {m.get('subject','?')}\nDate: {m.get('date','?')}\n\n"
                    f"Content:\n{m.get('body','')[:1500]}")

        elif name == "send_email":
            to, subj, body = params.get("to"), params.get("subject"), params.get("body")
            if not all([to, subj, body]):
                return "ERROR: 'to', 'subject' and 'body' are required."
            ok = await mc.send_message(ACCOUNT_ID, to, subj, body)
            return f"✅ Email sent!\nTo: {to}\nSubject: {subj}" if ok else "❌ Failed to send."

        elif name == "search_emails":
            q = params.get("query")
            if not q:
                return "ERROR: 'query' required."
            results = await mc.search_messages(ACCOUNT_ID, q, params.get("limit", 10))
            if not results:
                return f"'{q}' no results found."
            lines = [f"🔍 '{q}' Results:\n"]
            for i, m in enumerate(results, 1):
                lines.append(f"{i}. {m.get('from','?')} — {m.get('subject','?')}")
                bp = m.get("body","")
                if bp:
                    lines.append(f"   {bp[:150]}…")
                lines.append("")
            return "\n".join(lines)

    except Exception as e:
        return f"Gmail Error: {e}"
    return "Tool not found."

# ── Unified Tool Dispatcher ──────────────────────────────────────────────────

async def run_tool(name: str, params: dict, context: dict | None = None) -> str:
    context = context or {}

    if name == "get_datetime":
        return f"Current: {datetime.now().strftime('%d %B %Y, %A, %H:%M')}"

    if name == "get_weather":
        city   = params.get("city") or DEFAULT_CITY or "London"
        client = _get_client()
        try:
            if city not in _geo_cache:
                geo = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": city, "format": "json", "limit": 1},
                    headers={"User-Agent": "piSynapse/1.0"}
                )
                gd = geo.json()
                if not gd:
                    return f"City not found: {city}"
                _geo_cache[city] = (gd[0]["lat"], gd[0]["lon"])
            lat, lon = _geo_cache[city]
            w = await client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,apparent_temperature,weathercode",
                    "timezone": "auto"
                },
                headers={"User-Agent": "piSynapse/1.0"}
            )
            c = w.json()["current"]
            return f"{city}: {c['temperature_2m']}°C, feels like {c['apparent_temperature']}°C"
        except Exception as e:
            return f"Weather error: {e}"

    if name in {"create_calendar_event", "list_calendar_events", "delete_calendar_event"}:
        nc = get_nextcloud_client()
        if not nc:
            return "ERROR: Nextcloud credentials missing."
        try:
            if name == "create_calendar_event":
                s = params.get("summary","New Event")
                st = params.get("start_time")
                dur = params.get("duration_minutes", 60)
                if not st:
                    return "ERROR: start_time required."
                return await asyncio.to_thread(_nc_create_event, nc, s, st, dur)
            elif name == "list_calendar_events":
                return await asyncio.to_thread(_nc_list_events, nc, params.get("days_ahead", 7))
            elif name == "delete_calendar_event":
                s = params.get("summary")
                if not s:
                    return "ERROR: Event name required."
                return await asyncio.to_thread(_nc_delete_event, nc, s)
        except Exception as e:
            return f"Nextcloud Error: {e}"

    if name in {"list_emails", "read_email", "send_email", "search_emails"}:
        return await _run_mail_tool(name, params)

    if name == "save_memory":
        content = (params.get("content") or "").strip()
        if not content:
            return "ERROR: content required."
        category = params.get("category", "general")
        await save_memory(content=content, category=category, user_id=context.get("user_id"))
        return "Memory saved."

    return "Tool not found."

# ── Conversation Summarization ───────────────────────────────────────────────
# Used to fold messages that have aged out of the recent history window into a
# short running summary, so context isn't lost while keeping token usage low.

SUMMARY_SYSTEM_PROMPT = (
    "You maintain a short running summary of an ongoing conversation between a "
    "user and an AI assistant. Update the existing summary with the new messages "
    "below, keeping only information useful for future context: facts about the "
    "user, ongoing tasks, decisions and preferences. Keep it to a short paragraph. "
    "Reply in the same language as the conversation. Output ONLY the updated "
    "summary text, with no preamble or extra commentary."
)


async def summarize_conversation(messages: list[dict], previous_summary: str = "") -> str:
    """Condenses a batch of older conversation turns into an updated running
    summary. Runs as a lightweight background call (low num_predict, no
    thinking) so it doesn't compete much with the user-facing response."""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
    user_content = (
        f"Existing summary:\n{previous_summary or '(none yet)'}\n\n"
        f"New messages:\n{transcript}\n\n"
        "Updated summary:"
    )

    client = _get_client()
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.2,
            "num_ctx":     LLM_NUM_CTX,
            "num_predict": 300,
        },
        "keep_alive": os.getenv("LLM_KEEP_ALIVE", "24h"),
    }
    try:
        resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except Exception as e:
        logger.error(f"Summarization failed: {e}")
        return previous_summary

# ── Ollama Non-Streaming Bridge ──────────────────────────────────────────────

async def chat_with_ollama(
    messages: list[dict],
    memories: list[dict] = [],
    think: bool = False,
    summary: str = "",
    user_id: str | None = None,
) -> dict:
    """
    Returns a dict:
        {"reply": str, "pending_action": dict | None, "memories_saved": int}

    pending_action is set instead of reply when the model wants to call a
    tool in CONFIRM_TOOLS (send_email, delete_calendar_event) — the caller
    must get user approval before running it via run_tool().
    """
    mem_ctx = ""
    if memories:
        mem_ctx = "\n\nCore Memories:\n" + "\n".join(f"- {m['content']}" for m in memories)

    summary_ctx = ""
    if summary:
        summary_ctx = f"\n\nSummary of earlier parts of this conversation (not repeated below):\n{summary}"

    datetime_ctx = _current_datetime_context()

    client  = _get_client()
    context = {"user_id": user_id}
    current_msgs    = list(messages)
    memories_saved  = 0

    for iteration in range(LLM_MAX_TOOL_ITERATIONS):
        payload = {
            "model":    LLM_MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT + datetime_ctx + mem_ctx + summary_ctx}] + current_msgs,
            "stream":   False,
            "think":    think,
            "tools":    TOOLS,
            "options": {
                "temperature": 0.2,
                "top_p":       0.9,
                "num_ctx":     LLM_NUM_CTX,
                "num_thread":  LLM_NUM_THREAD,
                "num_batch":   LLM_NUM_BATCH,
            },
            "keep_alive": os.getenv("LLM_KEEP_ALIVE", "24h"),
        }

        try:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
            resp.raise_for_status()
            message = resp.json()["message"]
        except Exception as e:
            return {"reply": f"Engine Error: Cannot reach Ollama. Details: {e}",
                    "pending_action": None, "memories_saved": memories_saved}

        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            return {"reply": message.get("content", ""), "pending_action": None,
                    "memories_saved": memories_saved}

        # If any call in this batch needs confirmation, stop before running
        # anything else in the batch — risky actions never execute silently.
        for call in tool_calls:
            tool_name = call.get("function", {}).get("name", "")
            if tool_name in CONFIRM_TOOLS:
                tool_args = _parse_tool_args(call["function"].get("arguments"))
                return {"reply": "", "pending_action": {"tool": tool_name, "params": tool_args},
                        "memories_saved": memories_saved}

        current_msgs.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": tool_calls})
        for call in tool_calls:
            fn        = call.get("function", {})
            tool_name = fn.get("name", "")
            tool_args = _parse_tool_args(fn.get("arguments"))
            result    = await run_tool(tool_name, tool_args, context)
            if tool_name == "save_memory" and not result.startswith("ERROR"):
                memories_saved += 1
            tool_msg = {"role": "tool", "tool_name": tool_name, "content": result}
            if call.get("id"):
                tool_msg["tool_call_id"] = call["id"]
            current_msgs.append(tool_msg)

    logger.warning(f"Max tool iterations ({LLM_MAX_TOOL_ITERATIONS}) exceeded")
    return {"reply": "I made several tool calls but couldn't reach a final answer — please try rephrasing.",
            "pending_action": None, "memories_saved": memories_saved}


# ── Ollama Streaming Bridge ──────────────────────────────────────────────────
async def chat_with_ollama_stream(
    messages: list[dict],
    memories: list[dict] = [],
    think: bool = False,
    summary: str = "",
    user_id: str | None = None,
):
    """
    Async generator — yields tokens one by one.

    Yields:
        {"token": str}                       — text chunk for UI
        {"confirm": dict}                    — action requiring confirmation
        {"error": str}                        — error message
        {"done": True, "memories_saved": int} — stream complete

    Strategy:
    - Buffer content until either the model commits to a tool call (its
      message carries a non-empty tool_calls list) or ~80 chars/done is
      reached with no tool call — whichever comes first.
    - If no tool call appears, stream tokens directly (first word ~3-5s).
    - If a tool call appears, run it via the non-streaming loop, then stream
      the final answer once the model has the tool results.
    """
    mem_ctx = ""
    if memories:
        mem_ctx = "\n\nCore Memories:\n" + "\n".join(f"- {m['content']}" for m in memories)

    summary_ctx = ""
    if summary:
        summary_ctx = f"\n\nSummary of earlier parts of this conversation (not repeated below):\n{summary}"

    datetime_ctx = _current_datetime_context()

    client  = _get_client()
    context = {"user_id": user_id}
    current_msgs   = list(messages)
    memories_saved = 0

    TOOL_DETECT_CHARS = 80

    for iteration in range(LLM_MAX_TOOL_ITERATIONS):
        payload = {
            "model":   LLM_MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT + datetime_ctx + mem_ctx + summary_ctx}] + current_msgs,
            "stream":  True,
            "think":   think,
            "tools":   TOOLS,
            "options": {
                "temperature": 0.2,
                "top_p":       0.9,
                "num_ctx":     LLM_NUM_CTX,
                "num_thread":  LLM_NUM_THREAD,
                "num_batch":   LLM_NUM_BATCH,
            },
            "keep_alive": os.getenv("LLM_KEEP_ALIVE", "24h"),
        }

        buf            = ""
        decided        = False
        is_tool        = False
        tool_calls_acc: list = []

        try:
            async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for raw in resp.aiter_lines():
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    msg   = data.get("message", {})
                    token = msg.get("content", "")
                    tc    = msg.get("tool_calls")
                    done  = data.get("done", False)

                    if tc:
                        tool_calls_acc = tc
                    buf += token

                    if not decided:
                        if tool_calls_acc:
                            is_tool = True
                            decided = True
                        elif len(buf) >= TOOL_DETECT_CHARS or done:
                            is_tool = False
                            decided = True
                            if buf:
                                yield {"token": buf}
                                buf = ""
                    else:
                        if not is_tool and token:
                            yield {"token": token}

                    if done:
                        break

        except Exception as e:
            yield {"error": f"Ollama connection error: {e}"}
            return

        if not is_tool:
            yield {"done": True, "memories_saved": memories_saved}
            return

        # --- Tool call execution ---
        for call in tool_calls_acc:
            tool_name = call.get("function", {}).get("name", "")
            if tool_name in CONFIRM_TOOLS:
                tool_args = _parse_tool_args(call["function"].get("arguments"))
                yield {"confirm": {"tool": tool_name, "params": tool_args}}
                return

        current_msgs = current_msgs + [
            {"role": "assistant", "content": "", "tool_calls": tool_calls_acc},
        ]
        for call in tool_calls_acc:
            fn        = call.get("function", {})
            tool_name = fn.get("name", "")
            tool_args = _parse_tool_args(fn.get("arguments"))
            result    = await run_tool(tool_name, tool_args, context)
            if tool_name == "save_memory" and not result.startswith("ERROR"):
                memories_saved += 1
            tool_msg = {"role": "tool", "tool_name": tool_name, "content": result}
            if call.get("id"):
                tool_msg["tool_call_id"] = call["id"]
            current_msgs.append(tool_msg)
        # Loop continues — next iteration sends the tool results back to the model.

    yield {"done": True, "memories_saved": memories_saved}
