"""
Step 4. Nightly metrics: TST, efficiency, fragmentation, overnight HRV and resting HR.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from layer1 import config as C


def _clip_minutes(df: pd.DataFrame, lo, hi) -> pd.Series:
    """Minutes of each row that fall inside [lo, hi]."""
    s = df["start_utc"].clip(lower=lo, upper=hi)
    e = df["end_utc"].clip(lower=lo, upper=hi)
    return (e - s).dt.total_seconds() / 60


def count_awakenings(awake: pd.DataFrame, lo, hi) -> tuple[int, float]:
    """Awake pieces inside the window, with touching pieces merged. Returns (count, total minutes)."""
    a = awake[(awake["end_utc"] > lo) & (awake["start_utc"] < hi)].sort_values("start_utc")
    bouts: list[list[pd.Timestamp]] = []
    for s, e in zip(a["start_utc"].clip(lower=lo), a["end_utc"].clip(upper=hi)):
        # Only pieces that touch or overlap merge. Sleep between two awake pieces stays sleep.
        if bouts and s <= bouts[-1][1]:
            bouts[-1][1] = max(bouts[-1][1], e)
        else:
            bouts.append([s, e])
    lengths = [(e - s).total_seconds() / 60 for s, e in bouts]
    return sum(1 for m in lengths if m >= C.MIN_AWAKENING_MIN), float(sum(lengths))


def overnight_rhr(hr: pd.DataFrame, lo, hi) -> dict:
    """
    Lowest RHR_WINDOW_MIN-minute rolling average of heart rate during sleep.
    Returns the value, where it happened, and the rolling series (for charts).
    """
    w = hr[(hr["start_utc"] >= lo) & (hr["start_utc"] <= hi)].sort_values("start_utc")
    result = {
        "rhr_night_bpm": np.nan,
        "rhr_window_end_utc": pd.NaT,
        "hr_night_count": len(w),
        "hr_slot_count": w["start_utc"].dt.floor(f"{C.HR_COVERAGE_SLOT_MIN}min").nunique(),
        "rolling": None,
    }
    if w.empty:
        return result
    series = w.set_index("start_utc")["value"]
    window = f"{C.RHR_WINDOW_MIN}min"
    roll = pd.DataFrame({"mean": series.rolling(window).mean(), "n": series.rolling(window).count()})
    # Only windows that are full length (start after onset) and have enough readings.
    full = roll.index - pd.Timedelta(minutes=C.RHR_WINDOW_MIN) >= lo
    valid = roll[full & (roll["n"] >= C.RHR_MIN_SAMPLES_IN_WINDOW)]
    result["rolling"] = roll
    if not valid.empty:
        result["rhr_night_bpm"] = float(valid["mean"].min())
        result["rhr_window_end_utc"] = valid["mean"].idxmin()
    return result


NIGHT_COLUMNS = [
    "night_date",
    "sleep_onset",
    "final_wake",
    "sleep_window_min",
    "tst_min",
    "core_min",
    "deep_min",
    "rem_min",
    "unspecified_min",
    "waso_min",
    "awakenings",
    "tib_min",
    "tib_source",
    "sleep_latency_min",
    "sleep_efficiency_pct",
    "fragmentation_per_hr",
    "waso_pct_of_tib",
    "hrv_night_ms",
    "hrv_ln",
    "hrv_count",
    "rhr_night_bpm",
    "hr_night_count",
    "hr_slot_count",
    "apple_rhr_bpm",
    "naps",
]


def nightly_metrics(sessions: pd.DataFrame, stages: pd.DataFrame, cleaned: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Step 4. One row per night that has a main sleep."""
    hr, hrv = cleaned["heart_rate"], cleaned["hrv_sdnn"]
    in_bed, apple_rhr = cleaned["in_bed"], cleaned["resting_heart_rate"]
    apple_rhr_by_day = apple_rhr.groupby(apple_rhr["start_local"].dt.date)["value"].mean()
    match = pd.Timedelta(hours=C.IN_BED_MATCH_HOURS)

    rows = []
    for _, s in sessions[sessions["is_main"]].iterrows():
        lo, hi = s["onset_utc"], s["wake_utc"]
        g = stages[stages["session_id"] == s["session_id"]]
        mins = _clip_minutes(g, lo, hi)
        by_stage = mins.groupby(g["stage"]).sum()
        minutes = {k: float(by_stage.get(k, 0.0)) for k in ("core", "deep", "rem", "asleep_unspecified")}
        tst = sum(minutes[k] for k in C.ASLEEP_STAGES)
        awakenings, waso = count_awakenings(g[g["stage"] == "awake"], lo, hi)
        window_min = (hi - lo).total_seconds() / 60

        # Time in bed: iPhone "In Bed" if it overlaps this night, else the sleep window itself.
        ib = in_bed[(in_bed["end_utc"] > lo - match) & (in_bed["start_utc"] < hi + match)]
        if not ib.empty:
            tib_start, tib_end, tib_source = (
                min(ib["start_utc"].min(), lo),
                max(ib["end_utc"].max(), hi),
                "iphone_in_bed",
            )
        else:
            tib_start, tib_end, tib_source = lo, hi, "sleep_window"
        tib = (tib_end - tib_start).total_seconds() / 60

        # Overnight vitals, restricted to the main sleep window.
        night_hrv = hrv[(hrv["start_utc"] >= lo) & (hrv["start_utc"] <= hi)]["value"]
        hrv_mean = float(night_hrv.mean()) if len(night_hrv) else np.nan
        rhr = overnight_rhr(hr, lo, hi)

        rows.append(
            {
                "night_date": s["night_date"],
                "sleep_onset": s["onset_local"],
                "final_wake": s["wake_local"],
                "sleep_window_min": window_min,
                "tst_min": tst,
                "core_min": minutes["core"],
                "deep_min": minutes["deep"],
                "rem_min": minutes["rem"],
                "unspecified_min": minutes["asleep_unspecified"],
                "waso_min": waso,
                "awakenings": awakenings,
                "tib_min": tib,
                "tib_source": tib_source,
                "sleep_latency_min": (lo - tib_start).total_seconds() / 60 if tib_source == "iphone_in_bed" else np.nan,
                "sleep_efficiency_pct": tst / tib * 100 if tib > 0 else np.nan,
                "fragmentation_per_hr": awakenings / (tst / 60) if tst > 0 else np.nan,
                "waso_pct_of_tib": waso / tib * 100 if tib > 0 else np.nan,
                "hrv_night_ms": hrv_mean,
                "hrv_ln": math.log(hrv_mean) if C.HRV_LOG_TRANSFORM and hrv_mean > 0 else hrv_mean,
                "hrv_count": int(len(night_hrv)),
                "rhr_night_bpm": rhr["rhr_night_bpm"],
                "hr_night_count": rhr["hr_night_count"],
                "hr_slot_count": rhr["hr_slot_count"],
                "apple_rhr_bpm": apple_rhr_by_day.get(s["wake_local"].date(), np.nan),
                "naps": int(((sessions["night_date"] == s["night_date"]) & ~sessions["is_main"]).sum()),
            }
        )
    return pd.DataFrame(rows, columns=NIGHT_COLUMNS)
