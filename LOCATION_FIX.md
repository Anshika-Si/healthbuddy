# 📍 Why location failed, and what fixes it

## The actual cause

Your screenshot said **"Location permission declined"** while your phone's
location was switched on. Both things were true, because they're different
permissions:

- **Phone location ON** = the device's GPS radio is enabled.
- **App location permission** = *this app* is allowed to use it.

Your APK never declared the location permission, so Android refused the
request **instantly, without ever showing you a prompt**. A web page inside
an app shell can't ask for an Android permission on its own — which is why
"Use my exact location" appeared to fail while everything else worked.

## How Google Maps does it (and now, so do you)

Maps uses Android's **fused location provider** — GPS + wifi + cell towers
combined — behind a runtime permission prompt. Two things make that possible,
and both are now in your build:

1. **`ACCESS_FINE_LOCATION` + `ACCESS_COARSE_LOCATION` declared in the
   manifest.** Added automatically by the build workflow, and the build now
   **fails loudly** if they're ever missing.
2. **The Capacitor Geolocation plugin installed** (`@capacitor/geolocation`),
   which is what can actually trigger the permission dialog and read the
   fused provider. The app now calls `checkPermissions()` →
   `requestPermissions()` → `getCurrentPosition()`, in that order.

## Other fixes in this build

**Indoor GPS timeouts.** A precise satellite fix often fails indoors. The app
now retries with a network-based fix (accurate to a few hundred metres —
far more than enough for weather) before giving up.

**Dead-end error replaced with a route out.** If permission really is
blocked, you now get a dialog naming the exact screen to fix it
(Settings → Apps → HealthBuddy → Permissions → Location), plus **Try again**
and **Type my city** buttons.

**The confusing city list.** "Nepal, Nepal" vs "Nepal, Punjab, Pakistan" was
Open-Meteo returning every place sharing a name, unranked. Now results are:
- **sorted by population**, so the intended city is first;
- **de-duplicated**;
- shown with a **flag, region, country and population**
  (🇳🇵 **Kathmandu** · Bagmati, Nepal · 1.4M people).

## What you need to do

1. Upload the new zip to GitHub.
2. **Rebuild the APK** (Actions → Build Android APK → Run workflow). This is
   the essential step — the permission lives in the APK, so the old build
   can never work no matter how many times you tap Allow.
3. Install the new APK (uninstall the old one first).
4. Tap **Use my location** → Android will now show a real permission dialog
   → choose *While using the app* → your actual city appears.

On the **website** version, permission comes from the browser instead: tap
the 🔒 next to the address bar → Site settings → Location → Allow.

## Files changed

| File | Change |
|---|---|
| `.github/workflows/build-apk.yml` | Declares location permissions, installs the Geolocation plugin, fails the build if missing |
| `static/app.js` | Native permission flow, coarse-fix retry, "blocked" help dialog, richer city rows |
| `services/weather.py` | City search ranked by population, deduped, flag + population labels |
| `tests/test_weather.py` | 3 new tests for ranking, dedup, country hint |
