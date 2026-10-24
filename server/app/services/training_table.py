"""
The training table for the readiness model: one row per person per night, joining
  - the score first shown that morning and the exact inputs behind it (readiness_snapshots)
  - that morning's check-in answers, the label (checkins, the check-in on day D labels night D-1)
  - training load from rated workouts up to that evening (effort x minutes)

Nights a run added along with a newer night (a first sync or an import) were never shown on Today,
so they're left out unless asked for. The placeholder score is included only to compare against,
never to train on.
"""

import json
from datetime import date, timedelta

import pandas as pd

from app.readiness.features import FEATURE_COLUMNS
from app.services.time_checks import local_time

CHECKIN_SCALES = [
    "ready_to_train",
    "sleep_quality",
    "fatigue",
    "energy",
    "stress",
    "motivation",
    "hydration",
    "soreness",
]
LOAD_WINDOWS = {"load_1d": 1, "load_3d": 3, "load_7d": 7, "load_28d": 28}

COLUMNS = [
    "person_id",
    "night_date",
    "catch_up",
    "taken_local",
    "model_version",
    "placeholder_score",
    "placeholder_status",
    "confidence",
    *FEATURE_COLUMNS,
    *LOAD_WINDOWS,
    "rated_workouts_7d",
    "weight_kg",
    *[f"checkin_{c}" for c in CHECKIN_SCALES],
    "checkin_sore_muscles",
    "checkin_unusual",
    "checkin_rehydrated",
    "checkin_answered_local",
]


def _list(values) -> str | None:
    """["quads", "glutes"] -> "quads;glutes". An empty list was a real answer ("None"), so it stays visible."""
    if values is None:
        return None
    return ";".join(values) if values else "none"


def _daily_load(conn, user_id: str) -> dict[date, float]:
    """Effort x minutes per local day, from rated workouts only."""
    out: dict[date, float] = {}
    rows = conn.execute(
        "SELECT start_ms, end_ms, start_tz_min, effort FROM workouts WHERE user_id = ? AND effort IS NOT NULL",
        (user_id,),
    )
    for r in rows:
        day = local_time(r["start_ms"], r["start_tz_min"]).date()
        out[day] = out.get(day, 0.0) + r["effort"] * (r["end_ms"] - r["start_ms"]) / 60000
    return out


def _rated_days(conn, user_id: str) -> list[date]:
    rows = conn.execute(
        "SELECT start_ms, start_tz_min FROM workouts WHERE user_id = ? AND effort IS NOT NULL", (user_id,)
    )
    return [local_time(r["start_ms"], r["start_tz_min"]).date() for r in rows]


def build(conn, user_ids: list[str] | None = None, include_catch_up: bool = False) -> pd.DataFrame:
    if user_ids is None:
        user_ids = [r[0] for r in conn.execute("SELECT user_id FROM users ORDER BY user_id")]
    rows = []
    for user_id in user_ids:
        weight = conn.execute("SELECT weight_kg FROM users WHERE user_id = ?", (user_id,)).fetchone()
        load = _daily_load(conn, user_id)
        rated = _rated_days(conn, user_id)
        checkins = {r["night_date"]: r for r in conn.execute("SELECT * FROM checkins WHERE user_id = ?", (user_id,))}
        snaps = conn.execute(
            "SELECT * FROM readiness_snapshots WHERE user_id = ? ORDER BY night_date", (user_id,)
        ).fetchall()
        for s in snaps:
            if s["catch_up"] and not include_catch_up:
                continue
            night = date.fromisoformat(s["night_date"])
            row = {
                "person_id": user_id,
                "night_date": s["night_date"],
                "catch_up": s["catch_up"],
                "taken_local": s["taken_local"],
                "model_version": s["model_version"],
                "placeholder_score": s["score"],
                "placeholder_status": s["status"],
                "confidence": s["confidence"],
                **json.loads(s["features"]),
                "weight_kg": weight["weight_kg"] if weight else None,
            }
            # Training up to and including the evening the night started, since that's what the morning feels.
            for col, days in LOAD_WINDOWS.items():
                row[col] = round(sum(load.get(night - timedelta(days=i), 0.0) for i in range(days)), 1)
            row["rated_workouts_7d"] = sum(1 for d in rated if night - timedelta(days=6) <= d <= night)
            c = checkins.get(s["night_date"])
            if c is not None:
                answers = json.loads(c["answers"])
                for scale in CHECKIN_SCALES:
                    row[f"checkin_{scale}"] = answers.get(scale)
                row["checkin_sore_muscles"] = _list(answers.get("sore_muscles"))
                row["checkin_unusual"] = _list(answers.get("unusual"))
                row["checkin_rehydrated"] = answers.get("rehydrated")
                row["checkin_answered_local"] = local_time(c["answered_at_ms"], c["tz_offset_min"]).isoformat(
                    timespec="minutes"
                )
            rows.append(row)
    return pd.DataFrame(rows, columns=COLUMNS)
