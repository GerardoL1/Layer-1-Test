from typing import Literal

from pydantic import BaseModel


class ImportJob(BaseModel):
    """Where an Apple Health export import is up to."""

    import_id: str
    state: Literal["queued", "running", "processing", "done", "error"]
    user_id: str
    counts: dict[str, int]  # heart_rate, resting_heart_rate, hrv_sdnn, sleep_stages, skipped, new
    error: str | None
    file_name: str
    file_bytes: int
    read_fraction: float  # how far through export.xml the reader is, 0 to 1
    reading: str | None  # what kind of record it's on, e.g. "sleep"
    nights_ready: int | None
