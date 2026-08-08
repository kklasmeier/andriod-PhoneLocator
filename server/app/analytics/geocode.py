"""Reverse geocoding via OpenStreetMap Nominatim."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app import config

POI_CLASSES = frozenset({"amenity", "shop", "tourism", "leisure", "office", "building", "craft"})

_last_request_at = 0.0


def _rate_limit() -> None:
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = config.NOMINATIM_MIN_INTERVAL_SEC - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def format_geocode_label(payload: dict[str, Any]) -> str:
    """POI name when available, otherwise 'Road, City'."""
    name = (payload.get("name") or "").strip()
    feature_class = payload.get("class") or ""
    if name and feature_class in POI_CLASSES:
        return name

    address = payload.get("address") or {}
    road = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("residential")
        or address.get("neighbourhood")
    )
    city = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("municipality")
        or address.get("county")
    )

    if road and city:
        return f"{road}, {city}"
    if road:
        return str(road)
    if city:
        return str(city)
    if name:
        return name

    display = (payload.get("display_name") or "").strip()
    if display:
        return display.split(",")[0].strip()
    return "Unknown location"


def cache_key_for(lat: float, lon: float) -> str:
    return f"{lat:.5f},{lon:.5f}"


def reverse_geocode(lat: float, lon: float) -> tuple[str, dict[str, Any]]:
    """Call Nominatim reverse geocode. Respects 1 req/sec rate limit."""
    params = urllib.parse.urlencode(
        {
            "lat": f"{lat:.6f}",
            "lon": f"{lon:.6f}",
            "format": "json",
            "addressdetails": "1",
            "zoom": "18",
        }
    )
    url = f"{config.NOMINATIM_BASE_URL}/reverse?{params}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": config.NOMINATIM_USER_AGENT, "Accept": "application/json"},
    )

    _rate_limit()
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Nominatim HTTP {err.code}: {body[:200]}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Nominatim unreachable: {err.reason}") from err

    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))

    return format_geocode_label(payload), payload
