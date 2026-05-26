import httpx
import json
import os
import asyncio
import re
import logging
from datetime import datetime, timedelta
from nextcloud_auth import get_nextcloud_client
from gmail import get_mail_client
from memory import save_memory

logger = logging.getLogger("piSynapse")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "gemma4:e2b")

SYSTEM_PROMPT = """You are piSynapse, a personal AI assistant. Be honest, helpful, and conversational. Always respond in the same language the user is writing in.

If you need current information, calendar events, or emails to answer a request, call the relevant tool FIRST before generating a response. 

For SINGLE tool calls, use this format:
TOOL: tool_name
PARAMS: {"key": "value"}

For MULTIPLE tool calls, use this format:
TOOLS: [
  {"tool": "tool_name", "params": {"key": "value"}}
]

Available tools:
- get_weather: Get current weather. Params: {"city": "city name"}
- get_datetime: Get current date and time. Params: {}
- create_calendar_event: Add an event to the calendar. Params: {"summary": "Event Title", "start_time": "YYYY-MM-DDTHH:MM:SS", "duration_minutes": 60}
- list_calendar_events: List upcoming calendar events. Params: {"days_ahead": 7}
- delete_calendar_event: Delete a calendar event by title. Params: {"summary": "Event Title"}
- list_emails: List recent inbox emails. Params: {"limit": 10}
- read_email: Read a specific email. Params: {"message_id": 123}
- send_email: Send an email. Params: {"to": "recipient@mail.com", "subject": "Subject", "body": "Message body"}
- search_emails: Search emails by keyword. Params: {"query": "search term", "limit": 10}

CRITICAL RULES:
1. CONTEXT-AWARE TOOL CALLING: Analyze the user's request to identify PRIMARY goal and REQUIRED information. Call ONLY the tools necessary - DO NOT add irrelevant tools.
   - "Send weather summary to email" → get_weather + send_email
   - "Check calendar and reply to availability email" → list_calendar_events + send_email (NOT weather!)
   - "Look up recent emails and summarize" → list_emails (NOT calendar or weather)
   - NEVER call tools unrelated to the user's request

2. NEVER claim you have sent an email, added a calendar event, or performed any action until you have actually called the tool and received confirmation.

3. If a user message contains BOTH tool-based requests AND general knowledge questions:
   - Execute the required tools
   - After getting results, provide a complete response that includes:
     a) Summary of what the tools accomplished
     b) Answers to any general knowledge questions asked
   - Do NOT skip answering general questions just because you executed tools

CRITICAL RULE FOR MEMORY:
If the user shares information worth remembering, you MUST append a memory block at the VERY END of your response using EXACTLY this format (do not use Markdown, do not translate the word MEMORY):
MEMORY: [category] content

Categories: personal, preference, habit, work, general

EXAMPLE INTERACTION:
User: Tame Impala dinlemeyi çok seviyorum, şarkıları müthiş.
piSynapse: Kesinlikle harika bir tercih! Özellikle melodileri çok sürükleyici.
MEMORY: [preference] Kullanıcı Tame Impala dinlemeyi çok seviyor.

If no tool or memory is needed, respond normally.
"""

KNOWN_TOOLS = {
    "get_weather", "get_datetime",
    "create_calendar_event", "list_calendar_events", "delete_calendar_event",
    "list_emails", "read_email", "send_email", "search_emails",
}

# --- Nextcloud CalDAV (sync, runs in thread pool) ---

def _get_primary_calendar(client):
    principal = client.principal()
    calendars = principal.calendars()
    if not calendars:
        raise Exception("No calendar found on Nextcloud.")
    return calendars[0]

def _nc_create_event(client, summary, start_time_str, duration_minutes):
    calendar = _get_primary_calendar(client)
    start_dt = datetime.fromisoformat(start_time_str)
    end_dt = start_dt + timedelta(minutes=duration_minutes)

    ical_content = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//piSynapse//Private-Intelligence Assistant//EN",
        "BEGIN:VEVENT",
        f"SUMMARY:{summary}",
        f"DTSTART;VALUE=DATE-TIME:{start_dt.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;VALUE=DATE-TIME:{end_dt.strftime('%Y%m%dT%H%M%S')}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]) + "\r\n"

    calendar.add_event(ical_content)
    return f"✅ '{summary}' added to Nextcloud calendar."

def _nc_list_events(client, days_ahead):
    calendar = _get_primary_calendar(client)
    start = datetime.now()
    end = start + timedelta(days=days_ahead)

    events = calendar.date_search(start, end)
    if not events:
        return f"No events in the next {days_ahead} days."

    lines = []
    for event in events:
        ev_data = event.vobject_instance.vevent
        ev_summary = getattr(ev_data, "summary", getattr(ev_data, "description", "Untitled")).value
        ev_start = ev_data.dtstart.value
        start_str = ev_start.strftime("%Y-%m-%d %H:%M") if hasattr(ev_start, "strftime") else str(ev_start)
        lines.append(f"- {start_str} | {ev_summary}")

    return "📅 Upcoming Events:\n" + "\n".join(lines)

