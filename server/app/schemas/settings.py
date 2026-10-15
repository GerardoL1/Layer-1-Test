"""The settings a person can change from Setup and Profile."""

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, field_validator


class Settings(BaseModel):
    timezone: str | None = None
    update_time: str | None = None
    age: int | None = None
    training: str | None = None
    training_days: list[int] | None = None
    units: Literal["metric", "imperial"] | None = None

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError(f"unknown time zone '{v}', use a name like America/Chicago") from None
        return v

    @field_validator("update_time")
    @classmethod
    def clock_time(cls, v):
        if v is not None:
            try:
                h, m = (int(x) for x in v.split(":"))
                assert 0 <= h < 24 and 0 <= m < 60
            except (ValueError, AssertionError):
                raise ValueError("use HH:MM, for example 08:00") from None
            v = f"{h:02d}:{m:02d}"
        return v

    @field_validator("age")
    @classmethod
    def sensible_age(cls, v):
        if v is not None and not 13 <= v <= 100:
            raise ValueError("age must be between 13 and 100")
        return v

    @field_validator("training")
    @classmethod
    def short_text(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("keep training under 100 characters")
        return v

    @field_validator("training_days")
    @classmethod
    def weekdays(cls, v):
        if v is not None:
            if any(d not in range(7) for d in v):
                raise ValueError("training days are weekday numbers, 0 = Monday to 6 = Sunday")
            v = sorted(set(v))
        return v
