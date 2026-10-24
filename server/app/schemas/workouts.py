"""Workouts and their after-workout check-in (effort and satisfaction, both 1 to 10)."""

import re
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, field_validator

from app.schemas.checkins import Scale

Source = Literal["manual", "apple_health", "patch"]


# The id goes in URLs, so no slashes, control characters, blank ids or "." and "..".
_BAD_ID = re.compile(r"[/\\\x00-\x1f\x7f]|^\s|\s$|^\.{1,2}$")


class WorkoutIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)  # made by the sender, so a repeat send updates the same workout
    start_ms: StrictInt
    end_ms: StrictInt
    start_tz_min: StrictInt
    end_tz_min: StrictInt
    source: Source = "manual"
    type: str = Field(min_length=1, max_length=40)  # like "Leg day" or "Run"

    @field_validator("id")
    @classmethod
    def url_safe(cls, v):
        if _BAD_ID.search(v):
            raise ValueError("use an id without slashes, control characters or leading and trailing spaces")
        return v

    @field_validator("type")
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("type can't be blank")
        return v.strip()


class RatingIn(BaseModel):
    effort: Scale
    satisfaction: Scale | None = None
    answered_at_ms: StrictInt


class Workout(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    start_tz_min: int
    end_tz_min: int
    start_local: str
    end_local: str
    source: Source
    type: str
    duration_min: float
    effort: int | None
    satisfaction: int | None
    rated_at_ms: int | None
    load: float | None  # effort times minutes, once it's been rated
