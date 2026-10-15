"""
Step 5. Missing data and quality: one row per calendar night, flags and usable_* columns.
"""

from __future__ import annotations

import pandas as pd

from layer1 import config as C
from layer1.metrics import NIGHT_COLUMNS


def flag_quality(nights: pd.DataFrame, first_night=None, last_night=None) -> pd.DataFrame:
    """
    Step 5. Add one row for every calendar night in range (so missing nights are visible),
    quality flags, and three usable_* columns that decide which values feed the baselines.
    """
    if first_night is None and nights.empty:
        return nights
    first = first_night or nights["night_date"].min()
    last = last_night or nights["night_date"].max()
    calendar = pd.DataFrame({"night_date": pd.date_range(first, last, freq="D").date})
    df = calendar.merge(nights, on="night_date", how="left")
    num_cols = [c for c in NIGHT_COLUMNS if c not in ("night_date", "sleep_onset", "final_wake", "tib_source")]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors="coerce")

    has_sleep = df["tst_min"].notna()
    df["flag_no_sleep_data"] = ~has_sleep
    df["flag_short_sleep"] = has_sleep & (df["tst_min"] < C.MIN_TST_FOR_USABLE_MIN)
    df["flag_no_stages"] = (
        has_sleep & (df["unspecified_min"].fillna(0) >= df["tst_min"].fillna(0)) & (df["tst_min"] > 0)
    )
    df["flag_no_hrv"] = has_sleep & (df["hrv_count"].fillna(0) == 0)
    hr_per_hour = df["hr_night_count"] / (df["tst_min"] / 60)
    df["flag_low_hr_coverage"] = has_sleep & (hr_per_hour.fillna(0) < C.MIN_HR_SAMPLES_PER_SLEEP_HOUR)
    df["flag_no_rhr"] = has_sleep & df["rhr_night_bpm"].isna()

    df["usable_sleep"] = has_sleep & ~df["flag_short_sleep"]
    df["usable_hrv"] = df["usable_sleep"] & ~df["flag_no_hrv"]
    df["usable_rhr"] = df["usable_sleep"] & ~df["flag_low_hr_coverage"] & ~df["flag_no_rhr"]

    labels = {
        "flag_no_sleep_data": "no sleep recorded",
        "flag_short_sleep": "short sleep",
        "flag_no_stages": "no sleep stages",
        "flag_no_hrv": "no HRV",
        "flag_low_hr_coverage": "few heart rate readings",
        "flag_no_rhr": "no overnight resting HR",
    }
    df["quality_notes"] = df.apply(lambda r: "; ".join(t for c, t in labels.items() if r[c]), axis=1)
    return df
