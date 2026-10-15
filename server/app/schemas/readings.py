"""What our iPhone app sends to POST /upload."""

from pydantic import BaseModel


class Sample(BaseModel):
    uuid: str
    metric: str
    value: float
    start_ms: int
    end_ms: int
    tz_offset_min: int | None = None  # minutes ahead of UTC when the reading was taken
    source: str | None = None
    unit: str | None = None  # ignored, each metric has one fixed unit


class SleepStage(BaseModel):
    uuid: str
    stage: str  # in_bed, awake, core, deep, rem, asleep_unspecified
    start_ms: int
    end_ms: int
    start_tz_min: int | None = None
    end_tz_min: int | None = None
    source: str | None = None


class Upload(BaseModel):
    user_id: str
    samples: list[Sample] = []
    sleep: list[SleepStage] = []
