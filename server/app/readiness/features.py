"""
One night's inputs for the readiness model, built from the person's nights up to and including that night.
Nothing after it is used, so a score only ever depends on what was known that morning.

Derived history features (HRV 7-night trend, sleep debt, poor nights in a row) belong here once the team
defines them. That's why this takes the whole history and not just one row.
"""

import pandas as pd

from app.core.json_values import clean

# Inputs from docs/ml_llm_plan.md, plus the fields the placeholder needs to pick a no-score status.
FEATURE_COLUMNS = [
    # core values and their z-scores
    "hrv_night_ms",
    "hrv_ln",
    "z_hrv",
    "rhr_night_bpm",
    "z_rhr",
    "tst_min",
    "z_tst",
    "sleep_efficiency_pct",
    "z_eff",
    "fragmentation_per_hr",
    "z_frag",
    # lower weight
    "waso_min",
    "sleep_latency_min",
    "naps",
    # data quality
    "usable_sleep",
    "usable_hrv",
    "usable_rhr",
    "flag_short_sleep",
    "flag_no_hrv",
    "flag_low_hr_coverage",
    "flag_no_stages",
    "hrv_count",
    "hr_slot_count",
    # baseline sizes
    "hrv_ln_base_n",
    "rhr_night_bpm_base_n",
    "tst_min_base_n",
    "sleep_efficiency_pct_base_n",
    "fragmentation_per_hr_base_n",
]


def build_features(history: pd.DataFrame) -> dict:
    """The inputs for the last night in history, as plain JSON values (missing is None, never 0)."""
    row = history.iloc[-1]
    return {col: clean(row.get(col)) for col in FEATURE_COLUMNS}
