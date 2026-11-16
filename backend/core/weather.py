"""Today's weather for the top bar. The browser may only talk to this server (the production
policy is connect-src 'self'), so the server asks Open-Meteo, a free service that needs no key.
The coordinates are rounded to about 10 km and the answer is cached for a quarter of an hour, so
the service never learns exactly where anyone is, and an open page does not call it every minute."""

import logging

import requests
from django.core.cache import cache

log = logging.getLogger(__name__)
URL = "https://api.open-meteo.com/v1/forecast"
CACHE_SECONDS = 15 * 60


def current(lat: float, lon: float) -> dict | None:
    """{"temperature_c", "code", "place"} for the spot, or None if the service is unavailable.
    `code` is the WMO weather code; `place` is the city part of the area's time zone name."""
    lat, lon = round(lat, 1), round(lon, 1)
    key = f"weather:{lat}:{lon}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    try:
        resp = requests.get(
            URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,weather_code",
                "timezone": "auto",
            },
            timeout=5,
        )
        data = resp.json() if resp.status_code == 200 else {}
        now = data["current"]
        out = {
            "temperature_c": round(float(now["temperature_2m"])),
            "code": int(now["weather_code"]),
            "place": str(data.get("timezone", "")).rsplit("/", 1)[-1].replace("_", " "),
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        log.warning("weather lookup failed")
        return None
    cache.set(key, out, CACHE_SECONDS)
    return out
