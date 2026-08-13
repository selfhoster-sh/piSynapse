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
        return {"error": "DEFAULT_CITY is not set", "city": "", "summary": ""}
    try:
        from weather import get_weather
        summary = await get_weather(city)
        return {"city": city, "summary": summary}
    except Exception as e:
        logger.error(f"Weather widget error: {e}")
        return {"error": "Widget error", "city": city, "summary": ""}


@router.get("/widget/calendar")
async def widget_calendar():
    try:
        from calendar_ops import list_events_today
        events = await asyncio.to_thread(list_events_today)
        return {"events": events}
    except Exception as e:
        logger.warning(f"Calendar widget error: {e}")
        return {"events": []}
