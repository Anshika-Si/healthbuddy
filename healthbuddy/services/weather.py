"""Weather — turns a coarse location into nudge-ready conditions.

PROVIDER: Open-Meteo (open-meteo.com). Free for non-commercial use, no API
key, no signup, 10,000 calls/day. Data is CC BY 4.0, so the UI shows
"Weather by Open-Meteo" wherever weather is displayed — that attribution is
a licence condition, not decoration.

PRIVACY, by design:
  * Coordinates are rounded to 2 decimals (~1 km) before they're ever
    stored — enough to know it's raining on you, useless for following you.
  * The weather lookup uses an even coarser 1-decimal grid (~11 km), so
    users in the same cell share a single cached row and a single API call.
    (Neighbours either side of a cell boundary cost one call each — that's
    inherent to grid rounding, and harmless at this volume.)
  * Location is optional. Nothing breaks without it: every weather flag is
    simply absent, and the app behaves exactly as it did before.
  * Never shared with buddies or the leaderboard; deletable in one call.

CALL BUDGET: 30-minute TTL per cell → ~48 calls/day per populated cell,
however many users share it. A city spanning a few cells still costs a few
hundred calls/day against a 10,000/day free allowance.
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime

from ..db import execute, query

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_TTL_MINUTES = 30
UA = "HealthBuddy/1.0 (health nudge app; open-meteo client)"
ATTRIBUTION = "Weather by Open-Meteo"

#: WMO weather interpretation codes → (label, emoji, is_rain)
WMO = {
    0: ("Clear sky", "☀️", False), 1: ("Mainly clear", "🌤️", False),
    2: ("Partly cloudy", "⛅", False), 3: ("Overcast", "☁️", False),
    45: ("Fog", "🌫️", False), 48: ("Icy fog", "🌫️", False),
    51: ("Light drizzle", "🌦️", True), 53: ("Drizzle", "🌦️", True),
    55: ("Heavy drizzle", "🌧️", True), 56: ("Freezing drizzle", "🌧️", True),
    57: ("Freezing drizzle", "🌧️", True),
    61: ("Light rain", "🌦️", True), 63: ("Rain", "🌧️", True),
    65: ("Heavy rain", "🌧️", True), 66: ("Freezing rain", "🌧️", True),
    67: ("Freezing rain", "🌧️", True),
    71: ("Light snow", "🌨️", True), 73: ("Snow", "🌨️", True),
    75: ("Heavy snow", "❄️", True), 77: ("Snow grains", "🌨️", True),
    80: ("Showers", "🌦️", True), 81: ("Showers", "🌧️", True),
    82: ("Heavy showers", "⛈️", True),
    85: ("Snow showers", "🌨️", True), 86: ("Snow showers", "❄️", True),
    95: ("Thunderstorm", "⛈️", True), 96: ("Thunderstorm", "⛈️", True),
    99: ("Thunderstorm", "⛈️", True),
}


def round_coords(lat, lon):
    """Store no better than ~1 km. Raises ValueError on nonsense input."""
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Those coordinates aren't on Earth.")
    return round(lat, 2), round(lon, 2)


def _grid_key(lat, lon):
    """~11 km cell — the cache/lookup unit, shared across nearby users."""
    return f"{round(float(lat), 1)},{round(float(lon), 1)}"


def _http_json(url, params):
    full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read().decode())


# ------------------------------------------------------------------ fetching
def fetch(lat, lon, force=False):
    """Weather for a grid cell, from cache when it's fresh enough.
    Returns None if the provider can't be reached — callers must cope."""
    key = _grid_key(lat, lon)
    if not force:
        row = query("""SELECT payload FROM weather_cache
                       WHERE grid_key=? AND fetched_at >= datetime('now', ?)""",
                    (key, f"-{CACHE_TTL_MINUTES} minutes"), one=True)
        if row:
            try:
                return json.loads(row["payload"])
            except (TypeError, ValueError):
                pass
    try:
        data = _http_json(FORECAST_URL, {
            "latitude": key.split(",")[0], "longitude": key.split(",")[1],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "precipitation,weather_code,wind_speed_10m,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
                     "precipitation_probability_max",
            "timezone": "auto", "forecast_days": 1,
        })
    except Exception:
        # stale cache beats no weather at all
        row = query("SELECT payload FROM weather_cache WHERE grid_key=?", (key,), one=True)
        if row:
            try:
                return json.loads(row["payload"])
            except (TypeError, ValueError):
                return None
        return None

    snapshot = _shape(data)
    execute("""INSERT INTO weather_cache (grid_key, payload, fetched_at)
               VALUES (?,?,datetime('now'))
               ON CONFLICT(grid_key) DO UPDATE SET
                 payload=excluded.payload, fetched_at=datetime('now')""",
            (key, json.dumps(snapshot)))
    return snapshot


