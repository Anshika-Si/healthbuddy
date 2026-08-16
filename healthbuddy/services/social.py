"""Challenges, leaderboards, and the buddy system."""
from datetime import date
from ..db import query, execute
from . import gamification


def _progress(user_id, ch):
    if ch["metric_type"] == "nudge_acted":
        row = query("SELECT COUNT(*) AS n FROM interaction_logs WHERE user_id=? AND action='acted' "
                    "AND date(created_at) BETWEEN ? AND ?",
                    (user_id, ch["starts_on"], ch["ends_on"]), one=True)
    else:
        row = query("SELECT COUNT(DISTINCT logged_on) AS n FROM habit_logs WHERE user_id=? AND type=? "
                    "AND logged_on BETWEEN ? AND ?",
                    (user_id, ch["metric_type"], ch["starts_on"], ch["ends_on"]), one=True)
    return min(row["n"], ch["target"])


def list_challenges(user_id):
    today = date.today().isoformat()
    rows = query("SELECT * FROM challenges WHERE ends_on >= ? ORDER BY starts_on", (today,))
    joined = {r["challenge_id"] for r in
              query("SELECT challenge_id FROM challenge_members WHERE user_id=?", (user_id,))}
    out = []
    for ch in rows:
        members = query("SELECT COUNT(*) AS n FROM challenge_members WHERE challenge_id=?",
                        (ch["id"],), one=True)["n"]
        item = dict(ch) | {"members": members, "joined": ch["id"] in joined}
        if item["joined"]:
            item["progress"] = _progress(user_id, ch)
        out.append(item)
    return out


def join(user_id, challenge_id):
    ch = query("SELECT * FROM challenges WHERE id=?", (challenge_id,), one=True)
    if ch is None:
        raise LookupError("challenge not found")
    already = query("SELECT 1 FROM challenge_members WHERE challenge_id=? AND user_id=?",
                    (challenge_id, user_id), one=True)
    if already:
        return {"xp_earned": 0, "new_badges": []}
    execute("INSERT INTO challenge_members (challenge_id, user_id) VALUES (?,?)", (challenge_id, user_id))
    xp = gamification.award_xp(user_id, "challenge_join")
    return {"xp_earned": xp, "new_badges": gamification.check_and_award(user_id)}


def leaderboard(challenge_id, limit=20):
    ch = query("SELECT * FROM challenges WHERE id=?", (challenge_id,), one=True)
    if ch is None:
        raise LookupError("challenge not found")
    members = query("SELECT u.id, u.name FROM challenge_members cm JOIN users u ON u.id=cm.user_id "
                    "WHERE cm.challenge_id=?", (challenge_id,))
    board = sorted(
        ({"user_id": m["id"], "name": m["name"], "progress": _progress(m["id"], ch)} for m in members),
        key=lambda x: -x["progress"])[:limit]
    for i, row in enumerate(board, 1):
        row["rank"] = i
    return {"challenge": dict(ch), "leaderboard": board}


def link_buddy(user_id, buddy_code):
    buddy = query("SELECT id, name FROM users WHERE buddy_code=?", (buddy_code.strip().upper(),), one=True)
    if buddy is None:
        raise LookupError("No one has that buddy code. Double-check it with your friend.")
    if buddy["id"] == user_id:
        raise ValueError("That's your own code! Share it with a friend instead.")
    for a, b in ((user_id, buddy["id"]), (buddy["id"], user_id)):
        if not query("SELECT 1 FROM buddies WHERE user_id=? AND buddy_id=?", (a, b), one=True):
            execute("INSERT INTO buddies (user_id, buddy_id) VALUES (?,?)", (a, b))
    gamification.check_and_award(user_id)
    gamification.check_and_award(buddy["id"])
    return {"buddy": {"id": buddy["id"], "name": buddy["name"]}}


def list_buddies(user_id):
    rows = query("SELECT u.id, u.name FROM buddies b JOIN users u ON u.id=b.buddy_id WHERE b.user_id=?",
                 (user_id,))
    return [{"id": r["id"], "name": r["name"], "streaks": gamification.all_streaks(r["id"])} for r in rows]


