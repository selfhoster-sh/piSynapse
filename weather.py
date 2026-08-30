"""piSynapse Weather
Open-Meteo weather with Nominatim geocoding.
"""

import logging
from collections import OrderedDict

import httpx

import config

logger = logging.getLogger("piSynapse")

# Bounded LRU geocoding cache: Nominatim rate-limits (1 req/s) so we reuse
# results aggressively, but cap memory so long-running instances never grow
# the dict without bound.
_GEO_CACHE_MAX = 100
_geo_cache: "OrderedDict[str, tuple[str, str]]" = OrderedDict()
_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=config.WEATHER_TIMEOUT)
    return _client


def _geo_lookup(city: str) -> tuple[str, str] | None:
    """Return cached lat/lon, or None to force a fresh geocode."""
    if city not in _geo_cache:
        return None
    _geo_cache.move_to_end(city)  # mark most-recently used
    return _geo_cache[city]


def _cache_city(city: str, lat: str, lon: str) -> None:
    _geo_cache[city] = (lat, lon)
    _geo_cache.move_to_end(city)
    while len(_geo_cache) > _GEO_CACHE_MAX:
        _geo_cache.popitem(last=False)  # evict least-recently used


def _wmo_condition(code: int | None) -> str:
    """Map a WMO weather code to a short Turkish condition label."""
    base = {
        0: "Açık", 1: "Az bulutlu", 2: "Parçalı bulutlu", 3: "Kapalı",
        45: "Sisli", 48: "Kırağılı sis",
        51: "Hafif çisenti", 53: "Çisenti", 55: "Yoğun çisenti",
        56: "Hafif donan çisenti", 57: "Donan çisenti",
        61: "Hafif yağmur", 63: "Yağmurlu", 65: "Yoğun yağmur",
        66: "Hafif donan yağmur", 67: "Donan yağmur",
        71: "Hafif kar", 73: "Karlı", 75: "Yoğun kar", 77: "Kar tanesi",
        80: "Hafif sağanak", 81: "Sağanak", 82: "Şiddetli sağanak",
        85: "Kar sağanağı", 86: "Yoğun kar sağanağı",
    }
    if code in base:
        return base[code]
    if code is not None and 95 <= code <= 99:
        return "Gök gürültülü" + (" dolu" if code >= 96 else "")
    return "Bilinmiyor"


async def get_weather(city: str = "") -> str:
    city = city or config.DEFAULT_CITY or "London"
    client = _get_client()
    try:
        coords = _geo_lookup(city)
        if coords is None:
            geo = await client.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": city, "format": "json", "limit": 1},
                headers={"User-Agent": "piSynapse/1.0"},
            )
            gd = geo.json()
            if not gd:
                return f"ERROR: City not found: {city}"
            coords = (gd[0]["lat"], gd[0]["lon"])
            _cache_city(city, *coords)
        lat, lon = coords
        w = await client.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature,weather_code",
                "timezone": "auto",
            },
            headers={"User-Agent": "piSynapse/1.0"},
        )
        c = w.json()["current"]
        cond = _wmo_condition(c.get("weather_code"))
        return f"{city}: {c['temperature_2m']}°C, {cond}, feels like {c['apparent_temperature']}°C"
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return "ERROR: unable to fetch weather data"
