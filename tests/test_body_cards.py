"""Tests for body basics + flash cards."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from healthbuddy import create_app
from healthbuddy.db import execute, query
from healthbuddy.services import body as body_svc
from healthbuddy.services import flashcards


class BodyAndCardsTestCase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".db")
        self.app = create_app({"DATABASE": self.db_path, "TESTING": True, "SECRET_KEY": "t"})
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def auth(self, email="b@example.com"):
        r = self.client.post("/api/auth/register",
                             json={"email": email, "name": "B", "password": "password123"})
        tok = self.client.post("/api/auth/register/verify",
                               json={"email": email, "code": r.get_json()["dev_code"]}
                               ).get_json()["token"]
        h = {"Authorization": "Bearer " + tok}
        self.client.post("/api/onboarding", headers=h,
                         json={"occupation": "student", "gender": "female",
                               "activity_level": "moderate", "health_goals": ["general"]})
        return h

    # ---------------- body basics ----------------
    def test_bmi_maths_and_bands(self):
        self.assertEqual(body_svc.bmi(170, 65), 22.5)
        self.assertEqual(body_svc.bmi(160, 45), 17.6)
        self.assertIsNone(body_svc.bmi(None, 65))
        self.assertIsNone(body_svc.bmi(170, None))
        self.assertEqual(body_svc.bmi_band(17.0), "below the typical range")
        self.assertEqual(body_svc.bmi_band(22.5), "in the typical range")
        self.assertEqual(body_svc.bmi_band(27.0), "above the typical range")

    def test_bmi_language_is_never_a_verdict(self):
        """Guards the product stance: BMI is described, never prescribed.
        The bands must not use clinical labels or imply the user should
        change; the explanatory note may say 'not a target' — that's the
        reassurance, so only the BANDS are checked for those words."""
        bands = " ".join(filter(None, [body_svc.bmi_band(v) for v in (16, 22, 27, 33)])).lower()
        for banned in ("obese", "overweight", "underweight", "lose weight",
                       "should", "target", "ideal", "unhealthy", "normal"):
            self.assertNotIn(banned, bands)
        note = body_svc.summary(_row(170, 65, None))["note"].lower()
        for reassurance in ("not a target", "rough"):
            self.assertIn(reassurance, note)
        for banned in ("lose weight", "you should", "goal weight"):
            self.assertNotIn(banned, note)

    def test_age_from_dob(self):
        born = date.today().replace(year=date.today().year - 20)
        self.assertEqual(body_svc.age_from_dob(born.isoformat()), 20)
        tomorrow_bday = (date.today() + timedelta(days=1)).replace(year=date.today().year - 20)
        self.assertEqual(body_svc.age_from_dob(tomorrow_bday.isoformat()), 19)
        self.assertIsNone(body_svc.age_from_dob(None))
        self.assertIsNone(body_svc.age_from_dob("garbage"))

    def test_body_endpoint_saves_and_validates(self):
        h = self.auth()
        res = self.client.patch("/api/body", headers=h,
                                json={"dob": "2003-07-15", "height_cm": 165, "weight_kg": 58})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["bmi"], 21.3)
        for bad in ({"height_cm": 5}, {"weight_kg": 999}, {"dob": "not-a-date"},
                    {"dob": (date.today() + timedelta(days=2)).isoformat()}):
            self.assertEqual(self.client.patch("/api/body", headers=h, json=bad).status_code, 400)

    def test_body_fields_are_optional_and_clearable(self):
        h = self.auth()
        self.assertIsNone(self.client.get("/api/body", headers=h).get_json()["bmi"])
        self.client.patch("/api/body", headers=h, json={"height_cm": 170, "weight_kg": 70})
        self.assertIsNotNone(self.client.get("/api/body", headers=h).get_json()["bmi"])
        self.client.patch("/api/body", headers=h, json={"weight_kg": None})
        self.assertIsNone(self.client.get("/api/body", headers=h).get_json()["bmi"])

    # ---------------- flash cards ----------------
    def _age_account(self, days):
        execute("UPDATE users SET created_at = datetime('now', ?) WHERE id=1",
                (f"-{days} days",))

    def test_first_card_waits_then_appears(self):
        h = self.auth()
        with self.app.app_context():
            self._age_account(0)
            self.assertIsNone(flashcards.due_card(1, query("SELECT created_at FROM users WHERE id=1",
                                                           one=True)["created_at"]))
            self._age_account(3)
            card = flashcards.due_card(1, query("SELECT created_at FROM users WHERE id=1",
                                                one=True)["created_at"])
            self.assertIsNotNone(card)
            self.assertFalse(card["sensitive"])      # light questions come first

    def test_cooldown_between_cards(self):
        h = self.auth()
        with self.app.app_context():
            self._age_account(5)
            created = query("SELECT created_at FROM users WHERE id=1", one=True)["created_at"]
            first = flashcards.due_card(1, created)
            flashcards.record(1, first["id"], "Vegetarian")
            self.assertIsNone(flashcards.due_card(1, created))          # too soon
            execute("UPDATE profile_answers SET answered_at = datetime('now','-4 days')")
            self.assertIsNotNone(flashcards.due_card(1, created))       # cooldown passed

    def test_skipping_is_recorded_and_not_re_asked(self):
        h = self.auth()
        with self.app.app_context():
            self._age_account(5)
            created = query("SELECT created_at FROM users WHERE id=1", one=True)["created_at"]
            card = flashcards.due_card(1, created)
            flashcards.record(1, card["id"], skipped=True)
            execute("UPDATE profile_answers SET answered_at = datetime('now','-9 days')")
            nxt = flashcards.due_card(1, created)
            self.assertNotEqual(nxt["id"], card["id"])

    def test_answers_are_private_and_deletable(self):
        h = self.auth()
        self.client.post("/api/flashcard", headers=h,
                         json={"question_id": "conditions", "answer": "Asthma / breathing"})
        got = self.client.get("/api/flashcard/answers", headers=h).get_json()["answers"]
        self.assertEqual(got[0]["answer"], "Asthma / breathing")

        # must never surface on the leaderboard
        board = self.client.get("/api/leaderboard?scope=global", headers=h).get_json()
        self.assertNotIn("Asthma", json.dumps(board))

        self.client.delete("/api/flashcard/answers", headers=h)
        self.assertEqual(self.client.get("/api/flashcard/answers", headers=h).get_json()["answers"], [])

    def test_bad_question_rejected(self):
        h = self.auth()
        res = self.client.post("/api/flashcard", headers=h,
                               json={"question_id": "not_a_real_question", "answer": "x"})
        self.assertEqual(res.status_code, 400)

    def test_hints_are_presence_only_never_diagnoses(self):
        h = self.auth()
        self.client.post("/api/flashcard", headers=h,
                         json={"question_id": "conditions", "answer": "Diabetes"})
        self.client.post("/api/flashcard", headers=h,
                         json={"question_id": "allergies", "answer": "Nuts"})
        with self.app.app_context():
            hints = flashcards.personalization_hints(1)
        self.assertTrue(hints["has_condition"])       # a flag, not the condition
        self.assertNotIn("Diabetes", json.dumps(hints))
        self.assertEqual(hints["allergy"], "Nuts")    # kept, so food nudges can avoid it


def _row(h, w, dob):
    """Tiny stand-in for a sqlite Row in the language test."""
    class R(dict):
        def keys(self):
            return super().keys()
        def __getitem__(self, k):
            return super().get(k)
    return R(height_cm=h, weight_kg=w, dob=dob)


if __name__ == "__main__":
    unittest.main()


class AccountDeletionTestCase(BodyAndCardsTestCase):
    """Deleting an account must be complete — and must free the email."""

    def _populate(self, h):
        self.client.post("/api/logs", headers=h, json={"type": "water", "value": 1})
        self.client.post("/api/flashcard", headers=h,
                         json={"question_id": "conditions", "answer": "Asthma / breathing"})
        self.client.post("/api/location", headers=h, json={"lat": 26.45, "lon": 80.33})
        self.client.post("/api/activity/manual", headers=h, json={"steps": 4000})
        self.client.patch("/api/body", headers=h, json={"height_cm": 165, "weight_kg": 58})

    def test_delete_removes_every_trace_and_frees_the_email(self):
        h = self.auth("gone@example.com")
        self._populate(h)
        with self.app.app_context():
            uid = query("SELECT id FROM users WHERE email='gone@example.com'", one=True)["id"]

        res = self.client.delete("/api/account", headers=h, json={"password": "password123"})
        self.assertEqual(res.status_code, 200, res.get_json())

        with self.app.app_context():
            from healthbuddy.services.account import _tables_with_user_id
            self.assertIsNone(query("SELECT 1 FROM users WHERE id=?", (uid,), one=True))
            for table in _tables_with_user_id():
                left = query(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (uid,), one=True)["n"]
                self.assertEqual(left, 0, f"{table} still holds data for the deleted user")
            self.assertIsNone(query("SELECT 1 FROM email_otps WHERE email='gone@example.com'", one=True))

        # the whole point: sign up again with the same email
        again = self.client.post("/api/auth/register",
                                 json={"email": "gone@example.com", "name": "Fresh",
                                       "password": "password123"})
        self.assertEqual(again.status_code, 200)
        verified = self.client.post("/api/auth/register/verify",
                                    json={"email": "gone@example.com",
                                          "code": again.get_json()["dev_code"]})
        self.assertEqual(verified.status_code, 201)
        self.assertEqual(verified.get_json()["user"]["name"], "Fresh")

    def test_wrong_password_deletes_nothing(self):
        h = self.auth("safe@example.com")
        self._populate(h)
        res = self.client.delete("/api/account", headers=h, json={"password": "wrongwrong"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.client.get("/api/dashboard", headers=h).status_code, 200)

    def test_old_session_stops_working_after_deletion(self):
        h = self.auth("bye@example.com")
        self.client.delete("/api/account", headers=h, json={"password": "password123"})
        self.assertEqual(self.client.get("/api/dashboard", headers=h).status_code, 401)

    def test_buddy_links_pointing_at_the_deleted_user_are_cleaned_up(self):
        me = self.auth("stay@example.com")
        them = self.auth("leaving@example.com")
        code = self.client.get("/api/buddies", headers=them).get_json()["my_code"]
        self.client.post("/api/buddies/link", headers=me, json={"code": code})
        self.client.delete("/api/account", headers=them, json={"password": "password123"})
        # the remaining user's buddy list must not reference a ghost
        buds = self.client.get("/api/buddies", headers=me).get_json()["buddies"]
        self.assertEqual(buds, [])
        self.assertEqual(self.client.get("/api/leaderboard?scope=buddies", headers=me).status_code, 200)

    def test_deletion_covers_new_tables_automatically(self):
        """The table list is derived from the schema, so a future table with a
        user_id column is covered without anyone remembering to update it."""
        with self.app.app_context():
            from healthbuddy.services.account import _tables_with_user_id
            covered = set(_tables_with_user_id())
        for expected in ("habit_logs", "profile_answers", "activity_daily",
                         "cycle_settings", "game_scores", "sessions"):
            self.assertIn(expected, covered)