def _nc_delete_event(client, summary):
    calendar = _get_primary_calendar(client)
    events = calendar.date_search(
        datetime.now() - timedelta(days=30),
        datetime.now() + timedelta(days=90)
    )

    for event in events:
        ev_data = event.vobject_instance.vevent
        ev_summary = getattr(ev_data, "summary", "").value
        if summary.lower() in ev_summary.lower():
            event.delete()
            return f"✅ '{ev_summary}' deleted from Nextcloud calendar."

    return f"No event found matching '{summary}'."

# --- Gmail tools ---

async def _run_mail_tool(name: str, params: dict) -> str:
    mail_client = get_mail_client()
    if not mail_client:
        return "ERROR: Gmail connection failed. Check GMAIL_USER and GMAIL_APP_PASSWORD in your .env file."

    ACCOUNT_ID = 1
    MAILBOX_ID = "INBOX"

    try:
        if name == "list_emails":
            limit = params.get("limit", 10)
            messages = await mail_client.get_messages(ACCOUNT_ID, MAILBOX_ID, limit)
            if not messages:
                return "Your inbox is empty."

            lines = ["📬 Recent Emails:\n"]
            for i, msg in enumerate(messages, 1):
                lines.append(f"{i}. 📧 From: {msg.get('from', 'Unknown')}")
                lines.append(f"   📝 Subject: {msg.get('subject', '(no subject)')}")
                lines.append(f"   📅 Date: {msg.get('date', 'Unknown date')}")
                lines.append(f"   🆔 ID: {msg.get('id')}")
                body_preview = msg.get('body', '(no content)')
                if body_preview:
                    lines.append(f"   📄 Preview: {body_preview[:200]}...")
                lines.append("")
            return "\n".join(lines)

        elif name == "read_email":
            message_id = params.get("message_id")
            if not message_id:
                return "ERROR: message_id is required."
            message = await mail_client.get_message(ACCOUNT_ID, MAILBOX_ID, message_id)
            if not message:
                return "Email not found."
            return (
                f"📧 Email Details\n\n"
                f"From: {message.get('from', 'Unknown')}\n"
                f"Subject: {message.get('subject', '(no subject)')}\n"
                f"Date: {message.get('date', 'Unknown date')}\n\n"
                f"Body:\n{message.get('body', '(no content)')[:1500]}"
            )

        elif name == "send_email":
            to = params.get("to")
            subject = params.get("subject")
            body = params.get("body")
            if not all([to, subject, body]):
                return "ERROR: 'to', 'subject', and 'body' are all required."
            success = await mail_client.send_message(ACCOUNT_ID, to, subject, body)
            if success:
                return f"✅ Email sent!\nTo: {to}\nSubject: {subject}"
            return "❌ Failed to send email."

        elif name == "search_emails":
            query = params.get("query")
            limit = params.get("limit", 10)
            if not query:
                return "ERROR: 'query' is required."
            results = await mail_client.search_messages(ACCOUNT_ID, query, limit)
            if not results:
                return f"No results found for '{query}'."
            lines = [f"🔍 Search Results for '{query}':\n"]
            for i, msg in enumerate(results, 1):
                lines.append(f"{i}. 📧 {msg.get('from', 'Unknown')} — {msg.get('subject', '(no subject)')}")
                body_preview = msg.get('body', '')
                if body_preview:
                    lines.append(f"   📄 {body_preview[:150]}...")
                lines.append("")
            return "\n".join(lines)

    except Exception as e:
        return f"Gmail Error: {str(e)}"

    return "Tool not found."

# --- Tool runner ---

async def run_tool(name: str, params: dict) -> str:
    if name == "get_datetime":
        return f"Current time: {datetime.now().strftime('%d %B %Y, %A, %H:%M')}"

    if name == "get_weather":
        city = params.get("city", "London")
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                geo = await client.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": city, "format": "json", "limit": 1},
                    headers={"User-Agent": "piSynapse/1.0"}
                )
                geo_data = geo.json()
                if not geo_data:
                    return f"City not found: {city}"
                lat, lon = geo_data[0]["lat"], geo_data[0]["lon"]
                weather = await client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": lat, "longitude": lon,
                        "current": "temperature_2m,apparent_temperature,weathercode",
                        "timezone": "auto"
                    },
                    headers={"User-Agent": "piSynapse/1.0"}
                )
                w = weather.json()["current"]
                return f"{city}: {w['temperature_2m']}°C, feels like {w['apparent_temperature']}°C"
            except Exception as e:
                return f"Weather error: {str(e)}"

    if name in {"create_calendar_event", "list_calendar_events", "delete_calendar_event"}:
        client = get_nextcloud_client()
        if not client:
            return "ERROR: Nextcloud credentials missing or invalid."
        try:
            if name == "create_calendar_event":
                summary = params.get("summary", "New Event")
                start_str = params.get("start_time")
                duration = params.get("duration_minutes", 60)
                if not start_str:
                    return "ERROR: start_time is required."
                return await asyncio.to_thread(_nc_create_event, client, summary, start_str, duration)

            elif name == "list_calendar_events":
                days = params.get("days_ahead", 7)
                return await asyncio.to_thread(_nc_list_events, client, days)

            elif name == "delete_calendar_event":
                summary = params.get("summary")
                if not summary:
                    return "ERROR: Event title is required."
                return await asyncio.to_thread(_nc_delete_event, client, summary)

        except Exception as e:
            return f"Nextcloud CalDAV Error: {str(e)}"

    if name in {"list_emails", "read_email", "send_email", "search_emails"}:
        return await _run_mail_tool(name, params)

    return "Tool not found."

