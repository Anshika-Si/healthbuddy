"""Tests for location + weather-aware nudges.

The weather provider is stubbed, so these run offline and deterministically.
"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healthbuddy import create_app
from healthbuddy.services import weather as weather_svc
from healthbuddy.services import weather_nudges, notify

KANPUR = {"lat": 26.4499, "lon": 80.3319}


def fake_api(temp=34.0, feels=39.0, code=2, rain_chance=10, humidity=60,
             precip=0.0, tmax=38.0, tmin=27.0):
    """Shape matches Open-Meteo's documented response."""
    return {
        "current": {"temperature_2m": temp, "apparent_temperature": feels,
                    "relative_humidity_2m": humidity, "precipitation": precip,
                    "weather_code": code, "wind_speed_10m": 9.0, "is_day": 1},
        "daily": {"weather_code": [code], "temperature_2m_max": [tmax],
                  "temperature_2m_min": [tmin],
                  "precipitation_probability_max": [rain_chance]},
    }


class LocationTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"DATABASE": self.db_path, "TESTING": True, "SECRET_KEY": "t"})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def auth(self, email="loc@example.com"):
        r = self.client.post("/api/auth/register",
                             json={"email": email, "name": "Loc", "password": "password123"})
        tok = self.client.post("/api/auth/register/verify",
                               json={"email": email, "code": r.get_json()["dev_code"]}
                               ).get_json()["token"]
        h = {"Authorization": "Bearer " + tok}
        self.client.post("/api/onboarding", headers=h,
                         json={"occupation": "student", "gender": "female",
                               "activity_level": "moderate", "health_goals": ["general"]})
        return h

    # ---------------- privacy ----------------
    def test_coordinates_are_stored_coarse(self):
        """Precision is deliberately destroyed before storage (~1 km)."""
        h = self.auth()
        res = self.client.post("/api/location", headers=h,
                               json={"lat": 26.449923456, "lon": 80.331987654})
        self.assertEqual(res.status_code, 200)
        loc = res.get_json()["location"]
        self.assertEqual((loc["lat"], loc["lon"]), (26.45, 80.33))
        stored = self.client.get("/api/location", headers=h).get_json()["location"]
        self.assertEqual(stored["lat"], 26.45)
        self.assertNotIn("26.4499", json.dumps(stored))

    def test_bad_coordinates_rejected(self):
        h = self.auth()
        for bad in ({"lat": 999, "lon": 0}, {"lat": "abc", "lon": 12}, {}):
            self.assertEqual(self.client.post("/api/location", headers=h, json=bad).status_code, 400)

    def test_location_is_deletable(self):
        h = self.auth()
        self.client.post("/api/location", headers=h, json=KANPUR)
        self.assertIsNotNone(self.client.get("/api/location", headers=h).get_json()["location"])
        self.client.delete("/api/location", headers=h)
        self.assertIsNone(self.client.get("/api/location", headers=h).get_json()["location"])

    def test_app_works_with_no_location(self):
        """The whole point: skipping the ask must break nothing."""
        h = self.auth()
        self.assertEqual(self.client.get("/api/dashboard", headers=h).status_code, 200)
        w = self.client.get("/api/weather", headers=h).get_json()
        self.assertIsNone(w["weather"])
        with self.app.app_context():
            self.assertEqual(weather_nudges.flags(1), {})     # no weather flags at all

    def test_location_never_appears_on_the_leaderboard(self):
        h = self.auth()
        self.client.post("/api/location", headers=h, json=KANPUR)
        board = self.client.get("/api/leaderboard?scope=global", headers=h).get_json()
        blob = json.dumps(board)
        for leak in ("loc_lat", "loc_lon", "26.45", "80.33", "Kanpur"):
            self.assertNotIn(leak, blob)

    # ---------------- caching ----------------
    def test_weather_is_cached_per_grid_cell(self):
        h = self.auth()
        self.client.post("/api/location", headers=h, json=KANPUR)
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json",
                                   return_value=fake_api()) as m:
                first = weather_svc.for_user(1)
                second = weather_svc.for_user(1)          # served from cache
                self.assertEqual(m.call_count, 1)
        self.assertEqual(first["weather"]["temp"], 34.0)
        self.assertEqual(second["weather"]["label"], "Partly cloudy")

    def test_users_in_the_same_cell_share_one_api_call(self):
        """Users inside the same ~11 km cell cost ONE call between them.
        (Users either side of a cell boundary still cost one call each —
        that's inherent to grid rounding and fine for the call budget.)"""
        h1 = self.auth("a@example.com")
        h2 = self.auth("b@example.com")
        self.client.post("/api/location", headers=h1, json={"lat": 26.45, "lon": 80.33})
        self.client.post("/api/location", headers=h2, json={"lat": 26.44, "lon": 80.31})
        with self.app.app_context():
            self.assertEqual(weather_svc._grid_key(26.45, 80.33),
                             weather_svc._grid_key(26.44, 80.31))
            with mock.patch.object(weather_svc, "_http_json", return_value=fake_api()) as m:
                weather_svc.for_user(1)
                weather_svc.for_user(2)
                self.assertEqual(m.call_count, 1)

    def test_provider_failure_is_survivable(self):
        h = self.auth()
        self.client.post("/api/location", headers=h, json=KANPUR)
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json", side_effect=OSError("no net")):
                bundle = weather_svc.for_user(1)
        self.assertIsNone(bundle["weather"])          # honest absence, not a crash
        self.assertEqual(self.client.get("/api/weather", headers=h).status_code, 200)

    # ---------------- condition flags ----------------
    def test_condition_flags_match_the_weather(self):
        cases = [
            (fake_api(temp=41, feels=45, code=0), "very_hot"),
            (fake_api(temp=35, feels=34, code=0), "hot"),
            (fake_api(temp=24, feels=24, code=63, precip=1.2), "raining_now"),
            (fake_api(temp=30, feels=32, code=1, rain_chance=80), "rain_likely"),
            (fake_api(temp=10, feels=8, code=3), "cold"),
            (fake_api(temp=26, feels=26, code=1, rain_chance=10), "pleasant"),
            (fake_api(temp=29, feels=34, code=2, humidity=85), "humid"),
            (fake_api(temp=27, feels=28, code=95), "storm"),
        ]
        for payload, expected in cases:
            snap = weather_svc._shape(payload)
            conds = weather_svc.conditions(snap, hour=14)
            self.assertTrue(conds[expected], f"{expected} should be true for {snap['label']}")

    def test_weather_templates_fire_only_with_matching_weather(self):
        h = self.auth()
        self.client.post("/api/location", headers=h, json=KANPUR)
        with self.app.app_context():
            # rain → the rain alert is available
            with mock.patch.object(weather_svc, "_http_json",
                                   return_value=fake_api(temp=25, feels=25, code=63, precip=0.8)):
                picks = notify.compose(1, now=datetime(2026, 8, 17, 15, 0))
            ids = [p["id"] for p in picks]
            self.assertTrue(any(i.startswith("w_rain") for i in ids), ids)

            # scorching, no rain → heat nudge instead, never the rain one
            weather_svc.execute("DELETE FROM weather_cache")
            with mock.patch.object(weather_svc, "_http_json",
                                   return_value=fake_api(temp=41, feels=45, code=0)):
                picks = notify.compose(1, now=datetime(2026, 8, 17, 14, 0))
            ids = [p["id"] for p in picks]
            self.assertIn("w_very_hot", ids)
            self.assertFalse(any(i.startswith("w_rain") for i in ids), ids)

    def test_existing_notifications_still_work_without_location(self):
        """The friend's engine must behave identically for users with no location."""
        h = self.auth()
        with self.app.app_context():
            picks = notify.compose(1, now=datetime(2026, 8, 17, 15, 0))
            self.assertTrue(picks)                          # still produces nudges
            self.assertFalse(any(p["id"].startswith("w_") for p in picks))

    def test_quiet_hours_still_respected_for_weather_nudges(self):
        h = self.auth()
        self.client.post("/api/location", headers=h, json=KANPUR)
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json",
                                   return_value=fake_api(temp=41, feels=45, code=0)):
                self.assertEqual(notify.compose(1, now=datetime(2026, 8, 17, 2, 0)), [])

    def test_city_search_shapes_results(self):
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json", return_value={"results": [
                    {"name": "Kanpur", "admin1": "Uttar Pradesh", "country": "India",
                     "latitude": 26.44991, "longitude": 80.33191}]}):
                hits = weather_svc.search_city("kanpur")
        self.assertEqual(hits[0]["label"], "Kanpur, Uttar Pradesh, India")
        self.assertEqual((hits[0]["lat"], hits[0]["lon"]), (26.45, 80.33))


