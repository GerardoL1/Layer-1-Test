"""
Step 2. Clean: Apple Watch only, no duplicates, no impossible values.
"""

from __future__ import annotations

import pandas as pd

from layer1 import config as C


def _named(source: pd.Series, keywords) -> pd.Series:
    """True where the source name contains one of the keywords."""
    mask = pd.Series(False, index=source.index)
    for kw in keywords:
        mask |= source.str.contains(kw, case=False, regex=False)
    return mask


def clean(records: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, pd.DataFrame]:
    """
    Step 2. Returns cleaned tables, a summary of what was removed, and the removed rows themselves.

    Tables: heart_rate, resting_heart_rate (Apple's daily value), hrv_sdnn,
            sleep_stages (watch only, no In Bed), in_bed (iPhone or watch).
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

    # Watch only. "In Bed" is the exception: it comes from the iPhone's sleep schedule.
    watch = _named(df["source"], C.WATCH_SOURCE_KEYWORDS)
    iphone_in_bed = (df["stage"] == "in_bed") & _named(df["source"], C.IN_BED_SOURCE_KEYWORDS)
    keep_source = watch | iphone_in_bed
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
    removal_log = (
        pd.DataFrame(log, columns=["reason", "data", "removed"])
        if log
        else pd.DataFrame(columns=["reason", "data", "removed"])
    )
    removed_rows = (
        pd.concat(removed_parts, ignore_index=True)
        if removed_parts
        else records.iloc[0:0].assign(reason=pd.Series(dtype=str))
    )
    return out, removal_log, removed_rows