# --- Tool call parser ---
def parse_tool_call(text: str) -> tuple[str, dict] | None:
    tool_match = re.search(r"TOOL:\s*(\w+)", text)
    params_match = re.search(r"PARAMS:\s*(\{.*?\})", text, re.DOTALL)
    
    if tool_match:
        tool_name = tool_match.group(1).strip()
        tool_params = {}
        if params_match:
            try:
                tool_params = json.loads(params_match.group(1).strip())
            except json.JSONDecodeError:
                tool_params = {}
        if tool_name in KNOWN_TOOLS:
            return tool_name, tool_params
    return None

def parse_multiple_tools(text: str) -> list[tuple[str, dict]] | None:
    match = re.search(r"TOOLS:\s*(\[.*?\])", text, re.DOTALL)
    if match:
        try:
            tools_json = match.group(1).strip()
            tools_data = json.loads(tools_json)
            result = []
            for tool_obj in tools_data:
                tool_name = tool_obj.get("tool", "")
                tool_params = tool_obj.get("params", {})
                if tool_name in KNOWN_TOOLS:
                    result.append((tool_name, tool_params))
            return result if result else None
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
            
    elif text.strip().startswith("[") and text.strip().endswith("]"):
        try:
            tools_data = json.loads(text.strip())
            result = []
            for tool_obj in tools_data:
                tool_name = tool_obj.get("tool", "")
                tool_params = tool_obj.get("params", {})
                if tool_name in KNOWN_TOOLS:
                    result.append((tool_name, tool_params))
            return result if result else None
        except json.JSONDecodeError:
            pass
            
    return None

# --- Ollama bridge ---

async def chat_with_ollama(messages: list[dict], memories: list[dict] = []) -> str:
    memory_context = ""
    if memories:
        memory_context = "\n\nCore Memories:\n" + "\n".join(f"- {m['content']}" for m in memories)

    async with httpx.AsyncClient(timeout=300) as client:
        for iteration in range(5):
            payload = {
                "model": LLM_MODEL,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT + memory_context}] + messages,
                "stream": False,
                "options": {
                    "temperature": 0.3,
                    "top_p": 0.9,
                    "think": False,
                },
                "keep_alive": "24h",
            }

            try:
                resp = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
                resp.raise_for_status()
                reply = resp.json()["message"]["content"]
            except Exception as e:
                return f"Engine Error: Could not reach Ollama. Detail: {str(e)}"

            # Check for multiple tools
            multiple_tools = parse_multiple_tools(reply)
            if multiple_tools:
                tool_results = []
                for tool_name, tool_params in multiple_tools:
                    result = await run_tool(tool_name, tool_params)
                    tool_results.append(f"✓ {tool_name}: {result}")
                
                combined_result = "\n".join(tool_results)
                messages = messages + [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"Tool results:\n{combined_result}\n\nNow provide a complete response that includes: (1) summary of what tools accomplished, and (2) answer any other questions the user asked that don't require tools."},
                ]
                continue

            # Check for single tool
            single_tool = parse_tool_call(reply)
            if single_tool:
                tool_name, tool_params = single_tool
                tool_result = await run_tool(tool_name, tool_params)

                messages = messages + [
                    {"role": "assistant", "content": reply},
                    {"role": "user", "content": f"Tool result: {tool_result}\n\nNow provide a complete response that includes: (1) summary of what was done, and (2) answer any other questions the user asked that don't require tools."},
                ]
                continue

            # Check for MEMORY
            # memory_match = re.search(r"MEMORY:\s*\[(.*?)\]\s*(.*)", reply, re.DOTALL)
            # if memory_match:
            #     category = memory_match.group(1).strip()
            #     content = memory_match.group(2).strip()
            #     await save_memory(content=content, category=category)
            #     reply = reply[:memory_match.start()].strip()  # Remove memory part from final reply
            
            # No tools found, return the reply immediately (prevents hallucination loops)
            if iteration >= 4:
                logger.warning(f"Max iterations ({iteration + 1}) reached, returning reply to prevent hallucination loop")
            
            return reply

    return "I've reached the processing limit. Could you rephrase your request?"
