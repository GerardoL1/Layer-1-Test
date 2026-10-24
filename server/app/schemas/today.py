from pydantic import BaseModel

from app.schemas.common import Cutoffs, MetricRow, Readiness, SleepBlock


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
