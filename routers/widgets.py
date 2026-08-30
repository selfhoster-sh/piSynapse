"""piSynapse Widget Endpoints
Sidebar weather and calendar widgets.
"""

import asyncio
import logging

from fastapi import APIRouter

import config

logger = logging.getLogger("piSynapse")

router = APIRouter(tags=["widgets"])


@router.get("/widget/weather")
async def widget_weather():
    city = config.DEFAULT_CITY
    if not city:
        return {"ok": False, "error": "DEFAULT_CITY is not set", "city": "", "summary": ""}
    try:
        from weather import _weather_data
        data = await _weather_data(city)
        if data is None:
            return {"ok": False, "error": "City not found or forecast unavailable",
                    "city": city, "summary": ""}
        summary = (f"{data['city']}: {data['temp_c']}°C, {data['condition']}, "
                   f"feels like {data['feels_c']}°C"
                   if data["feels_c"] is not None
                   else f"{data['city']}: {data['temp_c']}°C, {data['condition']}")
        return {"ok": True, "city": data["city"], "temp_c": data["temp_c"],
                "feels_c": data["feels_c"], "condition": data["condition"],
                "wmo_code": data["wmo_code"], "kind": data["kind"], "summary": summary}
    except Exception as e:
        logger.error(f"Weather widget error: {e}")
        return {"ok": False, "error": "Weather service unavailable", "city": city, "summary": ""}


@router.get("/widget/calendar")
async def widget_calendar():
    try:
        from calendar_ops import list_events_today
        events = await asyncio.to_thread(list_events_today)
        return {"ok": True, "events": events}
    except Exception as e:
        logger.warning(f"Calendar widget error: {e}")
        return {"ok": False, "error": "Calendar unavailable", "events": []}
