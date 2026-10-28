"""The same date and time zone rules as the readings routes, for check-ins and workouts."""

from datetime import datetime, timedelta

from fastapi import HTTPException

from app.core import db


def require_time(ms: int, offset_min: int, what: str) -> None:
    if not db.valid_offset(offset_min):
        raise HTTPException(400, f"{what} has an impossible UTC offset: {offset_min} minutes.")
    if not db.valid_time(ms):
        raise HTTPException(400, f"{what} is dated before 2000 or in the future. Check the phone's clock.")


def utc_ms(dt: datetime, offset: timedelta, shown: str) -> tuple[int, int]:
    """UTC milliseconds and the offset in minutes for a parsed import date. Bad dates raise ValueError."""
    minutes = int(offset.total_seconds() // 60)
    if not db.valid_offset(minutes):
        raise ValueError(f"impossible UTC offset: {shown}")
    try:
        ms = int(dt.timestamp() * 1000)
    except OverflowError:  # year 1 with a positive offset falls before year 1 in UTC
        raise ValueError(f"date out of range: {shown}") from None
    if not db.valid_time(ms):
        raise ValueError(f"date out of range: {shown}")
    return ms, minutes


def local_time(ms: int, offset_min: int) -> datetime:
    """The person's wall-clock time for a UTC moment."""
    return datetime(1970, 1, 1) + timedelta(milliseconds=ms, minutes=offset_min)
