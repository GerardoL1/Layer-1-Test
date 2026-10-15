from pydantic import BaseModel

from app.schemas.common import Cutoffs, Readiness


class TrendValue(BaseModel):
    value: float | None
    z: float | None
    usual_low: float | None
    usual_high: float | None


class TrendRow(BaseModel):
    night_date: str
    readiness: Readiness
    usable_sleep: bool
    quality_notes: str | None
    deep_min: float | None
    core_min: float | None
    rem_min: float | None
    unspecified_min: float | None
    hrv: TrendValue
    rhr: TrendValue
    sleep: TrendValue
    efficiency: TrendValue
    fragmentation: TrendValue


class Trends(BaseModel):
    user_id: str
    nights: int
    # These three are missing when there are no nights yet.
    cutoffs: Cutoffs | None = None
    placeholder: bool | None = None
    rows: list[TrendRow]
    summaries: dict[str, str | None] | None = None
