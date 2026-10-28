"""What our iPhone app sends with a batch of readings."""

from pydantic import BaseModel, FiniteFloat


class Sample(BaseModel):
    uuid: str
    metric: str
    value: FiniteFloat  # no NaN or Infinity
    start_ms: int
    end_ms: int
    tz_offset_min: int | None = None  # minutes ahead of UTC when the reading was taken
    source: str | None = None
    unit: str | None = None  # converted to bpm or ms, left out means it already is


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


class ReadingsResult(BaseModel):
    received: int
    new: int  # the rest were repeats


class HealthAutoExportResult(BaseModel):
    samples: int
    sleep_stages: int
    new: int
    unreadable: int  # rows that couldn't be read
    ignored_metrics: list[str]  # things we don't use, like steps
    notes: list[str] = []  # what to change in Health Auto Export, when something can't be used
