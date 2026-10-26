"""
Demo sweat data (temporary, testing only, like the Layer 1 demo). Gives a demo person a few weeks of
workouts before the demo clock (1 Oct 2026, 8:30 am), with Nix imports built from the fake export
layout (sweat, no sweat, Customary) and one typed-in session, so the Train screens can be shown
without a sensor. It goes through the same code as a real import.
"""

from datetime import datetime, timedelta
from typing import NamedTuple

from fastapi import HTTPException

from app.core import db
from app.routers.workouts import save_workout
from app.schemas.workouts import Source, WorkoutIn
from app.services import sweat
from layer3.samples import NNBSP, Truth, nix_export

ERR_LOAD_FIRST = "Load the demo person first, then their sweat data."
LAG_MIN = 15  # Nix only picks up sweat after about 15 minutes
BREATHING_ML_H = 30.0


class Nix(NamedTuple):
    sweat_ml_h: float  # equal to breathing (30) means Nix picked up no sweat
    sodium_mg_h: float
    units: str


class Typed(NamedTuple):
    fluid_ml: float
    sodium_mg: float


class DemoWorkout(NamedTuple):
    id: str
    start: datetime  # local
    minutes: int
    type: str
    source: Source
    sweat: Nix | Typed | None


WORKOUTS = [
    DemoWorkout(
        "demo-run-0930", datetime(2026, 9, 30, 18, 5), 35, "Easy run", "apple_health", Nix(1500, 900, "metric")
    ),
    DemoWorkout(
        "demo-legs-0929", datetime(2026, 9, 29, 18, 10), 58, "Leg day", "apple_health", Nix(1450, 1100, "metric")
    ),
    DemoWorkout(
        "demo-upper-0927", datetime(2026, 9, 27, 10, 20), 52, "Upper body", "apple_health", Nix(30, 0, "customary")
    ),
    DemoWorkout("demo-legs-0925", datetime(2026, 9, 25, 18, 30), 61, "Leg day", "patch", Typed(640, 410)),
    DemoWorkout("demo-run-0923", datetime(2026, 9, 23, 7, 0), 32, "Easy run", "apple_health", None),
    DemoWorkout(
        "demo-long-0920", datetime(2026, 9, 20, 9, 45), 74, "Long run", "apple_health", Nix(1400, 800, "metric")
    ),
    DemoWorkout("demo-upper-0915", datetime(2026, 9, 15, 18, 5), 48, "Upper body", "apple_health", None),
]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _nix_time(t: datetime) -> str:
    """The way Nix writes it: "Sep 30, 2026 at 6:05 PM"."""
    hour = t.hour % 12 or 12
    return f"{MONTHS[t.month - 1]} {t.day}, {t.year} at {hour}:{t.minute:02d}{NNBSP}{'PM' if t.hour >= 12 else 'AM'}"


def nix_file(start: datetime, minutes: int, type_: str, sweat_ml_h: float, sodium_mg_h: float, units: str) -> bytes:
    sweaty = sweat_ml_h > BREATHING_ML_H
    lag = min(LAG_MIN, minutes) if sweaty else minutes
    truth = Truth(
        start=_nix_time(start),
        end=_nix_time(start + timedelta(minutes=minutes)),
        duration=f"{minutes // 60:02d}:{minutes % 60:02d}:00",
        minutes=minutes,
        workout_type=type_,
        nix_index=70,
        respiration_ml_h=[BREATHING_ML_H] * minutes,
        sweat_ml_h=[BREATHING_ML_H] * lag + [sweat_ml_h] * (minutes - lag),
        sodium_mg_h=[0.0] * lag + [sodium_mg_h] * (minutes - lag),
        electrolyte_mg_h=[0.0] * lag + [sodium_mg_h * 1.4] * (minutes - lag),
        weight_kg=70,
        weight_lb=154,
        height_cm=178,
        height_ft="5' 10\"",
    )
    return nix_export(truth, units)


def load(person: str) -> dict:
    """Replaces the demo person's demo workouts and all their sweat data. Reloading starts them fresh."""
    user_id = f"demo-{person}"
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone() is None:
            raise HTTPException(404, ERR_LOAD_FIRST)
        conn.execute("DELETE FROM sweat_minutes WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM sweat_sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM workouts WHERE user_id = ? AND id LIKE 'demo-%'", (user_id,))
        # The demo person's readings say which offset they live in (no time zone setting).
        offsets = {w.id: sweat._offsets(conn, user_id, w.start, None)[0] for w in WORKOUTS}
    sessions = 0
    for wid, start, minutes, type_, source, data in WORKOUTS:
        start_ms = sweat._utc_ms(start, offsets[wid])
        save_workout(
            user_id,
            WorkoutIn(
                id=wid,
                start_ms=start_ms,
                end_ms=start_ms + minutes * 60000,
                start_tz_min=offsets[wid],
                end_tz_min=offsets[wid],
                source=source,
                type=type_,
            ),
        )
        if isinstance(data, Nix):
            file = nix_file(start, minutes, type_, data.sweat_ml_h, data.sodium_mg_h, data.units)
            sweat.save_nix(user_id, file, None, wid, False)
        elif isinstance(data, Typed):
            sweat.save_manual(user_id, wid, data.fluid_ml, data.sodium_mg, None)
        else:
            continue
        sessions += 1
    return {"user_id": user_id, "workouts": len(WORKOUTS), "sweat_sessions": sessions}