if __name__ == "__main__":
    unittest.main()


class CitySearchRankingTestCase(LocationTestCase):
    """The 'Nepal, Nepal / Nepal, Pakistan' confusion: results must be ranked
    so the obviously-intended place is first, and labelled well enough to
    tell the rest apart."""

    RAW = {"results": [
        {"name": "Nepal", "admin1": "Punjab", "country": "Pakistan",
         "country_code": "PK", "population": 1200, "latitude": 32.1, "longitude": 73.0},
        {"name": "Nepal", "admin1": "Central Java", "country": "Indonesia",
         "country_code": "ID", "population": 5000, "latitude": -7.0, "longitude": 110.0},
        {"name": "Kathmandu", "admin1": "Bagmati", "country": "Nepal",
         "country_code": "NP", "population": 1442271, "latitude": 27.7, "longitude": 85.3},
        # duplicate of the first — must be collapsed
        {"name": "Nepal", "admin1": "Punjab", "country": "Pakistan",
         "country_code": "PK", "population": 1200, "latitude": 32.1, "longitude": 73.0},
    ]}

    def test_results_are_ranked_deduped_and_labelled(self):
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json", return_value=self.RAW):
                hits = weather_svc.search_city("nepal")
        self.assertEqual(len(hits), 3)                     # duplicate collapsed
        self.assertEqual(hits[0]["name"], "Kathmandu")     # biggest first
        self.assertEqual(hits[0]["flag"], "🇳🇵")
        self.assertEqual(hits[0]["population_label"], "1.4M people")
        # every result still says which country it's in
        for h in hits:
            self.assertTrue(h["country"])
            self.assertIn(h["country"], h["label"])

    def test_country_hint_floats_the_right_country_up(self):
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json", return_value=self.RAW):
                hits = weather_svc.search_city("nepal", country_hint="Pakistan")
        self.assertEqual(hits[0]["country"], "Pakistan")

    def test_short_queries_do_not_hit_the_api(self):
        with self.app.app_context():
            with mock.patch.object(weather_svc, "_http_json") as m:
                self.assertEqual(weather_svc.search_city("k"), [])
                m.assert_not_called()
