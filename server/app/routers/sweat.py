"""
Sweat data (Layer 3): import a Nix export (preview first, then save), type numbers in by hand,
and read it back for a workout, the Train tab and the Trends chart. The work is in app/services/sweat.py.
"""

import re

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core import limits
from app.core.urls import USER
from app.schemas.sweat import ManualSweatIn, NixPreview, SweatDaily, SweatSession
from app.services import sweat

router = APIRouter(prefix=USER, tags=["sweat"])

DAILY_RANGES = (14, 28, 90)
_TRUE, _FALSE = ("true", "1", "yes", "on"), ("false", "0", "no", "off", "")


def _upload_body(**fields: dict) -> dict:
    """Describes the upload form in openapi.json, since the routes read the form themselves."""
    properties = {
        "file": {"type": "string", "format": "binary", "description": "The .xlsx from Export Workout in Nix"},
        "tz_offset_min": {"type": "integer", "description": "The phone's UTC offset, used only as a last resort"},
        **fields,
    }
    schema = {"type": "object", "required": ["file"], "properties": properties}
    return {"requestBody": {"required": True, "content": {"multipart/form-data": {"schema": schema}}}}


async def _read_upload(request: Request) -> tuple[bytes, dict[str, str]]:
    """
    The file and the text fields. Read by hand so a part without a filename or an oversized field gets a
    plain message, instead of a 422 that echoes the whole file back or Starlette's own wording.
    """
    # Text parts may be as big as the whole upload (already capped by limits.py), so a file sent without a
    # filename arrives as text and gets the "choose the file" message rather than a size error.
    try:
        async with request.form(max_files=1, max_fields=10, max_part_size=limits.MAX_NIX_UPLOAD_BYTES) as form:
            file = form.get("file")
            data = await file.read() if isinstance(file, UploadFile) else None
            fields = {k: v for k, v in form.items() if isinstance(v, str)}
    except StarletteHTTPException:
        raise HTTPException(400, sweat.ERR_BAD_FORM) from None
    if data is None:
        raise HTTPException(400, sweat.ERR_NO_FILE)
    if any(len(v) > sweat.MAX_FORM_FIELD_BYTES for v in fields.values()):
        raise HTTPException(400, sweat.ERR_BAD_FORM)
    return data, fields


def _offset_field(fields: dict[str, str]) -> int | None:
    v = fields.get("tz_offset_min", "").strip()
    if not v:
        return None
    if not re.fullmatch(r"-?\d{1,6}", v):
        raise HTTPException(400, sweat.ERR_BAD_FORM)
    return int(v)


def _bool_field(fields: dict[str, str], name: str) -> bool:
    v = fields.get(name, "").strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise HTTPException(400, sweat.ERR_BAD_FORM)


@router.post("/sweat/nix/preview", response_model=NixPreview, openapi_extra=_upload_body())
async def preview_nix(user_id: str, request: Request):
    """
    Reads a Nix export and says what saving it would do: the numbers, the workout it matches (or nearby
    ones to pick from) and whether it replaces sweat data already saved. Nothing is stored.
    tz_offset_min is the phone's UTC offset, used only when there's no time zone in Settings or readings.
    """
    data, fields = await _read_upload(request)
    return await run_in_threadpool(sweat.preview_nix, user_id, data, _offset_field(fields))


@router.post(
    "/sweat/nix",
    response_model=SweatSession,
    openapi_extra=_upload_body(
        workout_id={"type": "string", "description": "Save to this workout"},
        new_workout={"type": "boolean", "description": "Save as a new workout when nothing matches"},
    ),
)
async def save_nix(user_id: str, request: Request):
    """
    Saves a Nix export, sent again after the preview. It goes to workout_id when given, else to a new
    workout when new_workout is true, else to the workout it overlaps. 409 when more precise sweat data
    for the session is already saved.
    """
    data, fields = await _read_upload(request)
    offset, new_workout = _offset_field(fields), _bool_field(fields, "new_workout")
    workout_id = fields.get("workout_id") or None
    return await run_in_threadpool(sweat.save_nix, user_id, data, offset, workout_id, new_workout)


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
