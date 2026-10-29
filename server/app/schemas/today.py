from pydantic import BaseModel, StrictBool

from app.schemas.common import Cutoffs, MetricRow, Readiness, SleepBlock


class Hydration(BaseModel):
    """Today's "Yesterday's run" panel: the workout behind the advice, and the advice itself."""

    title: str  # "Yesterday's run", "This morning's workouts"
    fluid_ml: float
    sodium_mg: float | None
    duration_min: float
    line: str


class Today(BaseModel):
    user_id: str
    now_local: str
    update_time: str
    next_update: str
    updated_at: str | None
    can_update_now: bool
    readiness_method: str
    cutoffs: Cutoffs
    night_date: str | None
    is_last_night: bool
    message: str | None
    readiness: Readiness | None
    metrics: list[MetricRow]
    sleep: SleepBlock | None
    quality_notes: str | None
    # Only once there's a night to talk about.
    verdict: str | None = None
    reason: str | None = None
    advice: str | None = None  # also at the end of reason, so older app builds still show it
    text_placeholder: bool | None = None
    name: str | None = None  # for the greeting, None until the person gives one
    helpful: bool | None = None  # their "Was this helpful?" answer for this night, None if not answered
    hydration: Hydration | None = None  # only when a sweaty workout leads into this morning


class FeedbackIn(BaseModel):
    helpful: StrictBool


class Feedback(BaseModel):
    night_date: str
    helpful: bool
