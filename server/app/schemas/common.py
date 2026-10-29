"""Pieces shared by several responses: the readiness block, metric rows and sleep."""

from typing import Literal

from pydantic import BaseModel

ReadinessStatus = Literal["low", "moderate", "ready", "building_baseline", "short_sleep", "no_data"]
Direction = Literal["better", "usual", "worse"]
Confidence = Literal["high", "medium", "low", "sleep_only"]


class Contribution(BaseModel):
    """How far one input moved the score, in points. input is the Last night row key when there is one."""

    input: str
    label: str
    value: float | None
    points: float


class Readiness(BaseModel):
    score: int | None
    status: ReadinessStatus
    z_count: int
    placeholder: bool
    # Added for the readiness model. Today has all four, Trends leaves out contributions.
    confidence: Confidence | None = None
    confidence_reason: str | None = None  # the line under Today's band, None when confidence is high
    contributions: list[Contribution] | None = None
    illness_flag: bool | None = None
    model_version: str | None = None


class Cutoffs(BaseModel):
    low_below: int
    ready_from: int
    placeholder: bool | None = None  # only Today says this


class MetricRow(BaseModel):
    """One row of "Last night vs your usual"."""

    key: str
    label: str
    unit: str
    value: float | None
    z: float | None
    usual_low: float | None
    usual_high: float | None
    usual_mean: float | None
    direction: Direction | None
    placeholder: bool


class SleepBlock(BaseModel):
    onset: str | None
    wake: str | None
    total_min: float | None
    deep_min: float | None
    core_min: float | None
    rem_min: float | None
    unspecified_min: float | None
    awake_min: float | None
    in_bed_min: float | None
    efficiency_pct: float | None
