"""
PLACEHOLDER readiness score: an equal-weight average of the z-scores and its 40 / 70 cut-offs.
Not decided yet, so don't tune these numbers without the team.
"""

import pandas as pd

from app.core.json_values import r1
from app.readiness.model import Confidence, Contribution, ReadinessResult
from app.readiness.usual import METRICS

# +1 means a higher value is better, -1 means higher is worse.
READINESS_SIGNS = {"z_hrv": 1, "z_rhr": -1, "z_tst": 1, "z_eff": 1, "z_frag": -1}
READINESS_CENTER, READINESS_POINTS_PER_SD = 50, 10
LOW_BELOW, READY_FROM = 40, 70

READINESS_METHOD = (
    "Placeholder: 50 + 10 x the average of the available z-scores "
    "(HRV, sleep time and efficiency count up, resting HR and fragmentation count down), "
    "clipped to 0-100. Weights and cut-offs are not decided yet."
)


def readiness(row) -> dict:
    zs = [sign * row[z] for z, sign in READINESS_SIGNS.items() if pd.notna(row.get(z))]
    if not zs:
        # No score: still learning the person's normal, a recorded night that was too short
        # (kept out of the baselines, so there's nothing to compare), or no sleep at all.
        if row.get("usable_sleep"):
            status = "building_baseline"
        elif pd.notna(row.get("tst_min")) and row.get("flag_short_sleep"):
            status = "short_sleep"
        else:
            status = "no_data"
        score = None
    else:
        score = int(round(min(100, max(0, READINESS_CENTER + READINESS_POINTS_PER_SD * sum(zs) / len(zs)))))
        status = "low" if score < LOW_BELOW else "moderate" if score < READY_FROM else "ready"
    return {"score": score, "status": status, "z_count": len(zs), "placeholder": True}


def _confidence(row, z_count: int) -> Confidence | None:
    """Placeholder rule: the more of the five inputs a night has, the more the score can be trusted."""
    if z_count == 0:
        return None
    if pd.isna(row.get("z_hrv")) and pd.isna(row.get("z_rhr")):
        return "sleep_only"
    return "high" if z_count == 5 else "medium" if z_count >= 3 else "low"


def _add_up(raw: list, total: float) -> list[Contribution]:
    """
    Scales the points so they add up to exactly how far the shown score is from 50, after it was clipped
    to 0-100 and rounded. Otherwise "HRV -16" could appear next to a score that only dropped to 0.
    """
    moved = sum(p for *_rest, p in raw)
    scale = total / moved if moved else 0.0
    points = [round(p * scale, 1) for *_rest, p in raw]
    if points:
        # Rounding to one decimal can leave a few tenths over. The biggest input absorbs them.
        biggest = max(range(len(points)), key=lambda i: abs(points[i]))
        points[biggest] = round(points[biggest] + total - sum(points), 1)
    return [Contribution(k, label, value, p + 0.0) for (k, label, value, _), p in zip(raw, points)]


class PlaceholderModel:
    """The formula above behind the ReadinessModel interface, so it can be swapped for the trained model."""

    version = "placeholder-1"
    method = READINESS_METHOD

    def score(self, features: dict) -> ReadinessResult:
        base = readiness(features)
        n = base["z_count"]
        contributions = []
        if base["score"] is not None:
            # Each z-score moves the score by its share of the average.
            raw = []
            for key, col, label, _unit, zcol, _up in METRICS:
                z = features.get(zcol)
                if z is not None and pd.notna(z):
                    raw.append(
                        (key, label, r1(features.get(col)), READINESS_POINTS_PER_SD * READINESS_SIGNS[zcol] * z / n)
                    )
            contributions = _add_up(raw, base["score"] - READINESS_CENTER)
        return ReadinessResult(
            score=base["score"],
            status=base["status"],
            confidence=_confidence(features, n),
            contributions=contributions,
            illness_flag=False,
            model_version=self.version,
            placeholder=True,
            z_count=n,
        )
