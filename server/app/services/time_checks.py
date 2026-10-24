"""The same date and time zone rules as the readings routes, for check-ins and workouts."""

from datetime import datetime, timedelta

from fastapi import HTTPException

from app.core import db


def require_time(ms: int, offset_min: int, what: str) -> None:
    if not db.valid_offset(offset_min):
        raise HTTPException(400, f"{what} has an impossible UTC offset: {offset_min} minutes.")
    if not db.valid_time(ms):
        raise HTTPException(400, f"{what} is dated before 2000 or in the future. Check the phone's clock.")


def local_time(ms: int, offset_min: int) -> datetime:
    """The person's wall-clock time for a UTC moment."""
    return datetime(1970, 1, 1) + timedelta(milliseconds=ms, minutes=offset_min)
