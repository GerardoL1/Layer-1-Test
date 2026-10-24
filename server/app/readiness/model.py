"""
The readiness model interface. Today's placeholder formula is one model, and the team's trained model
will be another. Routers only call get_model(), so a new model drops in without touching them or the app.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

# "sleep_only" means there was no HRV or resting HR to go on that night.
Confidence = Literal["high", "medium", "low", "sleep_only"]


@dataclass
class Contribution:
    """
    How far one input moved the score, in points. The explanation may only talk about these,
    so every reason it gives can be traced back to a number.
    input is the Last night row key (hrv, rhr, sleep, efficiency, fragmentation) when there is one.
    """

    input: str
    label: str
    value: float | None
    points: float


@dataclass
class ReadinessResult:
    score: int | None
    status: str
    confidence: Confidence | None
    contributions: list[Contribution] = field(default_factory=list)
    illness_flag: bool = False
    model_version: str = ""
    placeholder: bool = True
    z_count: int = 0  # how many z-scores went in, kept because the app's API already has it

    def to_api(self, with_contributions: bool = True) -> dict:
        out = asdict(self)
        if not with_contributions:
            del out["contributions"]
        return out


class ReadinessModel(Protocol):
    version: str
    # One plain sentence on how the score is worked out, shown in the API as readiness_method.
    method: str

    def score(self, features: dict) -> ReadinessResult: ...


def get_model() -> ReadinessModel:
    """
    The model in use, picked by the READINESS_MODEL setting. Only the placeholder exists for now.
    A trained model gets its own name here once the team hands it over.
    """
    from app.readiness.scoring import PlaceholderModel

    name = os.environ.get("READINESS_MODEL", "placeholder")
    if name == "placeholder":
        return PlaceholderModel()
    raise ValueError(f"Unknown READINESS_MODEL '{name}'. The only one so far is 'placeholder'.")
