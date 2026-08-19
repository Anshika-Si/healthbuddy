"""Body basics — age and BMI, handled carefully.

DESIGN STANCE (deliberate, please keep it):

* Everything here is **optional**. Height, weight and date of birth can be
  left blank forever and nothing in the app degrades.
* BMI is shown as **information, not a verdict**. It's a crude
  population-level ratio that ignores muscle, build, age and ethnicity, so
  the app says so plainly rather than implying a target.
* We never generate weight-loss nudges, calorie targets, "you should lose
  X kg" copy, or streaks around weighing yourself. A habit app nagging
  people about weight is how you nudge someone into disordered eating.
* Age is used only for gentle copy tuning, never to gate features.
"""
from datetime import date


def parse_dob(value):
    """Accepts YYYY-MM-DD. Returns a date, or raises ValueError with a
    friendly message."""
    try:
        d = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError("Use a date like 2003-07-15.")
    today = date.today()
    if d > today:
        raise ValueError("That date of birth is in the future.")
    if (today.year - d.year) > 120:
        raise ValueError("That date of birth seems too far back.")
    return d


def age_from_dob(dob):
    if not dob:
        return None
    try:
        d = date.fromisoformat(str(dob))
    except (TypeError, ValueError):
        return None
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def validate_height(cm):
    h = float(cm)
    if not (60 <= h <= 250):
        raise ValueError("Height should be between 60 and 250 cm.")
    return round(h, 1)


def validate_weight(kg):
    w = float(kg)
    if not (20 <= w <= 300):
        raise ValueError("Weight should be between 20 and 300 kg.")
    return round(w, 1)


def bmi(height_cm, weight_kg):
    if not height_cm or not weight_kg:
        return None
    m = float(height_cm) / 100.0
    if m <= 0:
        return None
    return round(float(weight_kg) / (m * m), 1)


#: WHO categories, worded as neutral descriptions — no "good/bad", no targets.
def bmi_band(value):
    if value is None:
        return None
    if value < 18.5:
        return "below the typical range"
    if value < 25:
        return "in the typical range"
    if value < 30:
        return "above the typical range"
    return "well above the typical range"


def summary(user_row):
    """What the profile screen shows. Returns None-safe fields only."""
    height = user_row["height_cm"] if "height_cm" in user_row.keys() else None
    weight = user_row["weight_kg"] if "weight_kg" in user_row.keys() else None
    dob = user_row["dob"] if "dob" in user_row.keys() else None
    value = bmi(height, weight)
    return {
        "dob": dob,
        "age": age_from_dob(dob),
        "height_cm": height,
        "weight_kg": weight,
        "bmi": value,
        "bmi_band": bmi_band(value),
        "note": ("BMI is a rough population measure — it can't see muscle, "
                 "build or bone. It's here for context, not a target."),
    }