def _shape(data):
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = int(cur.get("weather_code") or 0)
    label, emoji, is_rain = WMO.get(code, ("Weather", "🌡️", False))
    first = lambda k: (daily.get(k) or [None])[0]
    return {
        "temp": cur.get("temperature_2m"),
        "feels_like": cur.get("apparent_temperature"),
        "humidity": cur.get("relative_humidity_2m"),
        "precip": cur.get("precipitation"),
        "wind": cur.get("wind_speed_10m"),
        "is_day": bool(cur.get("is_day", 1)),
        "code": code, "label": label, "emoji": emoji, "raining": is_rain,
        "temp_max": first("temperature_2m_max"),
        "temp_min": first("temperature_2m_min"),
        "rain_chance": first("precipitation_probability_max"),
        "attribution": ATTRIBUTION,
        "as_of": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ------------------------------------------------------------------ location
def set_location(user_id, lat=None, lon=None, label=None, source="device"):
    if lat is None or lon is None:
        raise ValueError("Latitude and longitude are required.")
    lat, lon = round_coords(lat, lon)
    execute("""UPDATE users SET loc_lat=?, loc_lon=?, loc_label=?, loc_source=?,
               loc_updated_at=datetime('now') WHERE id=?""",
            (lat, lon, (label or "")[:80] or None, source, user_id))
    return {"lat": lat, "lon": lon, "label": label, "source": source}


def clear_location(user_id):
    execute("""UPDATE users SET loc_lat=NULL, loc_lon=NULL, loc_label=NULL,
               loc_source=NULL, loc_updated_at=NULL WHERE id=?""", (user_id,))


def get_location(user_id):
    u = query("""SELECT loc_lat, loc_lon, loc_label, loc_source, loc_updated_at
                 FROM users WHERE id=?""", (user_id,), one=True)
    if not u or u["loc_lat"] is None:
        return None
    return {"lat": u["loc_lat"], "lon": u["loc_lon"], "label": u["loc_label"],
            "source": u["loc_source"], "updated_at": u["loc_updated_at"]}


def search_city(name):
    """Manual fallback: type a city, pick from matches. Works when a user
    declines the OS permission but still wants weather nudges."""
    name = (name or "").strip()
    if len(name) < 2:
        return []
    try:
        data = _http_json(GEOCODE_URL, {"name": name, "count": 5, "language": "en",
                                        "format": "json"})
    except Exception:
        return []
    out = []
    for r in data.get("results") or []:
        bits = [r.get("name"), r.get("admin1"), r.get("country")]
        out.append({"label": ", ".join(b for b in bits if b),
                    "lat": round(r["latitude"], 2), "lon": round(r["longitude"], 2)})
    return out


# ------------------------------------------------------------------ for nudges
def for_user(user_id):
    """{location, weather, conditions} — or None if no location is set."""
    loc = get_location(user_id)
    if not loc:
        return None
    w = fetch(loc["lat"], loc["lon"])
    if not w:
        return {"location": loc, "weather": None, "conditions": {}}
    return {"location": loc, "weather": w, "conditions": conditions(w)}


def conditions(w, hour=None):
    """Boolean flags the notification layer can match on. Thresholds are
    tuned for Indian conditions (35 °C is a normal summer day, not an
    emergency) and every one is derived, never guessed."""
    hour = datetime.now().hour if hour is None else hour
    feels = w.get("feels_like") if w.get("feels_like") is not None else w.get("temp")
    temp = w.get("temp")
    hi = w.get("temp_max")
    rain_chance = w.get("rain_chance") or 0
    humidity = w.get("humidity") or 0
    return {
        "raining_now": bool(w.get("raining")) or (w.get("precip") or 0) > 0.1,
        "rain_likely": rain_chance >= 60 and not w.get("raining"),
        "very_hot": feels is not None and feels >= 38,
        "hot": feels is not None and 33 <= feels < 38,
        "humid": humidity >= 75 and (temp or 0) >= 28,
        "cold": temp is not None and temp <= 14,
        "chilly": temp is not None and 14 < temp <= 20,
        "pleasant": (temp is not None and 20 < temp <= 30
                     and rain_chance < 40 and not w.get("raining")),
        "hot_day_ahead": hi is not None and hi >= 38 and hour < 12,
        "storm": w.get("code") in (95, 96, 99),
    }
