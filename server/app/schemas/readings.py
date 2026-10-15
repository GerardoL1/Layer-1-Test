"""What our iPhone app sends with a batch of readings."""

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


class ReadingsBatch(BaseModel):
    # The user is in the URL. Older app builds also put it here, which is fine if it matches.
    user_id: str | None = None
    samples: list[Sample] = []
    sleep: list[SleepStage] = []


class Upload(ReadingsBatch):
    """The old POST /upload body, where the user id had to be in the body."""

    user_id: str
