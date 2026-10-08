"""
Layer 1 preprocessing: Apple Health export -> one ML-ready row per person per night.

Each step is a plain function that takes the previous step's output, so the steps
can be inspected one at a time (the test platform does this) or chained with
run_pipeline(). All tunable numbers come from config.py.

    1. load_export        read the records we need from export.zip / export.xml
    2. clean              watch-only, de-duplicate, drop impossible values
    3. find_sleep_windows group sleep pieces into sessions, pick each night's main sleep
    4. nightly_metrics    TST, efficiency, fragmentation, overnight HRV and resting HR
    5. flag_quality       mark short, empty and incomplete nights
    6. add_baselines      rolling personal baselines and z-scores (previous nights only)
    7. build_ml_table     final feature table + column dictionary
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

import config as C

DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


# ======================================================================= 1. Load

def _open_xml(source) -> IO[bytes]:
    """Accepts a path or file-like object pointing at export.zip or export.xml."""
    name = getattr(source, "name", str(source))
    if str(name).lower().endswith(".zip"):
        zf = zipfile.ZipFile(source)
        inner = next((n for n in zf.namelist() if n.endswith("export.xml")
                      and not n.endswith("export_cda.xml")), None)
        if inner is None:
            raise ValueError("No export.xml inside this zip. Use the zip made by the Health app "
                             "(Health > profile picture > Export All Health Data).")
        return zf.open(inner)
    if isinstance(source, (str, Path)):
        return open(source, "rb")
    return source


def load_export(source, days: int | None = C.DEFAULT_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Step 1. Stream the export and keep heart rate, resting HR, HRV and sleep records.

    Returns
      records      one row per kept record, with UTC and local timestamps
      type_counts  how many records of every type were in the file (kept or not)
    """
    rows, counts = [], {}
    with _open_xml(source) as f:
        for _, elem in ET.iterparse(f, events=("end",)):
            if elem.tag == "Record":
                rtype = elem.get("type", "")
                counts[rtype] = counts.get(rtype, 0) + 1
                if rtype in C.QUANTITY_TYPES:
                    rows.append(("quantity", C.QUANTITY_TYPES[rtype], elem.get("value"), elem.get("unit"),
                                 elem.get("sourceName", ""), elem.get("startDate"), elem.get("endDate")))
                elif rtype == C.SLEEP_TYPE:
                    rows.append(("sleep", "sleep_analysis", elem.get("value"), None,
                                 elem.get("sourceName", ""), elem.get("startDate"), elem.get("endDate")))
            if elem.tag in ("Record", "Workout", "Correlation", "ActivitySummary", "ClinicalRecord"):
                elem.clear()

    type_counts = (pd.DataFrame(sorted(counts.items(), key=lambda kv: -kv[1]), columns=["type", "records"])
                   if counts else pd.DataFrame(columns=["type", "records"]))
    type_counts["kept"] = type_counts["type"].isin(list(C.QUANTITY_TYPES) + [C.SLEEP_TYPE])

    records = pd.DataFrame(rows, columns=["kind", "metric", "raw_value", "unit", "source", "start_str", "end_str"])
    if records.empty:
        raise ValueError("No heart rate, HRV or sleep records found in this export.")

    # Apple writes local time with its UTC offset, e.g. "2026-09-30 23:14:05 -0700".
    # UTC is used for ordering and durations; the local wall-clock time decides which night it belongs to.
    for side in ("start", "end"):
        txt = records[f"{side}_str"].astype(str)
        records[f"{side}_utc"] = pd.to_datetime(txt, format=DATE_FORMAT, utc=True, errors="coerce")
        records[f"{side}_local"] = pd.to_datetime(txt.str.slice(0, 19), format="%Y-%m-%d %H:%M:%S", errors="coerce")
    records = records.dropna(subset=["start_utc", "end_utc"]).copy()

    records["value"] = np.where(records["kind"] == "quantity",
                                pd.to_numeric(records["raw_value"], errors="coerce"), np.nan)
    records["stage"] = records["raw_value"].map(C.SLEEP_VALUES).where(records["kind"] == "sleep")

    if days:
        cutoff = records["end_utc"].max() - pd.Timedelta(days=days)
        records = records[records["start_utc"] >= cutoff]

    records = records.drop(columns=["start_str", "end_str"]).sort_values("start_utc").reset_index(drop=True)
    return records, type_counts


