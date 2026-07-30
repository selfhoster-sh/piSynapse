"""
piSynapse Weather
Open-Meteo weather with Nominatim geocoding.
"""

import httpx
import logging
from config import DEFAULT_CITY, WEATHER_TIMEOUT

logger = logging.getLogger("piSynapse")

_geo_cache: dict[str, tuple[str, str]] = {}
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=WEATHER_TIMEOUT)
    return _client


async def get_weather(city: str = "") -> str:
    city = city or DEFAULT_CITY or "London"
    client = _get_client()
    try:
        if city not in _geo_cache:
            geo = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "piSynapse/1.0"},
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
                "timezone": "auto",
            },
            headers={"User-Agent": "piSynapse/1.0"},
        )
        c = w.json()["current"]
        return f"{city}: {c['temperature_2m']}°C, feels like {c['apparent_temperature']}°C"
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return "Weather error: unable to fetch weather data"
