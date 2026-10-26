"""Sweat sessions (Layer 3): a Nix import or numbers typed in by hand, one per workout."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.workouts import Workout

Source = Literal["nix", "manual"]
UnitSystem = Literal["metric", "customary", "manual"]
# What saving this preview would do to sweat data the workout already has.
Existing = Literal["none", "same", "replaces", "replaces_less_precise", "keeps_more_precise"]


class SweatSession(BaseModel):
    id: str
    workout_id: str | None  # None only in a preview that matched no workout
    source: Source
    start_ms: int
    end_ms: int
    start_tz_min: int
    end_tz_min: int
    start_local: str
    end_local: str
    duration_min: float
    fluid_loss_ml: float  # Nix's total, which includes breathing loss
    sweat_rate_l_h: float | None
    sodium_mg: float | None  # None when Nix picked up no sweat, never 0
    sodium_rate_mg_h: float | None
    electrolytes_mg: float | None
    electrolyte_rate_mg_h: float | None
    sweat_composition_mg_l: float | None
    nix_index: float | None
    workout_type: str | None
    sweat_detected: bool
    unit_system: UnitSystem
    warnings: list[str]
    imported_at_ms: int | None  # None in a preview, nothing is saved yet
    fluid_loss_pct_body_weight: float | None  # only with sweat detected and a weight in Settings


class NixPreview(BaseModel):
    session: SweatSession
    matched_workout: Workout | None
    nearby_workouts: list[Workout]  # closest first, to pick from when nothing matched
    existing: Existing
    weight_suggestion_kg: float | None  # from the file, only when Settings has no weight


# Typed-in numbers, in the stored units. The app converts from the person's Units setting before sending.
Millilitres = Annotated[float, Field(strict=True, ge=0, le=30_000)]
Milligrams = Annotated[float, Field(strict=True, ge=0, le=100_000)]
LitresPerHour = Annotated[float, Field(strict=True, ge=0, le=10)]


class ManualSweatIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    fluid_loss_ml: Millilitres
    sodium_mg: Milligrams | None = None
    sweat_rate_l_h: LitresPerHour | None = None


class SweatDay(BaseModel):
    date: str
    fluid_loss_ml: float | None  # None on days without sweat data, never 0
    sodium_mg: float | None
    sessions: int
    has_sweat_data: bool


class SweatDaily(BaseModel):
    nights: int
    days: list[SweatDay]  # oldest first, ending yesterday
    summary: str
    placeholder: bool  # the summary wording is a placeholder until the LLM writes it
