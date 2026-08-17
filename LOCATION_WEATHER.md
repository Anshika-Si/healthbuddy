# 📍 Location & weather-aware nudges

## What this adds

After onboarding, the app asks once: *"Weather-smart nudges?"* — with three
answers: **Use my location**, **Type my city instead**, or **Skip for now**.
Skipping breaks nothing; the user simply gets no weather nudges.

With a location set, nudges become weather-aware:

| Weather | Example nudge |
|---|---|
| Rain started | 🌦️ "The sky has started washing the city. Stay dry out there!" |
| Rain in the evening | ☕ "Rain outside. Chai inside. Sounds like a perfect plan." |
| 60%+ rain chance | ☔ "Umbrella in the bag = smug later." |
| Feels ≥ 38 °C | 🥵 "So hot even your ice cream is sweating. Hydrate before you melt." |
| Hot day forecast, morning | 🌡️ "Get your walk in now, before the sun means business." |
| Humid | 💦 "Humidity's doing the most today. Loose clothes, cold water." |
| ≤ 14 °C | 🧥 "Proper cold out there. Warm water is nicer than cold today." |
| Cool evening | 🚶 "Perfect walking weather. Your legs have been waiting." |
| Pleasant | 🌤️ "Genuinely nice out. Take the long way somewhere." |
| Thunderstorm | ⛈️ "Indoor day — hydrate anyway, the heat doesn't care." |

Home also shows a small line under the greeting: `⛅ 34°C · Partly cloudy ·
Kanpur · 20% rain today`.

## Nothing to set up, nothing to pay

Weather comes from **Open-Meteo**: free for non-commercial use, no API key,
no signup, 10,000 calls/day. It just works once deployed.

**One licence obligation:** Open-Meteo data is CC BY 4.0, so the attribution
"Weather by Open-Meteo" must stay visible where weather is shown. It's
already on the location screen — please don't remove it.

## Privacy choices (worth knowing, since this is location data)

- Coordinates are **rounded to 2 decimals (~1 km) before storage**. The
  server discards the precision; there's no exact position in the database.
- Weather lookups use an even coarser **~11 km grid**, so users in the same
  cell share one cached row and one API call (30-minute cache).
- Location is **never** shown to buddies or on the leaderboard — there's a
  test asserting it can't leak there.
- One tap to delete: Profile → Data & Permissions → Location → **Delete**.
- No location history is kept — only the current value, overwritten on update.

## Android: one extra permission for the APK

The website asks via the browser. For the native app, add to
`native/android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
```

Coarse (not fine) is deliberate — it matches what we actually store, and
Android shows the user a gentler permission prompt. Optionally add the
Capacitor Geolocation plugin (`npm install @capacitor/geolocation`); the code
uses it when present and falls back to the browser API when it isn't.

## Files

| File | What it does |
|---|---|
| `services/weather.py` | Open-Meteo client, grid cache, condition flags, city search |
| `services/weather_nudges.py` | The 12 weather nudge templates |
| `routes/features.py` | `/api/location` (GET/POST/DELETE), `/api/location/search`, `/api/weather` |
| `static/app.js` | Location consent screen, city picker, home weather line |
| `tests/test_weather.py` | 13 tests (privacy, caching, flags, nudge matching) |

**Your friend's notification engine was not modified.** `notify.py` gained
exactly 16 added lines and zero removed: one block appending the weather
templates, one merging the weather flags. The slot scheduler, snoozes, quiet
hours, push history and local-notification pipeline are untouched.
