"""Central configuration. Everything overridable via environment variables."""
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    SECRET_KEY = os.environ.get("HB_SECRET_KEY", "dev-only-change-me")
    DATABASE = os.environ.get("HB_DATABASE", os.path.join(BASE_DIR, "healthbuddy.db"))
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_DAYS = int(os.environ.get("HB_JWT_EXPIRY_DAYS", "7"))

    # Bandit tuning
    PRIOR_STRENGTH = 20          # pseudo-observations encoded from onboarding
    RECENT_CARD_WINDOW = 10      # avoid repeating the last N cards

    # Reward mapping: interaction -> reward signal for Thompson Sampling
    REWARDS = {"acted": 1.0, "opened": 0.6, "snoozed": 0.2, "dismissed": 0.0}

    # XP economy
    XP = {
        "nudge_acted": 10,
        "nudge_opened": 2,
        "habit_log": 5,
        "challenge_join": 15,
        "streak_bonus": 20,      # every 7-day streak milestone
        "onboarding": 25,
        "game_played": 5,
        "daily_challenge": 15,
        "cycle_checkin": 5,
        "wrapped_viewed": 10,
        "daily_plan_bonus": 30,
    }


CATEGORIES = ["nutrition", "hydration", "movement", "sleep", "mindfulness", "seasonal"]

CATEGORY_META = {
    "nutrition":   {"emoji": "🥗", "label": "Nutrition",   "color": "#FF8A5C"},
    "hydration":   {"emoji": "💧", "label": "Hydration",   "color": "#4FC3F7"},
    "movement":    {"emoji": "🏃", "label": "Movement",    "color": "#7ED957"},
    "sleep":       {"emoji": "😴", "label": "Sleep",       "color": "#B39DFF"},
    "mindfulness": {"emoji": "🧘", "label": "Mindfulness", "color": "#F7A8C4"},
    "seasonal":    {"emoji": "🌦️", "label": "Seasonal",   "color": "#FFD166"},
}
