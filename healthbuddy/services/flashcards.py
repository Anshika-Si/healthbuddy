"""Flash cards — one small question every few days.

The idea: instead of a 20-question intake form nobody finishes, ask ONE
question every 3–4 days when someone opens the app. Cheap for the user,
and it gradually builds a richer picture for personalization.

RULES BAKED IN:
* One card at a time, and no more than one per COOLDOWN_DAYS.
* Every card is skippable, and "Prefer not to say" is always an option —
  a skipped card is recorded so we don't ask it again for a long while.
* Health answers (conditions, medicines, allergies) are personal data:
  stored privately, never shown to buddies or on leaderboards, never used
  for advertising, and deletable in one tap.
* Nothing here diagnoses or advises. Answers tune *which* nudges appear
  and add mild caution (e.g. someone reporting a condition sees fewer
  "push harder" movement lines and more "check with your doctor" framing).
"""
import hashlib
from datetime import date, datetime

from ..db import execute, query

COOLDOWN_DAYS = 3          # minimum gap between cards
FIRST_CARD_AFTER_DAYS = 1  # let people use the app a bit before asking

SKIP = "prefer_not_to_say"

#: id, category, question, options (free_text=True means an optional text box)
QUESTIONS = [
    {"id": "conditions", "emoji": "🩺", "sensitive": True,
     "q": "Any ongoing health conditions we should keep in mind?",
     "why": "So nudges stay sensible for you — never to diagnose anything.",
     "options": ["None", "Asthma / breathing", "Diabetes", "Thyroid",
                 "PCOS / hormonal", "Blood pressure", "Something else"],
     "free_text": True},
    {"id": "medicines", "emoji": "💊", "sensitive": True,
     "q": "Do you take any medicines regularly?",
     "why": "Handy for timing reminders around meals or sleep.",
     "options": ["No", "Yes, daily", "Yes, occasionally"],
     "free_text": True},
    {"id": "allergies", "emoji": "🌾", "sensitive": True,
     "q": "Any known allergies?",
     "why": "So food nudges don't suggest something you can't eat.",
     "options": ["None", "Dust / pollen", "Dairy", "Nuts", "Gluten",
                 "Seafood", "Something else"],
     "free_text": True},
    {"id": "diet", "emoji": "🥗", "sensitive": False,
     "q": "How would you describe your usual diet?",
     "why": "Food nudges will match what you actually eat.",
     "options": ["Vegetarian", "Non-vegetarian", "Eggetarian", "Vegan", "It varies"]},
    {"id": "water_source", "emoji": "🚰", "sensitive": False,
     "q": "Do you keep a water bottle near you during the day?",
     "why": "The easiest hydration nudge is 'sip what's already next to you'.",
     "options": ["Always", "Sometimes", "Never"]},
    {"id": "sleep_pattern", "emoji": "🌙", "sensitive": False,
     "q": "What's your usual bedtime?",
     "why": "Wind-down nudges land better when they match your actual night.",
     "options": ["Before 11pm", "11pm–1am", "After 1am", "Wildly inconsistent"]},
    {"id": "activity_type", "emoji": "🏃", "sensitive": False,
     "q": "What movement do you actually enjoy?",
     "why": "Movement nudges will lean toward things you don't hate.",
     "options": ["Walking", "Gym", "Sports", "Yoga / stretching",
                 "Dance", "Nothing yet — help me find something"]},
    {"id": "stress_trigger", "emoji": "😮‍💨", "sensitive": False,
     "q": "What usually spikes your stress?",
     "why": "So calming nudges arrive at the right moments.",
     "options": ["Deadlines / exams", "Work pressure", "Social stuff",
                 "Money", "Health worries", "Prefer not to say"]},
    {"id": "meal_skipping", "emoji": "🍽️", "sensitive": False,
     "q": "Which meal do you skip most often?",
     "why": "We'll nudge that one specifically instead of nagging about all three.",
     "options": ["Breakfast", "Lunch", "Dinner", "I don't skip meals"]},
    {"id": "screen_wind_down", "emoji": "📱", "sensitive": False,
     "q": "Do you use your phone in bed before sleeping?",
     "why": "Wind-down nudges are only useful if they're honest about your habits.",
     "options": ["Every night", "Sometimes", "Rarely"]},
]

