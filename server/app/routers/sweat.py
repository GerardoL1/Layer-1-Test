"""
Sweat data (Layer 3): import a Nix export (preview first, then save), type numbers in by hand,
and read it back for a workout, the Train tab and the Trends chart. The work is in app/services/sweat.py.
"""

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.core.urls import USER
from app.schemas.sweat import ManualSweatIn, NixPreview, SweatDaily, SweatSession
from app.services import sweat

router = APIRouter(prefix=USER, tags=["sweat"])

DAILY_RANGES = (14, 28, 90)


@router.post("/sweat/nix/preview", response_model=NixPreview)
def preview_nix(user_id: str, file: UploadFile = File(...), tz_offset_min: int | None = Form(None)):
    """
    Reads a Nix export and says what saving it would do: the numbers, the workout it matches (or nearby
    ones to pick from) and whether it replaces sweat data already saved. Nothing is stored.
    tz_offset_min is the phone's UTC offset, used only when there's no time zone in Settings or readings.
    """
    return sweat.preview_nix(user_id, file.file.read(), tz_offset_min)


@router.post("/sweat/nix", response_model=SweatSession)
def save_nix(
    user_id: str,
    file: UploadFile = File(...),
    tz_offset_min: int | None = Form(None),
    workout_id: str | None = Form(None),
    new_workout: bool = Form(False),
):
    """
    Saves a Nix export, sent again after the preview. It goes to workout_id when given, else to a new
    workout when new_workout is true, else to the workout it overlaps. 409 when the workout already has
    more precise sweat data.
    """
    return sweat.save_nix(user_id, file.file.read(), tz_offset_min, workout_id, new_workout)


@router.put("/workouts/{workout_id}/sweat", response_model=SweatSession)
def save_manual(user_id: str, workout_id: str, body: ManualSweatIn):
    """Numbers typed in from any sweat sensor, in ml, mg and L/h. 409 if the workout has Nix data."""
    return sweat.save_manual(user_id, workout_id, body.fluid_loss_ml, body.sodium_mg, body.sweat_rate_l_h)


@router.get("/workouts/{workout_id}/sweat", response_model=SweatSession)
def get_workout_sweat(user_id: str, workout_id: str):
    return sweat.for_workout(user_id, workout_id)


@router.get("/sweat/sessions", response_model=list[SweatSession])
def list_sessions(user_id: str, days: int = Query(28, ge=1, le=3650)):
    """Sweat sessions of workouts that started in the last N days, oldest first."""
    return sweat.list_sessions(user_id, days)


@router.get("/sweat/daily", response_model=SweatDaily)
def daily(user_id: str, nights: int = 14):
    """Sweat per day for the Trends chart over the last 14, 28 or 90 days, plus a one-line summary."""
    if nights not in DAILY_RANGES:
        raise HTTPException(422, f"nights must be one of {', '.join(map(str, DAILY_RANGES))}")
    return sweat.daily(user_id, nights)
