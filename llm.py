import httpx
import os
import asyncio
import re
import logging
from datetime import datetime, timedelta
from nextcloud_auth import get_nextcloud_client
from gmail import get_mail_client

logger = logging.getLogger("piSynapse")

# LLM and tool configuration
OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL         = os.getenv("LLM_MODEL", "gemma4:e2b")
LLM_TEMPERATURE   = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_TOP_P         = float(os.getenv("LLM_TOP_P", "0.9"))
LLM_KEEP_ALIVE    = os.getenv("LLM_KEEP_ALIVE", "24h")
LLM_TIMEOUT       = float(os.getenv("LLM_TIMEOUT", "120"))
LLM_MAX_ITER      = int(os.getenv("LLM_MAX_ITERATIONS", "5"))
DEFAULT_CITY      = os.getenv("DEFAULT_CITY", "Istanbul")
WEATHER_TIMEOUT   = float(os.getenv("WEATHER_TIMEOUT", "10"))

SYSTEM_PROMPT = """You are piSynapse, a personal AI assistant. Be honest, helpful, and conversational. Always respond in the same language the user is writing in.

If you need current information, calendar events, or emails to answer a request, call the relevant tool FIRST before generating a response.

Use this EXACT XML format for tool calls. You can use multiple <tool_call> blocks if needed:
<tool_call>
    <name>tool_name</name>
    <parameters>
        <param_key>value</param_key>
    </parameters>
</tool_call>

Available tools:
- get_weather: Get current weather. Params: <city>city name</city>
- get_datetime: Get current date and time. No parameters needed.
- create_calendar_event: Add event to calendar. Params: <summary>Title</summary><start_time>YYYY-MM-DDTHH:MM:SS</start_time><duration_minutes>60</duration_minutes>
- list_calendar_events: List upcoming events. Params: <days_ahead>7</days_ahead>
- delete_calendar_event: Delete event by title. Params: <summary>Event Title</summary>
- get_emails: List recent inbox emails. Params: <limit>10</limit>
- read_email: Read a specific email. Params: <message_id>id</message_id>
- send_email: Send an email. Params: <to>email</to><subject>Subject</subject><body>Body</body>
- search_emails: Search emails by keyword. Params: <query>search text</query>

CRITICAL RULES:
1. Call ONLY the tools necessary for the request.
2. If a [SYSTEM NOTE] with tool results already exists in context, do NOT call that tool again.
3. NEVER claim you sent an email or created an event before receiving tool confirmation.

LONG-TERM MEMORY:
Proactively remember facts the user shares: name, preferences, habits, work, projects, technical setup, interests.
To save a memory, append this on a NEW LINE at the VERY END of your final response:
MEMORY: [category] content

Categories: personal, preference, habit, work, general
Only append a MEMORY line if genuinely new information was shared. Do NOT output MEMORY lines during tool calls.
"""

KNOWN_TOOLS = {
    "get_weather", "get_datetime",
    "create_calendar_event", "list_calendar_events", "delete_calendar_event",
    "get_emails", "read_email", "send_email", "search_emails",
}

# Nextcloud CalDAV helper functions (blocking operations, run in thread pool)
def _nc_create_event(client, summary: str, start_time_str: str, duration_minutes: int) -> str:
    """Create calendar event on Nextcloud."""
    import vobject
    calendars = client.principal().calendars()
    if not calendars:
        return "No calendar found on Nextcloud."
    cal = vobject.iCalendar()
    cal.add("vevent")
    cal.vevent.add("summary").value = summary
    start_dt = datetime.fromisoformat(start_time_str)
    cal.vevent.add("dtstart").value = start_dt
    cal.vevent.add("dtend").value = start_dt + timedelta(minutes=duration_minutes)
    calendars[0].add_event(cal.serialize())
    return f"✅ '{summary}' added to calendar at {start_time_str}."