BY_ID = {q["id"]: q for q in QUESTIONS}


def answered_ids(user_id):
    return {r["question_id"] for r in
            query("SELECT question_id FROM profile_answers WHERE user_id=?", (user_id,))}


def _last_answered_at(user_id):
    row = query("""SELECT answered_at FROM profile_answers
                   WHERE user_id=? ORDER BY answered_at DESC LIMIT 1""",
                (user_id,), one=True)
    return row["answered_at"] if row else None


def _days_since(ts):
    if not ts:
        return None
    try:
        when = datetime.fromisoformat(str(ts).replace("Z", ""))
    except ValueError:
        return None
    return (datetime.now() - when).days


def due_card(user_id, user_created_at=None):
    """The next card to show, or None. Order is stable per user (hashed) so
    it doesn't jump around, and sensitive questions never come first."""
    done = answered_ids(user_id)
    remaining = [q for q in QUESTIONS if q["id"] not in done]
    if not remaining:
        return None

    since_last = _days_since(_last_answered_at(user_id))
    if since_last is not None and since_last < COOLDOWN_DAYS:
        return None
    if since_last is None:                       # never answered anything yet
        age_days = _days_since(user_created_at)
        if age_days is not None and age_days < FIRST_CARD_AFTER_DAYS:
            return None

    # stable per-user shuffle; light questions first, sensitive ones later
    def key(q):
        h = hashlib.sha256(f"{user_id}:{q['id']}".encode()).hexdigest()
        return (1 if q["sensitive"] else 0, h)

    q = sorted(remaining, key=key)[0]
    return {**q, "remaining": len(remaining)}


def record(user_id, question_id, answer=None, skipped=False):
    if question_id not in BY_ID:
        raise ValueError("Unknown question.")
    value = None if skipped else (str(answer or "").strip()[:200] or None)
    if value is None and not skipped:
        raise ValueError("Pick an option or skip.")
    execute("""INSERT INTO profile_answers (user_id, question_id, answer, skipped, answered_at)
               VALUES (?,?,?,?,datetime('now'))
               ON CONFLICT(user_id, question_id) DO UPDATE SET
                 answer=excluded.answer, skipped=excluded.skipped,
                 answered_at=datetime('now')""",
            (user_id, question_id, value, 1 if skipped else 0))
    return {"question_id": question_id, "saved": True}


def answers(user_id, include_sensitive=True):
    """Everything this user has told us, for their own profile screen."""
    rows = query("""SELECT question_id, answer, skipped, answered_at
                    FROM profile_answers WHERE user_id=? ORDER BY answered_at""",
                 (user_id,))
    out = []
    for r in rows:
        meta = BY_ID.get(r["question_id"])
        if not meta or (meta["sensitive"] and not include_sensitive):
            continue
        out.append({"id": r["question_id"], "emoji": meta["emoji"], "q": meta["q"],
                    "answer": None if r["skipped"] else r["answer"],
                    "skipped": bool(r["skipped"]), "sensitive": meta["sensitive"],
                    "answered_at": r["answered_at"]})
    return out


def clear(user_id, question_id=None):
    if question_id:
        execute("DELETE FROM profile_answers WHERE user_id=? AND question_id=?",
                (user_id, question_id))
    else:
        execute("DELETE FROM profile_answers WHERE user_id=?", (user_id,))


def personalization_hints(user_id):
    """Compact, non-diagnostic signals other services can read. Presence
    only — we never infer a diagnosis or treat these as medical facts."""
    given = {a["id"]: a["answer"] for a in answers(user_id) if a["answer"]}
    hint = {}
    if given.get("conditions") and given["conditions"] not in ("None",):
        hint["has_condition"] = True          # → softer "push harder" copy
    if given.get("allergies") and given["allergies"] not in ("None",):
        hint["allergy"] = given["allergies"]  # → skip food nudges naming it
    if given.get("diet"):
        hint["diet"] = given["diet"]
    if given.get("meal_skipping"):
        hint["skipped_meal"] = given["meal_skipping"]
    if given.get("activity_type"):
        hint["preferred_movement"] = given["activity_type"]
    if given.get("sleep_pattern"):
        hint["bedtime"] = given["sleep_pattern"]
    return hint
