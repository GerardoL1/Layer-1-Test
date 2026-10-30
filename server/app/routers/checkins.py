"""
Morning check-ins. They're the labels the readiness model learns from, so each one is tied to the night it
describes: a check-in saved on day D (the person's own clock, as Today uses) belongs to the night of D-1,
and to the score first shown that morning.
"""

import json
import time
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.core import db
from app.core.urls import USER
from app.schemas.checkins import MorningCheckin, MorningCheckinIn
from app.services import processing
from app.services.time_checks import local_time, require_time
from app.services.users import require_user

router = APIRouter(prefix=USER + "/checkins", tags=["checkins"])

# Phone clocks drift a little, so a few minutes ahead is still fine.
CLOCK_SLACK_MS = 10 * 60 * 1000


def _out(conn, user_id: str, night: str) -> dict | None:
    row = conn.execute("SELECT * FROM checkins WHERE user_id = ? AND night_date = ?", (user_id, night)).fetchone()
    if row is None:
        return None
    snap = conn.execute(
        "SELECT score, status, model_version FROM readiness_snapshots WHERE user_id = ? AND night_date = ?",
        (user_id, night),
    ).fetchone()
    return {
        "night_date": row["night_date"],
        "answered_at_ms": row["answered_at_ms"],
        "tz_offset_min": row["tz_offset_min"],
        "survey_version": row["survey_version"],
        "answers": json.loads(row["answers"]),
        "snapshot": dict(snap) if snap else None,
    }


@router.post("/morning", response_model=MorningCheckin)
def save_morning_checkin(user_id: str, checkin: MorningCheckinIn):
    """Saves this morning's answers. A newer answer the same morning replaces an older one."""
    require_time(checkin.answered_at_ms, checkin.tz_offset_min, "The check-in")
    if checkin.answered_at_ms > time.time() * 1000 + CLOCK_SLACK_MS:
        # It would label a night that hasn't been slept yet.
        raise HTTPException(400, "The check-in is dated in the future. Check the phone's clock.")
    with db.connect() as conn:
        user = require_user(conn, user_id)
        # The night comes from when it was answered on the phone, so an answer sent late (offline, or retried
        # after midnight) still lands on the night it describes. Demo people live on a fixed clock instead,
        # which is the night their Today shows.
        if user["clock_local"]:
            answered = processing.local_now(conn, user_id, processing.utc_now())
        else:
            answered = local_time(checkin.answered_at_ms, checkin.tz_offset_min)
        night = (answered.date() - timedelta(days=1)).isoformat()
        conn.execute(
            # A retry of an older answer that arrives late must not replace a newer one.
            "INSERT INTO checkins VALUES (?,?,?,?,?,?) ON CONFLICT(user_id, night_date) DO UPDATE SET "
            "answered_at_ms = excluded.answered_at_ms, tz_offset_min = excluded.tz_offset_min, "
            "survey_version = excluded.survey_version, answers = excluded.answers "
            "WHERE excluded.answered_at_ms >= checkins.answered_at_ms",
            (
                user_id,
                night,
                checkin.answered_at_ms,
                checkin.tz_offset_min,
                checkin.survey_version,
                checkin.answers.model_dump_json(),
            ),
        )
        return _out(conn, user_id, night)


@router.get("/morning", response_model=list[MorningCheckin])
def list_morning_checkins(user_id: str, nights: int = Query(28, ge=1, le=366)):
    """The newest check-ins, oldest first."""
    with db.connect() as conn:
        require_user(conn, user_id)
        dates = [
            r[0]
            for r in conn.execute(
                "SELECT night_date FROM checkins WHERE user_id = ? ORDER BY night_date DESC LIMIT ?", (user_id, nights)
            )
        ]
        return [_out(conn, user_id, d) for d in reversed(dates)]


@router.get("/morning/{night_date}", response_model=MorningCheckin)
def get_morning_checkin(user_id: str, night_date: date):
    with db.connect() as conn:
        require_user(conn, user_id)
        found = _out(conn, user_id, night_date.isoformat())
    if found is None:
        raise HTTPException(404, f"No check-in for the night of {night_date.isoformat()}.")
    return found
