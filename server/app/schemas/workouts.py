"""Workouts and their after-workout check-in (effort and satisfaction, both 1 to 10)."""

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.checkins import Scale

Source = Literal["manual", "apple_health", "patch"]


class WorkoutIn(BaseModel):
    id: str = Field(min_length=1, max_length=100)  # made by the sender, so a repeat send updates the same workout
    start_ms: int
    end_ms: int
    start_tz_min: int
    end_tz_min: int
    source: Source = "manual"
    type: str = Field(min_length=1, max_length=40)  # like "Leg day" or "Run"


class RatingIn(BaseModel):
    effort: Scale
    satisfaction: Scale | None = None
    answered_at_ms: int


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
