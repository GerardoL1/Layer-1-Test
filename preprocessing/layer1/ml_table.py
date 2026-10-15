"""
Step 7. ML-ready table: fixed columns, rounded, with a column dictionary.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from layer1 import config as C

ML_COLUMNS = {
    # identity
    "person_id": "Tester / user the night belongs to",
    "night_date": "Date of the evening the night started (YYYY-MM-DD)",
    "weekday": "Day of week of night_date (0 = Monday)",
    # sleep architecture
    "tst_min": "Total sleep time: core + deep + REM (+ unspecified) minutes",
    "core_min": "Core sleep minutes",
    "deep_min": "Deep sleep minutes",
    "rem_min": "REM sleep minutes",
    "waso_min": "Awake minutes after sleep onset, before final awakening",
    "awakenings": f"Awake stretches of at least {C.MIN_AWAKENING_MIN:g} min inside the sleep window",
    "tib_min": "Time in bed (iPhone In Bed if available, else onset to final awakening)",
    "tib_source": "Where time in bed came from: iphone_in_bed or sleep_window",
    "sleep_efficiency_pct": "TST / time in bed x 100",
    "fragmentation_per_hr": "Awakenings per hour of sleep",
    "waso_pct_of_tib": "Original spec fragmentation: WASO / time in bed x 100 (kept for reference)",
    "sleep_onset_hour": "Local clock time of sleep onset in hours (23.5 = 11:30 pm, 25.0 = 1 am)",
    # vitals
    "hrv_night_ms": "Mean SDNN (ms) of HRV readings inside the sleep window",
    "hrv_ln": "Natural log of hrv_night_ms",
    "hrv_count": "Number of HRV readings that night",
    "rhr_night_bpm": f"Lowest {C.RHR_WINDOW_MIN}-min average heart rate during sleep",
    "apple_rhr_bpm": "Apple's own resting heart rate for the wake-up day (for comparison)",
    # personal baselines
    **{
        z: f"z-score of {label} vs previous {C.BASELINE_WINDOW_NIGHTS} nights (needs {C.BASELINE_MIN_NIGHTS})"
        for _, (z, label, _g) in C.ZSCORE_METRICS.items()
    },
    "hrv_ln_base_n": "Nights in the HRV baseline",
    "rhr_night_bpm_base_n": "Nights in the resting HR baseline",
    # quality
    "usable_sleep": "Night has enough sleep data to use",
    "usable_hrv": "HRV value usable",
    "usable_rhr": "Overnight resting HR usable",
    "quality_notes": "Why a night is incomplete (empty when complete)",
    # label placeholder
    "readiness_label": "EMPTY placeholder for the training label (e.g. morning readiness rating)",
}


def build_ml_table(nights: pd.DataFrame, person_id: str) -> pd.DataFrame:
    """Step 7. Final table, fixed column order, rounded. Nights with no sleep data are kept (flagged)."""
    df = nights.copy()
    df["person_id"] = person_id
    df["weekday"] = pd.to_datetime(df["night_date"]).dt.weekday
    onset = pd.to_datetime(df["sleep_onset"])
    hours = onset.dt.hour + onset.dt.minute / 60
    df["sleep_onset_hour"] = np.where(hours < C.NIGHT_SHIFT_HOURS, hours + 24, hours)
    df.loc[onset.isna(), "sleep_onset_hour"] = np.nan
    df["readiness_label"] = np.nan
    df = df[list(ML_COLUMNS)].copy()
    df["night_date"] = df["night_date"].astype(str)
    for col in ("awakenings", "hrv_count", "hrv_ln_base_n", "rhr_night_bpm_base_n"):
        df[col] = df[col].astype("Int64")  # whole numbers that may be missing
    for col in ("usable_sleep", "usable_hrv", "usable_rhr"):
        df[col] = df[col].fillna(False).astype(bool)
    num = df.select_dtypes("float").columns
    df[num] = df[num].round(3)
    return df.reset_index(drop=True)


def column_dictionary() -> pd.DataFrame:
    return pd.DataFrame({"column": list(ML_COLUMNS), "meaning": list(ML_COLUMNS.values())})
