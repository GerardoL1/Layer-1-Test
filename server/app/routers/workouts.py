"""
Workouts and the after-workout check-in. Effort (1 to 10) times minutes is the training load the readiness
model will use. Patch and sweat sessions (Layers 2 and 3) point at a workout by its id.
"""

import time

from fastapi import APIRouter, HTTPException, Query

from app.core import db
from app.core.urls import USER
from app.schemas.workouts import RatingIn, Workout, WorkoutIn
from app.services.time_checks import local_time, require_time
from app.services.users import require_user

router = APIRouter(prefix=USER + "/workouts", tags=["workouts"])

MAX_WORKOUT_HOURS = 24


def _out(row) -> dict:
    minutes = round((row["end_ms"] - row["start_ms"]) / 60000, 1)
    effort = row["effort"]
    return {
        "id": row["id"],
        "start_ms": row["start_ms"],
        "end_ms": row["end_ms"],
        "start_tz_min": row["start_tz_min"],
        "end_tz_min": row["end_tz_min"],
        "start_local": local_time(row["start_ms"], row["start_tz_min"]).isoformat(timespec="minutes"),
        "end_local": local_time(row["end_ms"], row["end_tz_min"]).isoformat(timespec="minutes"),
        "source": row["source"],
        "type": row["type"],
        "duration_min": minutes,
        "effort": effort,
        "satisfaction": row["satisfaction"],
        "rated_at_ms": row["rated_at_ms"],
        "load": round(effort * minutes, 1) if effort is not None else None,
    }


def _get(conn, user_id: str, workout_id: str):
    row = conn.execute("SELECT * FROM workouts WHERE user_id = ? AND id = ?", (user_id, workout_id)).fetchone()
    if row is None:
        raise HTTPException(404, f"No workout '{workout_id}'.")
    return row


@router.post("", response_model=Workout)
def save_workout(user_id: str, w: WorkoutIn):
    """Adds a workout, or updates it when the same id is sent again. A rating already given is kept."""
    require_time(w.start_ms, w.start_tz_min, "The workout start")
    require_time(w.end_ms, w.end_tz_min, "The workout end")
    if w.end_ms <= w.start_ms:
        raise HTTPException(400, "The workout ends before it starts.")
    if w.end_ms - w.start_ms > MAX_WORKOUT_HOURS * 3600 * 1000:
        raise HTTPException(400, f"A workout can't be longer than {MAX_WORKOUT_HOURS} hours.")
    with db.connect() as conn:
        require_user(conn, user_id)
        conn.execute(
            "INSERT INTO workouts (user_id, id, start_ms, end_ms, start_tz_min, end_tz_min, source, type) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id, id) DO UPDATE SET start_ms = excluded.start_ms, "
            "end_ms = excluded.end_ms, start_tz_min = excluded.start_tz_min, end_tz_min = excluded.end_tz_min, "
            "source = excluded.source, type = excluded.type",
            (user_id, w.id, w.start_ms, w.end_ms, w.start_tz_min, w.end_tz_min, w.source, w.type),
        )
        return _out(_get(conn, user_id, w.id))


@router.get("", response_model=list[Workout])
def list_workouts(user_id: str, days: int = Query(28, ge=1, le=366)):
    """Workouts that started in the last N days, oldest first."""
    since = int(time.time() * 1000) - days * 86400 * 1000
    with db.connect() as conn:
        require_user(conn, user_id)
        rows = conn.execute(
            "SELECT * FROM workouts WHERE user_id = ? AND start_ms >= ? ORDER BY start_ms", (user_id, since)
        ).fetchall()
    return [_out(r) for r in rows]


@router.get("/{workout_id}", response_model=Workout)
def get_workout(user_id: str, workout_id: str):
    with db.connect() as conn:
        require_user(conn, user_id)
        return _out(_get(conn, user_id, workout_id))


@router.put("/{workout_id}/rating", response_model=Workout)
def rate_workout(user_id: str, workout_id: str, rating: RatingIn):
    """The after-workout check-in. Rating again replaces the earlier answer."""
    if not db.valid_time(rating.answered_at_ms):
        raise HTTPException(400, "The rating is dated before 2000 or in the future. Check the phone's clock.")
    with db.connect() as conn:
        require_user(conn, user_id)
        _get(conn, user_id, workout_id)
        conn.execute(
            "UPDATE workouts SET effort = ?, satisfaction = ?, rated_at_ms = ? WHERE user_id = ? AND id = ?",
            (rating.effort, rating.satisfaction, rating.answered_at_ms, user_id, workout_id),
        )
        return _out(_get(conn, user_id, workout_id))
