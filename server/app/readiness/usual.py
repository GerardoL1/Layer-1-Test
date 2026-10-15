"""
PLACEHOLDER "usual range" (baseline mean plus or minus 1 SD) and the Worse / Usual / Better
label, plus the metric rows Today and Profile show.
"""

import math

import pandas as pd

from app.core.json_values import clean, r1

USUAL_RANGE_SD = 1.0

# The metric rows shown on Today and Profile, in order.
METRICS = [
    # key, column, label, unit, z column, higher is better?
    ("hrv", "hrv_night_ms", "Heart rate variability", "ms", "z_hrv", True),
    ("rhr", "rhr_night_bpm", "Resting heart rate", "bpm", "z_rhr", False),
    ("sleep", "tst_min", "Total sleep", "min", "z_tst", True),
    ("efficiency", "sleep_efficiency_pct", "Sleep efficiency", "%", "z_eff", True),
    ("fragmentation", "fragmentation_per_hr", "Awakenings per hour", "/h", "z_frag", False),
]
# Baselines are kept on these columns. HRV's is on the log scale.
BASE_COLUMN = {"hrv_night_ms": "hrv_ln"}


def usual_range(row, col) -> tuple:
    base = BASE_COLUMN.get(col, col)
    mu, sd = row.get(f"{base}_base_mean"), row.get(f"{base}_base_sd")
    if pd.isna(mu) or pd.isna(sd):
        return None, None
    lo, hi = mu - USUAL_RANGE_SD * sd, mu + USUAL_RANGE_SD * sd
    if base != col:  # back from the log scale
        lo, hi = math.exp(lo), math.exp(hi)
    return r1(lo), r1(hi)


def usual_mean(row, col):
    """The middle of the usual range, for changes like "-18%". HRV's is the geometric mean."""
    base = BASE_COLUMN.get(col, col)
    mu = row.get(f"{base}_base_mean")
    if pd.isna(mu):
        return None
    return r1(math.exp(mu) if base != col else mu)


def direction(z, higher_is_better) -> str | None:
    if pd.isna(z):
        return None
    good = z if higher_is_better else -z
    return "better" if good > USUAL_RANGE_SD else "worse" if good < -USUAL_RANGE_SD else "usual"


def metric_rows(row) -> list:
    out = []
    for key, col, label, unit, zcol, up in METRICS:
        lo, hi = usual_range(row, col)
        out.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "value": r1(row.get(col)),
                "z": r1(row.get(zcol)),
                "usual_low": lo,
                "usual_high": hi,
                "usual_mean": usual_mean(row, col),
                "direction": direction(row.get(zcol), up),
                "placeholder": True,
            }
        )
    # The count people understand. Its Worse / Usual / Better comes from the per-hour z-score,
    # since that's the measure the baseline is kept on (no usual range for the count itself).
    out.append(
        {
            "key": "awakenings",
            "label": "Awakenings",
            "unit": "",
            "value": clean(row.get("awakenings")),
            "z": r1(row.get("z_frag")),
            "usual_low": None,
            "usual_high": None,
            "usual_mean": None,
            "direction": direction(row.get("z_frag"), False),
            "placeholder": True,
        }
    )
    return out