# ======================================================================= 2. Clean

def _is_watch(source: pd.Series) -> pd.Series:
    mask = pd.Series(False, index=source.index)
    for kw in C.WATCH_SOURCE_KEYWORDS:
        mask |= source.str.contains(kw, case=False, regex=False)
    return mask


def clean(records: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """
    Step 2. Returns cleaned tables, a summary of what was removed, and the removed rows themselves.

    Tables: heart_rate, resting_heart_rate (Apple's daily value), hrv_sdnn,
            sleep_stages (watch only, no In Bed), in_bed (any source).
    """
    log, removed_parts = [], []
    df = records.copy()

    def drop(mask, reason):
        nonlocal df
        removed = df[mask]
        for metric, n in removed.groupby(removed["stage"].fillna(removed["metric"])).size().items():
            log.append({"reason": reason, "data": metric, "removed": int(n)})
        if len(removed):
            removed_parts.append(removed.assign(reason=reason))
        df = df[~mask]

    # Unknown sleep values (future iOS categories we don't handle yet).
    drop((df["kind"] == "sleep") & df["stage"].isna(), "Unrecognised sleep value")

    # Watch only. "In Bed" is the exception: it usually comes from the iPhone's sleep schedule.
    watch = _is_watch(df["source"])
    in_bed = df["stage"] == "in_bed"
    keep_source = watch | (in_bed if C.IN_BED_ANY_SOURCE else False)
    drop(~keep_source, "Not recorded by the Apple Watch")

    # Exact duplicates (same data, same time, same source), e.g. from re-imports or sync glitches.
    dup = df.duplicated(subset=["metric", "stage", "value", "source", "start_utc", "end_utc"])
    drop(dup, "Exact duplicate")

    # Impossible values.
    bad = pd.Series(False, index=df.index)
    for metric, (lo, hi) in C.VALID_RANGES.items():
        m = df["metric"] == metric
        bad |= m & (df["value"].isna() | (df["value"] < lo) | (df["value"] > hi))
    drop(bad, "Value outside plausible range")

    # Sleep segments that are too short to mean anything, or impossibly long / backwards.
    dur = (df["end_utc"] - df["start_utc"]).dt.total_seconds()
    sleep = df["kind"] == "sleep"
    drop(sleep & (dur < C.MIN_SLEEP_SEGMENT_SEC), "Sleep segment too short")
    dur = (df["end_utc"] - df["start_utc"]).dt.total_seconds()
    sleep = df["kind"] == "sleep"
    drop(sleep & (dur > C.MAX_SLEEP_SEGMENT_HOURS * 3600), "Sleep segment too long")

    out = {
        "heart_rate": df[df["metric"] == "heart_rate"],
        "resting_heart_rate": df[df["metric"] == "resting_heart_rate"],
        "hrv_sdnn": df[df["metric"] == "hrv_sdnn"],
        "sleep_stages": df[(df["kind"] == "sleep") & (df["stage"] != "in_bed")],
        "in_bed": df[df["stage"] == "in_bed"],
    }
    out = {k: v.reset_index(drop=True) for k, v in out.items()}
    removal_log = (pd.DataFrame(log, columns=["reason", "data", "removed"])
                   if log else pd.DataFrame(columns=["reason", "data", "removed"]))
    removed_rows = (pd.concat(removed_parts, ignore_index=True) if removed_parts
                    else records.iloc[0:0].assign(reason=pd.Series(dtype=str)))
    return out, removal_log, removed_rows


# ======================================================================= 3. Sleep window

def find_sleep_windows(stages: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Step 3. Group sleep pieces into sessions and choose each night's main sleep.

    A new session starts when the gap since the previous piece exceeds SESSION_GAP_MIN.
    Each session's window runs from the first asleep piece (onset) to the last asleep
    piece (final awakening); awake pieces before onset or after final awakening are ignored.

    Returns
      sessions  one row per session, with night_date and is_main
      stages    the input stages with a session_id column
    """
    st = stages.sort_values("start_utc").reset_index(drop=True).copy()
    if st.empty:
        st["session_id"] = pd.Series(dtype=int)
        return pd.DataFrame(columns=["session_id", "night_date", "onset_utc", "wake_utc", "onset_local",
                                     "wake_local", "asleep_min", "is_main"]), st

    gap = pd.Timedelta(minutes=C.SESSION_GAP_MIN)
    session_ids, current, latest_end = [], 0, None
    for start, end in zip(st["start_utc"], st["end_utc"]):
        if latest_end is not None and start - latest_end > gap:
            current += 1
        session_ids.append(current)
        latest_end = end if latest_end is None else max(latest_end, end)
    st["session_id"] = session_ids

    rows = []
    for sid, g in st.groupby("session_id"):
        asleep = g[g["stage"].isin(C.ASLEEP_STAGES)]
        if asleep.empty:          # a session of only "awake" pieces is not sleep
            continue
        first, last = asleep.loc[asleep["start_utc"].idxmin()], asleep.loc[asleep["end_utc"].idxmax()]
        asleep_min = (asleep["end_utc"] - asleep["start_utc"]).dt.total_seconds().sum() / 60
        night = (first["start_local"] - timedelta(hours=C.NIGHT_SHIFT_HOURS)).date()
        rows.append({"session_id": sid, "night_date": night,
                     "onset_utc": first["start_utc"], "wake_utc": last["end_utc"],
                     "onset_local": first["start_local"], "wake_local": last["end_local"],
                     "asleep_min": asleep_min})
    sessions = pd.DataFrame(rows)
    sessions["is_main"] = False
    main_idx = sessions.groupby("night_date")["asleep_min"].idxmax()
    sessions.loc[main_idx, "is_main"] = True
    return sessions, st


# ======================================================================= 4. Nightly metrics

def _clip_minutes(df: pd.DataFrame, lo, hi) -> pd.Series:
    """Minutes of each row that fall inside [lo, hi]."""
    s = df["start_utc"].clip(lower=lo, upper=hi)
    e = df["end_utc"].clip(lower=lo, upper=hi)
    return (e - s).dt.total_seconds() / 60


def count_awakenings(awake: pd.DataFrame, lo, hi) -> tuple[int, float]:
    """Awake pieces inside the window, with touching pieces merged. Returns (count, total minutes)."""
    a = awake[(awake["end_utc"] > lo) & (awake["start_utc"] < hi)].sort_values("start_utc")
    bouts = []
    for s, e in zip(a["start_utc"].clip(lower=lo), a["end_utc"].clip(upper=hi)):
        if bouts and s <= bouts[-1][1] + pd.Timedelta(seconds=60):
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
    result = {"rhr_night_bpm": np.nan, "rhr_window_end_utc": pd.NaT, "hr_night_count": len(w), "rolling": None}
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


NIGHT_COLUMNS = ["night_date", "sleep_onset", "final_wake", "sleep_window_min", "tst_min", "core_min", "deep_min",
                 "rem_min", "unspecified_min", "waso_min", "awakenings", "tib_min", "tib_source",
                 "sleep_latency_min", "sleep_efficiency_pct", "fragmentation_per_hr", "waso_pct_of_tib",
                 "hrv_night_ms", "hrv_ln", "hrv_count", "rhr_night_bpm", "hr_night_count", "apple_rhr_bpm", "naps"]


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
        stage = lambda k: float(by_stage.get(k, 0.0))
        tst = sum(stage(k) for k in C.ASLEEP_STAGES)
        awakenings, waso = count_awakenings(g[g["stage"] == "awake"], lo, hi)
        window_min = (hi - lo).total_seconds() / 60

        # Time in bed: iPhone "In Bed" if it overlaps this night, else the sleep window itself.
        ib = in_bed[(in_bed["end_utc"] > lo - match) & (in_bed["start_utc"] < hi + match)]
        if not ib.empty:
            tib_start, tib_end, tib_source = min(ib["start_utc"].min(), lo), max(ib["end_utc"].max(), hi), "iphone_in_bed"
        else:
            tib_start, tib_end, tib_source = lo, hi, "sleep_window"
        tib = (tib_end - tib_start).total_seconds() / 60

        # Overnight vitals, restricted to the main sleep window.
        night_hrv = hrv[(hrv["start_utc"] >= lo) & (hrv["start_utc"] <= hi)]["value"]
        hrv_mean = float(night_hrv.mean()) if len(night_hrv) else np.nan
        rhr = overnight_rhr(hr, lo, hi)

        rows.append({
            "night_date": s["night_date"],
            "sleep_onset": s["onset_local"],
            "final_wake": s["wake_local"],
            "sleep_window_min": window_min,
            "tst_min": tst,
            "core_min": stage("core"),
            "deep_min": stage("deep"),
            "rem_min": stage("rem"),
            "unspecified_min": stage("asleep_unspecified"),
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
            "apple_rhr_bpm": apple_rhr_by_day.get(s["wake_local"].date(), np.nan),
            "naps": int(((sessions["night_date"] == s["night_date"]) & ~sessions["is_main"]).sum()),
        })
    return pd.DataFrame(rows, columns=NIGHT_COLUMNS)


# ======================================================================= 5. Missing data / quality

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
    df["flag_no_stages"] = has_sleep & (df["unspecified_min"].fillna(0) >= df["tst_min"].fillna(0)) & (df["tst_min"] > 0)
    df["flag_no_hrv"] = has_sleep & (df["hrv_count"].fillna(0) == 0)
    hr_per_hour = df["hr_night_count"] / (df["tst_min"] / 60)
    df["flag_low_hr_coverage"] = has_sleep & (hr_per_hour.fillna(0) < C.MIN_HR_SAMPLES_PER_SLEEP_HOUR)
    df["flag_no_rhr"] = has_sleep & df["rhr_night_bpm"].isna()

    df["usable_sleep"] = has_sleep & ~df["flag_short_sleep"]
    df["usable_hrv"] = df["usable_sleep"] & ~df["flag_no_hrv"]
    df["usable_rhr"] = df["usable_sleep"] & ~df["flag_low_hr_coverage"] & ~df["flag_no_rhr"]

    labels = {"flag_no_sleep_data": "no sleep recorded", "flag_short_sleep": "short sleep",
              "flag_no_stages": "no sleep stages", "flag_no_hrv": "no HRV",
              "flag_low_hr_coverage": "few heart rate readings", "flag_no_rhr": "no overnight resting HR"}
    df["quality_notes"] = df.apply(lambda r: "; ".join(t for c, t in labels.items() if r[c]), axis=1)
    return df


# ======================================================================= 6. Baselines and z-scores

def add_baselines(nights: pd.DataFrame, only_dates=None) -> pd.DataFrame:
    """
    Step 6. For each night and each metric in ZSCORE_METRICS:
      baseline = values from the previous BASELINE_WINDOW_NIGHTS calendar nights (not tonight),
                 using only nights where that metric is usable
      z        = (tonight - baseline mean) / baseline SD, only if the baseline has
                 BASELINE_MIN_NIGHTS values and tonight's own value is usable

    only_dates: if given, only those nights are (re)computed and every other row keeps the
    baseline it already has. Daily updates use this so old nights aren't touched.
    """
    df = nights.copy()
    dates = pd.to_datetime(df["night_date"])
    rows = range(len(df)) if only_dates is None else \
        [i for i, d in enumerate(df["night_date"]) if d in set(only_dates)]
    for col, (zcol, _label, gate) in C.ZSCORE_METRICS.items():
        usable = df[col].where(df[gate].fillna(False).astype(bool))
        for name in (f"{col}_base_mean", f"{col}_base_sd", f"{col}_base_n", zcol):
            if name not in df:
                df[name] = np.nan
        for i in rows:
            d = dates.iloc[i]
            window = (dates >= d - pd.Timedelta(days=C.BASELINE_WINDOW_NIGHTS)) & (dates < d)
            vals = usable[window].dropna()
            n = len(vals)
            if n >= C.BASELINE_MIN_NIGHTS:
                mu = float(vals.mean())
                sd = max(float(vals.std(ddof=1)), C.MIN_SD_FRACTION_OF_MEAN * abs(mu))
                tonight = usable.iloc[i]
                z = (tonight - mu) / sd if pd.notna(tonight) and sd > 0 else np.nan
            else:
                mu = sd = z = np.nan
            df.iloc[i, df.columns.get_loc(f"{col}_base_mean")] = mu
            df.iloc[i, df.columns.get_loc(f"{col}_base_sd")] = sd
            df.iloc[i, df.columns.get_loc(f"{col}_base_n")] = n
            df.iloc[i, df.columns.get_loc(zcol)] = z
    return df


# ======================================================================= 7. ML-ready table

ML_COLUMNS = {
    # identity
    "person_id": "Tester / user the night belongs to",
    "night_date": "Date of the evening the night started (YYYY-MM-DD)",
    "weekday": "Day of week of night_date (0 = Monday)",
    # sleep architecture
    "tst_min": "Total sleep time: core + deep + REM (+ unspecified) minutes",
    "core_min": "Core sleep minutes", "deep_min": "Deep sleep minutes", "rem_min": "REM sleep minutes",
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
    **{z: f"z-score of {label} vs previous {C.BASELINE_WINDOW_NIGHTS} nights (needs {C.BASELINE_MIN_NIGHTS})"
       for _, (z, label, _g) in C.ZSCORE_METRICS.items()},
    "hrv_ln_base_n": "Nights in the HRV baseline", "rhr_night_bpm_base_n": "Nights in the resting HR baseline",
    # quality
    "usable_sleep": "Night has enough sleep data to use",
    "usable_hrv": "HRV value usable", "usable_rhr": "Overnight resting HR usable",
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


# ======================================================================= Run everything

@dataclass
class PipelineResult:
    person_id: str
    type_counts: pd.DataFrame
    records: pd.DataFrame
    cleaned: dict
    removal_log: pd.DataFrame
    removed_rows: pd.DataFrame
    sessions: pd.DataFrame
    stages: pd.DataFrame
    nights: pd.DataFrame          # metrics + flags + baselines (everything)
    ml_table: pd.DataFrame
    notes: list = field(default_factory=list)


def run_pipeline(source, person_id: str = "tester1", days: int | None = C.DEFAULT_DAYS) -> PipelineResult:
    records, type_counts = load_export(source, days)
    cleaned, removal_log, removed_rows = clean(records)
    sessions, stages = find_sleep_windows(cleaned["sleep_stages"])
    metrics = nightly_metrics(sessions, stages, cleaned)
    notes = []
    if metrics.empty:
        notes.append("No sleep sessions found. Is sleep tracking on (iPhone Watch app > Sleep)?")
        first = cleaned["heart_rate"]["start_local"].min()
        last = cleaned["heart_rate"]["start_local"].max()
        nights = flag_quality(metrics, first.date() if pd.notna(first) else None,
                              last.date() if pd.notna(last) else None)
    else:
        nights = flag_quality(metrics)
    nights = add_baselines(nights) if not nights.empty else nights
    ml = build_ml_table(nights, person_id) if not nights.empty else pd.DataFrame(columns=list(ML_COLUMNS))
    return PipelineResult(person_id, type_counts, records, cleaned, removal_log, removed_rows,
                          sessions, stages, nights, ml, notes)
