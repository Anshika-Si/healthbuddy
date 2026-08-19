# What's new — body basics, better location, flash cards

## 1. Body basics (height, weight, date of birth → BMI)

A new **optional** last step in onboarding asks for date of birth (calendar
picker), height and weight. Everything can be skipped or left blank, and
edited later in Profile → 📏 Body basics.

BMI is calculated and shown with deliberately neutral wording:

> BMI **21.3** — in the typical range.
> *BMI is a rough population measure — it can't see muscle, build or bone.
> It's here for context, not a target.*

**A product decision worth keeping:** there are no weight-loss nudges, no
calorie targets, no "ideal weight", and no streaks around weighing yourself.
The band labels avoid clinical words ("obese", "overweight") entirely — a
habit app that nags people about weight is how you nudge someone into
disordered eating. There's a test that fails if that language creeps back in.

Age is used only for gentler copy; it never gates anything.

## 2. Location — now actually accurate

**What was wrong:** the city-name search returns every place sharing a name
(Kanpur in India *and* in Pakistan), so a mis-tap set the wrong location.

**What changed:**

- **GPS is now the primary path**, with `enableHighAccuracy: true` and a
  fresh fix (a stale cached fix was part of the wrong-city problem).
- **Coordinates are reverse-geocoded on the device** into a real place name,
  using BigDataCloud's free client-side API (no key; their fair-use policy
  requires the call to come from the device, so it runs in the app, not on
  our server). You now see "📍 Kanpur — weather nudges are on" from your
  actual position, with no list to pick from.
- **New users are asked during sign-up**, right after onboarding.
- **Existing users get one gentle prompt** the next time they open Home
  (asked once per device; "Not now" is remembered).
- The manual city list is still there as a fallback, now with a "📍 Use my
  exact location instead" button and a warning that several places share a
  name — plus state and country on every result.
- Profile → Data & Permissions still shows Location with a Delete button.

## 3. Flash cards — one small question every few days

When you open the app, at most one card appears every **3 days** (and never
in the first day after signing up):

> 🩺 **Any ongoing health conditions we should keep in mind?**
> *So nudges stay sensible for you — never to diagnose anything.*
> None · Asthma / breathing · Diabetes · Thyroid · PCOS / hormonal ·
> Blood pressure · Something else · **Prefer not to say**

Ten questions in the bank: health conditions, regular medicines, allergies,
diet, water bottle habit, bedtime, movement you enjoy, stress triggers,
meal skipping, phone-in-bed. Light questions come first; sensitive ones are
never the first thing a new user sees.

**Privacy rules, enforced in code:**
- Always skippable — "Prefer not to say" is on every card, and a skip is
  recorded so it isn't asked again for a long time.
- Health answers are private: never shown to buddies, never on the
  leaderboard (there's a test), never used for advertising.
- Delete everything in one tap: Profile → 💬 What you've told us → Delete.
- The personalization layer only receives *presence* flags — e.g.
  `has_condition: true` and an allergy to avoid in food nudges — never the
  condition itself, and nothing here diagnoses or advises.

Answering earns the same small XP as a habit log; skipping earns none but
costs nothing.

## Android note

For GPS in the APK, add to `native/android/app/src/main/AndroidManifest.xml`:

```xml
<uses-permission android:name="android.permission.ACCESS_COARSE_LOCATION" />
<uses-permission android:name="android.permission.ACCESS_FINE_LOCATION" />
```

Fine location is requested so the *fix* is accurate; we still round it to
~1 km before storing. Optionally `npm install @capacitor/geolocation` — the
code uses the plugin when present and the browser API otherwise.

## Tests

92 total, passing on both SQLite and the Postgres path, plus the headless
screen check. New coverage: BMI maths and non-judgmental language, DOB
validation, optional/clearable fields, flash card cadence and cooldown,
skip behaviour, answer privacy and deletion, and presence-only hints.