def _nc_list_events(client, days_ahead: int) -> str:
    """Retrieve upcoming calendar events."""
    calendars = client.principal().calendars()
    if not calendars:
        return "No calendar found on Nextcloud."
    events = calendars[0].date_search(datetime.now(), datetime.now() + timedelta(days=days_ahead))
    if not events:
        return f"No events in the next {days_ahead} days."
    lines = []
    for e in events:
        vevent = e.vobject_instance.vevent
        summary = vevent.summary.value if hasattr(vevent, "summary") else "Untitled"
        start = vevent.dtstart.value
        start_str = start.strftime("%Y-%m-%d %H:%M") if hasattr(start, "strftime") else str(start)
        lines.append(f"- {start_str} | {summary}")
    return "📅 Upcoming Events:\n" + "\n".join(lines)

def _nc_delete_event(client, summary: str) -> str:
    """Delete calendar event by title match."""
    calendars = client.principal().calendars()
    if not calendars:
        return "No calendar found on Nextcloud."
    events = calendars[0].date_search(
        datetime.now() - timedelta(days=30),
        datetime.now() + timedelta(days=90)
    )
    for e in events:
        vevent = e.vobject_instance.vevent
        ev_summary = vevent.summary.value if hasattr(vevent, "summary") else ""
        if summary.lower() in ev_summary.lower():
            e.delete()
            return f"✅ '{ev_summary}' deleted from calendar."
    return f"No event found matching '{summary}'."

# Tool execution dispatcher
async def run_tool(name: str, params: dict) -> str:
    """Execute requested tool with parameters and return result."""
    try:
        if name == "get_datetime":
            return datetime.now().strftime("%d %B %Y, %A, %H:%M")

        elif name == "get_weather":
            city = params.get("city", DEFAULT_CITY)
            async with httpx.AsyncClient(timeout=WEATHER_TIMEOUT) as http:
                # Geocode city name to coordinates
                geo_resp = await http.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": city, "format": "json", "limit": 1},
                    headers={"User-Agent": "piSynapse/1.0"}
                )
                geo = geo_resp.json()
                if not geo:
                    return f"City not found: {city}"
                lat, lon = geo[0]["lat"], geo[0]["lon"]
                # Fetch weather from Open-Meteo
                w_resp = await http.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "current": "temperature_2m,apparent_temperature",
                        "timezone": "auto",
                    }
                )
                w = w_resp.json()["current"]
                return f"{city}: {w['temperature_2m']}°C, feels like {w['apparent_temperature']}°C"

        elif name == "create_calendar_event":
            client = get_nextcloud_client()
            if not client:
                return "ERROR: Nextcloud credentials missing."
            return await asyncio.to_thread(
                _nc_create_event, client,
                params.get("summary", "New Event"),
                params.get("start_time", datetime.now().isoformat()),
                int(params.get("duration_minutes", 60))
            )

        elif name == "list_calendar_events":
            client = get_nextcloud_client()
            if not client:
                return "ERROR: Nextcloud credentials missing."
            return await asyncio.to_thread(_nc_list_events, client, int(params.get("days_ahead", 7)))

        elif name == "delete_calendar_event":
            client = get_nextcloud_client()
            if not client:
                return "ERROR: Nextcloud credentials missing."
            return await asyncio.to_thread(_nc_delete_event, client, params.get("summary", ""))

        elif name == "get_emails":
            mail = get_mail_client()
            if not mail:
                return "ERROR: Gmail credentials missing."
            messages = await mail.get_messages(0, "INBOX", int(params.get("limit", 10)))
            if not messages:
                return "Inbox is empty."
            lines = ["📬 Recent Emails:\n"]
            for i, msg in enumerate(messages, 1):
                lines.append(f"{i}. ID:{msg.get('id')} | From: {msg.get('from')} | {msg.get('subject')}")
            return "\n".join(lines)

        elif name == "read_email":
            mail = get_mail_client()
            if not mail:
                return "ERROR: Gmail credentials missing."
            msg_id = params.get("message_id")
            if not msg_id:
                return "ERROR: message_id is required."
            msg = await mail.get_message(0, "INBOX", msg_id)
            if not msg:
                return "Email not found."
            return (
                f"From: {msg.get('from')}\n"
                f"Subject: {msg.get('subject')}\n"
                f"Date: {msg.get('date')}\n\n"
                f"{msg.get('body', '')[:2000]}"
            )

        elif name == "send_email":
            mail = get_mail_client()
            if not mail:
                return "ERROR: Gmail credentials missing."
            to = params.get("to")
            if not to:
                return "ERROR: 'to' field is required."
            success = await mail.send_message(0, to, params.get("subject", ""), params.get("body", ""))
            return f"✅ Email sent to {to}." if success else "❌ Failed to send email."

        elif name == "search_emails":
            mail = get_mail_client()
            if not mail:
                return "ERROR: Gmail credentials missing."
            query = params.get("query", "")
            if not query:
                return "ERROR: 'query' is required."
            results = await mail.search_messages(0, query, int(params.get("limit", 10)))
            if not results:
                return f"No emails found for '{query}'."
            return "\n".join([f"📧 ID:{m.get('id')} | {m.get('from')} — {m.get('subject')}" for m in results])

        else:
            return f"Unknown tool: {name}"

    except Exception as e:
        logger.error(f"Tool error [{name}]: {e}")
        return f"Tool error: {str(e)}"


