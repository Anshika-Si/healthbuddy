"""Account deletion — complete, verified, irreversible.

Why this exists: someone with a single email address who wants a clean start
shouldn't be locked out forever by their own old account. Deleting frees the
email for immediate re-registration.

Two design points worth keeping:

* **The table list is derived from the schema, not hand-written.** A
  hand-maintained list rots — someone adds a table, forgets this file, and
  personal data quietly survives a "delete my account". Instead we read
  db.SCHEMA and delete from every table that has a user_id column, so new
  tables are covered automatically. A test asserts the coverage.

* **Password required.** Deletion is destructive and permanent, so we
  re-verify the password even though the caller is already authenticated —
  it stops a borrowed unlocked phone from wiping someone's account.
"""
import re

from ..auth import verify_password
from ..db import SCHEMA, execute, query


def _tables_with_user_id():
    """Every table that stores something belonging to a user."""
    found = []
    for name, body in re.findall(r"CREATE TABLE IF NOT EXISTS (\w+) \((.*?)\n\);", SCHEMA, re.S):
        if re.search(r"^\s*user_id\b", body, re.M):
            found.append(name)
    return found


def preview(user_id):
    """What deletion would remove — shown in the confirmation dialog so the
    decision is informed rather than a blind 'are you sure?'."""
    counts = {}
    for table in _tables_with_user_id():
        try:
            n = query(f"SELECT COUNT(*) AS n FROM {table} WHERE user_id=?", (user_id,), one=True)["n"]
        except Exception:
            n = 0
        if n:
            counts[table] = n
    friendly = {
        "habit_logs": "habit logs", "interaction_logs": "nudge responses",
        "xp_events": "XP entries", "user_badges": "badges", "buddies": "buddy links",
        "game_scores": "game scores", "profile_answers": "flash-card answers",
        "cycle_history": "cycle records", "activity_daily": "step records",
        "device_wellbeing_daily": "screen-time records",
        "challenge_members": "challenge entries",
    }
    return {"items": [{"what": friendly.get(k, k.replace("_", " ")), "count": v}
                      for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
                      if k in friendly],
            "total_tables": len(counts)}


def delete_account(user_id, password):
    """Verify the password, then erase everything. Returns the freed email."""
    user = query("SELECT * FROM users WHERE id=?", (user_id,), one=True)
    if not user:
        raise LookupError("Account not found.")
    if not password or not verify_password(password, user["password_hash"]):
        raise PermissionError("That password doesn't match. Nothing was deleted.")

    email = user["email"]

    # rows where this user is the *other* side of a relationship
    execute("DELETE FROM buddies WHERE buddy_id=?", (user_id,))

    for table in _tables_with_user_id():
        execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))

    # anything keyed by email rather than user id, so re-registering is clean
    execute("DELETE FROM email_otps WHERE email=?", (email,))
    execute("DELETE FROM pending_signups WHERE email=?", (email,))

    execute("DELETE FROM users WHERE id=?", (user_id,))
    return email