def unlink_buddy(user_id, buddy_id):
    """Remove the link both ways. Quiet and drama-free."""
    execute("DELETE FROM buddies WHERE user_id=? AND buddy_id=?", (user_id, buddy_id))
    execute("DELETE FROM buddies WHERE user_id=? AND buddy_id=?", (buddy_id, user_id))


def xp_leaderboard(user_id, scope="buddies", limit=50):
    """Competitive ranking by XP.

    scope="buddies" → you + the people you've linked with.
    scope="global"  → everyone on HealthBuddy (top `limit`), plus your own row
                      appended if you fall outside the top slice, so you can
                      always see where you stand.

    Only public progress is exposed — name, avatar, XP, level, badge count and
    longest streak. Never habit logs, steps, screen time or cycle data.
    A single efficient query per scope; XP is summed in SQL rather than
    per-user so this stays fast as the user base grows.
    """
    from . import gamification
    scope = "global" if scope == "global" else "buddies"

    if scope == "buddies":
        ids = [user_id] + [r["buddy_id"] for r in
                           query("SELECT buddy_id FROM buddies WHERE user_id=?", (user_id,))]
        placeholders = ",".join("?" * len(ids))
        rows = query(f"""SELECT u.id, u.name, u.avatar,
                                COALESCE(SUM(x.amount), 0) AS xp
                         FROM users u LEFT JOIN xp_events x ON x.user_id = u.id
                         WHERE u.id IN ({placeholders})
                         GROUP BY u.id, u.name, u.avatar
                         ORDER BY xp DESC, u.name""", tuple(ids))
    else:
        rows = query("""SELECT u.id, u.name, u.avatar,
                               COALESCE(SUM(x.amount), 0) AS xp
                        FROM users u LEFT JOIN xp_events x ON x.user_id = u.id
                        WHERE u.onboarded = 1
                        GROUP BY u.id, u.name, u.avatar
                        ORDER BY xp DESC, u.name
                        LIMIT ?""", (limit,))

    out = []
    for i, r in enumerate(rows, 1):
        badges = query("SELECT COUNT(*) AS n FROM user_badges WHERE user_id=?",
                       (r["id"],), one=True)["n"]
        streaks = gamification.all_streaks(r["id"])
        out.append({"rank": i, "user_id": r["id"], "name": r["name"],
                    "avatar": r["avatar"] or "🙂", "xp": int(r["xp"]),
                    "level": gamification.level_for(int(r["xp"])), "badges": badges,
                    "best_streak": max(streaks.values()) if streaks else 0,
                    "is_you": r["id"] == user_id})

    you = next((r for r in out if r["is_you"]), None)
    if scope == "global" and you is None:
        # outside the top slice — work out the true rank and append the row
        my_xp = gamification.total_xp(user_id)
        ahead = query("""SELECT COUNT(*) AS n FROM (
                             SELECT u.id, COALESCE(SUM(x.amount), 0) AS xp
                             FROM users u LEFT JOIN xp_events x ON x.user_id = u.id
                             WHERE u.onboarded = 1
                             GROUP BY u.id HAVING COALESCE(SUM(x.amount), 0) > ?
                         ) t""", (my_xp,), one=True)["n"]
        me = query("SELECT id, name, avatar FROM users WHERE id=?", (user_id,), one=True)
        streaks = gamification.all_streaks(user_id)
        you = {"rank": ahead + 1, "user_id": user_id, "name": me["name"],
               "avatar": me["avatar"] or "🙂", "xp": my_xp,
               "level": gamification.level_for(my_xp),
               "badges": query("SELECT COUNT(*) AS n FROM user_badges WHERE user_id=?",
                               (user_id,), one=True)["n"],
               "best_streak": max(streaks.values()) if streaks else 0,
               "is_you": True, "outside_top": True}

    return {"scope": scope, "rows": out, "you": you,
            "total_players": query("SELECT COUNT(*) AS n FROM users WHERE onboarded=1",
                                   one=True)["n"] if scope == "global" else len(out)}