# Main LLM bridge with agentic tool-calling loop
async def chat_with_ollama(history: list[dict], core_memories: list[dict], user_id: str = "default") -> tuple[str, int]:
    """
    Execute multi-turn conversation with Ollama LLM, handle XML tool calls,
    execute tools, and inject results back into conversation.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Inject long-term memories if available
    if core_memories:
        memory_block = "Remembered facts about the user:\n" + "\n".join(
            f"- {m['content']}" for m in core_memories
        )
        messages.append({"role": "system", "content": memory_block})

    messages.extend(history)

    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        for iteration in range(LLM_MAX_ITER):
            payload = {
                "model": LLM_MODEL,
                "messages": messages,
                "stream": False,
                "options": {"temperature": LLM_TEMPERATURE, "top_p": LLM_TOP_P},
                "keep_alive": LLM_KEEP_ALIVE,
            }

            try:
                response = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                response.raise_for_status()
                reply = response.json()["message"]["content"]
            except Exception as e:
                logger.error(f"Ollama connection error: {e}")
                return f"Could not reach Ollama: {str(e)}", 0

            # Parse XML tool calls from response
            tool_calls = []
            for match in re.finditer(r"<tool_call>(.*?)</tool_call>", reply, re.DOTALL):
                block = match.group(1)
                name_match = re.search(r"<name>(.*?)</name>", block)
                if not name_match:
                    continue
                t_name = name_match.group(1).strip()
                t_params = {}
                param_block = re.search(r"<parameters>(.*?)</parameters>", block, re.DOTALL)
                if param_block:
                    for tag, val in re.findall(r"<([^/][^>]*)>([^<]*)</\1>", param_block.group(1)):
                        t_params[tag.strip()] = val.strip()
                tool_calls.append((t_name, t_params))

            # Malformed XML guard: request correction if tools detected but not parsed
            if "<tool_call>" in reply and not tool_calls:
                logger.warning(f"Malformed <tool_call> on iteration {iteration}, requesting correction.")
                messages.append({"role": "assistant", "content": reply})
                messages.append({
                    "role": "user",
                    "content": (
                        "⚠️ [SYSTEM WARNING]: Your <tool_call> block could not be parsed. "
                        "Please resend it with all tags properly closed: "
                        "<tool_call><name>tool_name</name><parameters><key>value</key></parameters></tool_call>"
                    )
                })
                continue

            # Execute tools and collect results
            if tool_calls:
                results = []
                for t_name, t_params in tool_calls:
                    if t_name in KNOWN_TOOLS:
                        result = await run_tool(t_name, t_params)
                        results.append(f"✓ {t_name}: {result}")
                    else:
                        results.append(f"❌ Unknown tool: {t_name}")

                # Inject tool results back into conversation
                tool_results_text = "\n".join(results)
                messages.append({"role": "assistant", "content": reply})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Tool results:\n{tool_results_text}\n\n"
                        "Now give a complete, natural response based on these results. "
                        "Do NOT call the same tool again."
                    )
                })
                continue

            # No tools called: return final response
            return reply, 0

    return "Processing limit reached. Please rephrase your request.", 0
