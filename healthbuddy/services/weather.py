"""Weather-aware notification context — powered by Open-Meteo.

Open-Meteo is free, needs no API key, and has no meaningful call cap for a
pilot this size. Given a user's last known lat/lon (see user_location table
and POST /api/location), returns a small dict of flags that notify.py folds
into its normal _context() output: is_hot, is_rainy, is_cold, is_high_uv.

Network calls are cached in memory per rounded-coordinate for CACHE_MINUTES
so many users in the same city share one upstream call, and any failure
(no internet, Open-Meteo down, bad coords) degrades to weather_ok=False
rather than raising — a weather outage should never break nudges overall.
"""
import json
import time
import urllib.request

from ..db import execute, query

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CACHE_MINUTES = 30
_cache = {}  # (lat_rounded, lon_rounded) -> (fetched_at_epoch, context_dict)

# Tune these to taste.
HOT_THRESHOLD_C = 32
COLD_THRESHOLD_C = 14
HUMID_THRESHOLD_PCT = 70
HIGH_UV_THRESHOLD = 7

# WMO weather codes meaning "rain or storm happening right now".
# https://open-meteo.com/en/docs -> "WMO Weather interpretation codes"
RAIN_CODES = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}


def save_location(user_id, lat, lon):
    execute(
        "INSERT INTO user_location (user_id, lat, lon, updated_at) "
        "VALUES (?,?,?,datetime('now')) "
        "ON CONFLICT(user_id) DO UPDATE SET "
        "lat=excluded.lat, lon=excluded.lon, updated_at=excluded.updated_at",
        (user_id, lat, lon),
    )


def _round_coord(v):
    # ~1.1km precision at the equator — plenty for weather, coarse enough
    # not to pin down someone's exact building.
    return round(float(v), 2)


def get_weather_context(lat, lon):
    """Returns a dict of flags/values, or {'weather_ok': False} on any
    failure or missing coordinates. Never raises."""
    if lat is None or lon is None:
        return {"weather_ok": False}

    key = (_round_coord(lat), _round_coord(lon))
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_MINUTES * 60:
        return cached[1]

    try:
        url = (
            f"{OPEN_METEO_URL}?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,weather_code,relative_humidity_2m,uv_index"
            "&timezone=auto"
        )
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = json.loads(resp.read())

        current = payload.get("current", {})
        temp_c = current.get("temperature_2m")
        code = current.get("weather_code")
        humidity = current.get("relative_humidity_2m")
        uv = current.get("uv_index")

        ctx = {
            "weather_ok": True,
            "temp_c": temp_c,
            "weather_code": code,
            "is_hot": temp_c is not None and temp_c >= HOT_THRESHOLD_C,
            "is_cold": temp_c is not None and temp_c <= COLD_THRESHOLD_C,
            "is_rainy": code in RAIN_CODES,
            "is_humid": humidity is not None and humidity >= HUMID_THRESHOLD_PCT,
            "is_high_uv": uv is not None and uv >= HIGH_UV_THRESHOLD,
        }
    except Exception as e:  # network hiccup, Open-Meteo down, bad coords, etc.
        ctx = {"weather_ok": False, "error": str(e)}

    _cache[key] = (now, ctx)
    return ctx


def get_user_weather_context(user_id):
    """Looks up the user's last saved location, then fetches weather for it.
    Returns {'weather_ok': False} (no network call at all) if the user has
    never shared a location — the normal, expected case for most users and
    for every account in the test suite."""
    row = query("SELECT lat, lon FROM user_location WHERE user_id=?", (user_id,), one=True)
    if not row:
        return {"weather_ok": False}
    return get_weather_context(row["lat"], row["lon"])
