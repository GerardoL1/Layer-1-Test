"""The morning check-in, as designed in Figma (Check-in v2). Every scale is 1 to 10 and 10 is always the good end."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictInt, field_validator

# Strict, so true, "7" and 7.0 aren't quietly turned into answers.
Scale = Annotated[StrictInt, Field(ge=1, le=10)]
# The 14 groups on the body map, front then back.
MuscleGroup = Literal[
    "shoulders",
    "chest",
    "biceps",
    "forearms",
    "abs",
    "quads",
    "shins",
    "traps",
    "lats",
    "triceps",
    "lower_back",
    "glutes",
    "hamstrings",
    "calves",
]
Unusual = Literal["alcohol", "feeling_sick", "late_caffeine", "travel", "poor_diet"]
Rehydrated = Literal["not_really", "somewhat", "fully"]


class MorningAnswers(BaseModel):
    ready_to_train: Scale  # the main training label, so it's the one answer that's required
    sleep_quality: Scale | None = None
    fatigue: Scale | None = None
    energy: Scale | None = None
    stress: Scale | None = None
    motivation: Scale | None = None
    hydration: Scale | None = None
    soreness: Scale | None = None
    # For both lists, [] means "none" was picked and null means the question wasn't answered.
    sore_muscles: list[MuscleGroup] | None = Field(None, max_length=14)
    unusual: list[Unusual] | None = Field(None, max_length=5)
    # Only asked when there was a workout yesterday.
    rehydrated: Rehydrated | None = None

    @field_validator("sore_muscles", "unusual", mode="before")
    @classmethod
    def once_each(cls, v):
        return list(dict.fromkeys(v)) if isinstance(v, list) else v


class MorningCheckinIn(BaseModel):
    answered_at_ms: StrictInt
    tz_offset_min: StrictInt
    survey_version: str = Field("v2", min_length=1, max_length=20)
    answers: MorningAnswers


class SnapshotRef(BaseModel):
    """The score that was first shown for the same night, the one this answer labels."""

    score: int | None
    status: str
    model_version: str


class MorningCheckin(BaseModel):
    night_date: str
    answered_at_ms: int
    tz_offset_min: int
    survey_version: str
    answers: MorningAnswers
    snapshot: SnapshotRef | None
