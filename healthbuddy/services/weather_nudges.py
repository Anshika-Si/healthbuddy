"""Weather-aware nudges — kept in its own module on purpose.

services/notify.py (the existing notification engine) is untouched apart
from two additive hooks: it merges the flags from `flags()` into its
condition dict and appends `TEMPLATES` to its own list. Nothing existing is
modified, so the slot scheduler, snoozes, quiet hours, push history and the
local-notification pipeline all keep working exactly as before.

Every template here fires only when the user has shared a location AND the
weather actually matches — no location means no weather flags, which means
none of these can fire.
"""
from . import weather as weather_svc

# (id, condition, hour_range, weekend_only, emoji, title, body, priority)
# Same tuple shape notify.py already uses, so it slots straight in.
TEMPLATES = [
    # --- rain ---
    ("w_rain_now", "raining_now", (7, 21), False, "🌦️", "Rain alert",
     "The sky has started washing the city. Stay dry out there!", 6),
    ("w_rain_chai", "raining_now", (16, 21), False, "☕", "Weather report",
     "Rain outside. Chai inside. Sounds like a perfect plan.", 5),
    ("w_rain_indoor_move", "raining_now", (10, 19), False, "🏠", "Indoor plan",
     "Rain's cancelled the walk, not the movement. Ten minutes of stretching counts.", 4),
    ("w_rain_likely", "rain_likely", (7, 17), False, "☔", "Pack an umbrella",
     "Good chance of rain today. Umbrella in the bag = smug later.", 5),
    ("w_storm", "storm", None, False, "⛈️", "Storm outside",
     "Thunderstorm out there. Indoor day — hydrate anyway, the heat doesn't care.", 7),
    # --- heat ---
    ("w_very_hot", "very_hot", (10, 18), False, "🥵", "It's brutal out",
     "It's so hot today even your ice cream is sweating. Hydrate before you also start melting.", 7),
    ("w_hot_hydrate", "hot", (11, 18), False, "💧", "Warm one today",
     "Warm out there — an extra glass of water now saves you a headache at 4pm.", 5),
    ("w_hot_morning_plan", "hot_day_ahead", (6, 11), False, "🌡️", "Beat the heat",
     "Today's going to be a hot one. Get your walk in now, before the sun means business.", 5),
    ("w_humid", "humid", (10, 19), False, "💦", "Sticky weather",
     "Humidity's doing the most today. Loose clothes, cold water, zero shame in moving slower.", 4),
    # --- cold / pleasant ---
    ("w_cold", "cold", (6, 11), False, "🧥", "Cold morning",
     "Proper cold out there. Layer up — and warm water is nicer than cold water today.", 5),
    ("w_chilly_walk", "chilly", (16, 20), False, "🚶", "Perfect walking weather",
     "Cool enough for a comfortable walk. Your legs have been waiting for weather like this.", 4),
    ("w_pleasant", "pleasant", (7, 19), False, "🌤️", "Weather's on your side",
     "Genuinely nice out. This is a sign to take the long way somewhere.", 3),
]


def flags(user_id, hour=None):
    """Weather condition flags for this user, or {} when no location/weather.
    Also returns `_weather` so a caller can show the temperature."""
    bundle = weather_svc.for_user(user_id)
    if not bundle or not bundle.get("weather"):
        return {}
    conds = weather_svc.conditions(bundle["weather"], hour=hour)
    conds["_weather"] = bundle["weather"]
    conds["_location_label"] = (bundle["location"] or {}).get("label")
    return conds
