"""
Independent checks for Layer 1. Nothing here reuses the pipeline's own math: the truth comes
from the scenario builder, and the formulas are re-implemented from docs/layer1_spec.md.

Every check returns Result(check, status, detail). status is "pass", "fail" or "warn".

Expectation types for a scenario's "expect" list:
  {"type": "rows", "equals": 35}
  {"type": "mean",  "column": "z_hrv", "nights": "last 5", "below": -1}        (or "above")
  {"type": "value", "column": "tst_min", "night": 12, "between": [100, 200]}  (or "equals")
  {"type": "flag",  "nights": [5, 6], "note_contains": "no HRV"}
  {"type": "usable", "nights": [5], "column": "usable_hrv", "equals": false}
  {"type": "no_row", "nights": [1]}                                           night must not appear
  {"type": "empty", "column": "z_hrv", "nights": "last 6"}                    value must be missing
"night"/"nights" use the scenario's night numbers (1 = first evening); "last N" counts back
from the last night of the scenario; {"from": a, "to": b} is a range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

TOL_MIN = 0.05        # minutes
TOL_REL = 1e-6

SPEC = {  # values from docs/layer1_spec.md, deliberately not imported from config.py
    "min_tst": 180, "min_hr_per_hour": 2, "baseline_nights": 28, "baseline_min": 7,
    "sd_floor": 0.02, "rhr_window": 30, "rhr_min_readings": 3,
    "hr_range": (30, 220), "hrv_range": (5, 300),
}
Z = {"z_hrv": ("hrv_ln", "usable_hrv"), "z_rhr": ("rhr_night_bpm", "usable_rhr"),
     "z_tst": ("tst_min", "usable_sleep"), "z_eff": ("sleep_efficiency_pct", "usable_sleep"),
     "z_frag": ("fragmentation_per_hr", "usable_sleep")}


@dataclass
class Result:
    check: str
    status: str
    detail: str = ""


def _close(a, b, tol=TOL_MIN) -> bool:
    if a is None or b is None or (isinstance(a, float) and math.isnan(a)) or (isinstance(b, float) and math.isnan(b)):
        return (a is None or (isinstance(a, float) and math.isnan(a))) and (b is None or (isinstance(b, float) and math.isnan(b)))
    return abs(float(a) - float(b)) <= tol + TOL_REL * abs(float(b))


def _isnan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x)


def _off(o: str) -> timedelta:
    return (-1 if o[0] == "-" else 1) * timedelta(hours=int(o[1:3]), minutes=int(o[3:5]))


def oracle_rhr(records, onset_local: datetime, wake_local: datetime, offset: str) -> float:
    """Lowest 30-min rolling mean of clean watch HR inside the window, computed independently."""
    lo, hi = onset_local - _off(offset), wake_local - _off(offset)
    seen, pts = set(), []
    for r in records:
        if r.rtype != "HKQuantityTypeIdentifierHeartRate" or "Apple Watch" not in r.source:
            continue
        v = float(r.value)
        if not (SPEC["hr_range"][0] <= v <= SPEC["hr_range"][1]):
            continue
        t = r.start - _off(r.offset)
        key = (t, v, r.source)
        if key in seen:
            continue
        seen.add(key)
        if lo <= t <= hi:
            pts.append((t, v))
    pts.sort()
    best = None
    w = timedelta(minutes=SPEC["rhr_window"])
    for i, (t, _) in enumerate(pts):
        if t - w < lo:
            continue
        window = [v for (tt, v) in pts[: i + 1] if tt > t - w]
        if len(window) >= SPEC["rhr_min_readings"]:
            m = sum(window) / len(window)
            best = m if best is None or m < best else best
    return float("nan") if best is None else best


def truth_checks(scenario, nights: pd.DataFrame) -> list[Result]:
    out = []
    rows = {str(d): r for d, r in zip(nights["night_date"].astype(str), nights.to_dict("records"))}
    bad = {k: [] for k in ("missing_row", "tst", "stages", "waso", "awakenings", "tib", "hrv", "naps", "rhr", "onset")}
    for t in scenario.truth["nights"]:
        d = t["night_date"]
        if not t["has_sleep"]:
            continue
        r = rows.get(d)
        if r is None:
            bad["missing_row"].append(d); continue
        if not _close(r["tst_min"], t["tst_min"]):
            bad["tst"].append(f"{d}: got {r['tst_min']:.2f}, truth {t['tst_min']:.2f}")
        for k in ("core_min", "deep_min", "rem_min", "unspecified_min"):
            if not _close(r[k], t[k]):
                bad["stages"].append(f"{d} {k}: got {r[k]:.2f}, truth {t[k]:.2f}")
        if not _close(r["waso_min"], t["waso_min"]):
            bad["waso"].append(f"{d}: got {r['waso_min']:.2f}, truth {t['waso_min']:.2f}")
        if int(r["awakenings"]) != t["awakenings"]:
            bad["awakenings"].append(f"{d}: got {r['awakenings']}, truth {t['awakenings']}")
        if r["tib_source"] != t["tib_source"] or not _close(r["tib_min"], t["tib_min"]):
            bad["tib"].append(f"{d}: got {r['tib_source']} {r['tib_min']:.2f}, truth {t['tib_source']} {t['tib_min']:.2f}")
        n_hrv = len(t["hrv_readings"])
        if int(r["hrv_count"]) != n_hrv or not _close(r["hrv_night_ms"], t["hrv_night_ms"], 1e-6):
            bad["hrv"].append(f"{d}: got {r['hrv_count']} readings mean {r['hrv_night_ms']}, truth {n_hrv} mean {t['hrv_night_ms']}")
        if int(r["naps"]) != t["naps"]:
            bad["naps"].append(f"{d}: got {r['naps']} naps, truth {t['naps']}")
        onset = datetime.fromisoformat(t["onset"]); wake = datetime.fromisoformat(t["final_wake"])
        if pd.Timestamp(r["sleep_onset"]) != pd.Timestamp(onset) or pd.Timestamp(r["final_wake"]) != pd.Timestamp(wake):
            bad["onset"].append(f"{d}: got {r['sleep_onset']}–{r['final_wake']}, truth {onset}–{wake}")
        want = oracle_rhr(scenario.records, onset, wake, t["offset"])
        if not _close(r["rhr_night_bpm"], want, 1e-6):
            bad["rhr"].append(f"{d}: got {r['rhr_night_bpm']}, independent calc {want}")
    names = {"missing_row": "Every night with sleep has a row", "tst": "Total sleep time matches truth",
             "stages": "Core / deep / REM minutes match truth", "waso": "Awake minutes after onset match truth",
             "awakenings": "Awakening count matches truth", "tib": "Time in bed and its source match truth",
             "hrv": "HRV readings and nightly mean match truth", "naps": "Naps detected and ignored",
             "rhr": "Overnight resting HR matches independent calculation",
             "onset": "Sleep window trimmed to onset → final awakening"}
    for k, label in names.items():
        out.append(Result(label, "fail" if bad[k] else "pass", "; ".join(bad[k][:8]) + (" …" if len(bad[k]) > 8 else "")))
    return out


def spec_checks(nights: pd.DataFrame, ml: pd.DataFrame) -> list[Result]:
    out = []
    df = nights.copy()
    has = df["tst_min"].notna()

    def rule(label, mask_bad, cols):
        bad = df[mask_bad]
        det = "; ".join(f"{r['night_date']}: " + ", ".join(f"{c}={r[c]}" for c in cols) for _, r in bad.head(6).iterrows())
        out.append(Result(label, "fail" if len(bad) else "pass", det))

    eff = df["tst_min"] / df["tib_min"] * 100
    rule("Efficiency = TST ÷ time in bed × 100", has & ~np.isclose(eff, df["sleep_efficiency_pct"], rtol=1e-9),
         ["tst_min", "tib_min", "sleep_efficiency_pct"])
    rule("Efficiency between 0 and 100", has & ((df["sleep_efficiency_pct"] <= 0) | (df["sleep_efficiency_pct"] > 100 + 1e-9)),
         ["sleep_efficiency_pct"])
    rule("Time in bed ≥ total sleep time", has & (df["tib_min"] < df["tst_min"] - 1e-9), ["tib_min", "tst_min"])
    frag = df["awakenings"].astype(float) / (df["tst_min"] / 60)
    rule("Fragmentation = awakenings per hour of sleep", has & ~np.isclose(frag, df["fragmentation_per_hr"], rtol=1e-9),
         ["awakenings", "tst_min", "fragmentation_per_hr"])
    waso_pct = df["waso_min"] / df["tib_min"] * 100
    rule("Spec fragmentation = awake minutes ÷ time in bed × 100",
         has & ~np.isclose(waso_pct, df["waso_pct_of_tib"], rtol=1e-9), ["waso_min", "tib_min", "waso_pct_of_tib"])
    hv = df["hrv_night_ms"].notna()
    rule("hrv_ln = ln(nightly HRV)", hv & ~np.isclose(np.log(df["hrv_night_ms"].where(hv, 1)), df["hrv_ln"].where(hv, 0)),
         ["hrv_night_ms", "hrv_ln"])
    rule("HRV within 5–300 ms", hv & ((df["hrv_night_ms"] < 5) | (df["hrv_night_ms"] > 300)), ["hrv_night_ms"])

    us = has & (df["tst_min"] >= SPEC["min_tst"])
    rule("usable_sleep = sleep recorded and TST ≥ 180 min", us != df["usable_sleep"].astype(bool), ["tst_min", "usable_sleep"])
    uh = us & (df["hrv_count"].fillna(0) > 0)
    rule("usable_hrv = usable sleep and ≥ 1 HRV reading", uh != df["usable_hrv"].astype(bool), ["hrv_count", "usable_hrv"])
    per_h = df["hr_night_count"] / (df["tst_min"] / 60)
    ur = us & df["rhr_night_bpm"].notna() & (per_h >= SPEC["min_hr_per_hour"])
    rule("usable_rhr = usable sleep, valid RHR and ≥ 2 HR readings per hour", ur != df["usable_rhr"].astype(bool),
         ["hr_night_count", "rhr_night_bpm", "usable_rhr"])
    incomplete = ~(df["usable_sleep"].astype(bool) & df["usable_hrv"].astype(bool) & df["usable_rhr"].astype(bool))
    notes = df["quality_notes"].fillna("") != ""
    rule("Every incomplete night has a quality note", incomplete & ~notes, ["quality_notes"])
    # "no sleep stages" is informational: the night is still usable, so it may carry that note alone.
    other_notes = df["quality_notes"].fillna("").str.replace("no sleep stages", "", regex=False).str.strip("; ") != ""
    rule("Complete nights carry no warning notes (\"no sleep stages\" is informational)", ~incomplete & other_notes,
         ["quality_notes"])

    dates = pd.to_datetime(df["night_date"])
    gaps = (dates.diff().dt.days.fillna(1) != 1)
    out.append(Result("One row per calendar night, no gaps or duplicates", "fail" if gaps.any() else "pass",
                      ", ".join(str(d.date()) for d in dates[gaps].head(5))))
    out.append(Result("readiness_label is an empty placeholder",
                      "pass" if ml["readiness_label"].isna().all() else "fail", ""))
    return out


def zscore_oracle(nights: pd.DataFrame) -> list[Result]:
    """Re-compute every baseline and z-score from the table's own values, per the spec."""
    out = []
    df = nights.reset_index(drop=True)
    dates = pd.to_datetime(df["night_date"])
    for z, (col, gate) in Z.items():
        bad = []
        vals = [v if g else None for v, g in zip(df[col], df[gate].fillna(False).astype(bool))]
        for i, d in enumerate(dates):
            prev = [vals[j] for j in range(len(df))
                    if dates[j] < d and dates[j] >= d - pd.Timedelta(days=SPEC["baseline_nights"])
                    and vals[j] is not None and not _isnan(vals[j])]
            want = float("nan")
            if len(prev) >= SPEC["baseline_min"] and vals[i] is not None and not _isnan(vals[i]):
                mu = sum(prev) / len(prev)
                sd = math.sqrt(sum((x - mu) ** 2 for x in prev) / (len(prev) - 1))
                sd = max(sd, SPEC["sd_floor"] * abs(mu))
                want = (vals[i] - mu) / sd if sd > 0 else float("nan")
            got = df.at[i, z]
            if not _close(got, want, 1e-6):
                bad.append(f"{d.date()}: got {got}, expected {want} (baseline n={len(prev)})")
        out.append(Result(f"{z} matches an independent baseline calculation", "fail" if bad else "pass",
                          "; ".join(bad[:6])))
    return out


def _resolve(spec_nights, truth) -> list[str]:
    all_n = [t["night_date"] for t in truth["nights"]]
    if isinstance(spec_nights, str) and spec_nights.startswith("last "):
        return all_n[-int(spec_nights.split()[1]):]
    if isinstance(spec_nights, dict):
        return all_n[int(spec_nights["from"]) - 1: int(spec_nights["to"])]
    if isinstance(spec_nights, int):
        spec_nights = [spec_nights]
    return [all_n[int(n) - 1] for n in spec_nights]


def expectation_checks(expect: list, truth: dict, nights: pd.DataFrame) -> list[Result]:
    out = []
    rows = nights.set_index(nights["night_date"].astype(str))
    for e in expect:
        kind = e["type"]
        label = e.get("label") or f"Expect {kind}: " + ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("type", "label"))
        try:
            if kind == "rows":
                ok = len(nights) == e["equals"]; det = f"{len(nights)} rows"
            elif kind == "no_row":
                ds = _resolve(e["nights"], truth); present = [d for d in ds if d in rows.index]
                ok = not present; det = f"present: {present}" if present else ""
            else:
                ds = _resolve(e.get("nights", e.get("night")), truth)
                missing = [d for d in ds if d not in rows.index]
                if missing:
                    out.append(Result(label, "fail", f"no row for {missing}")); continue
                sub = rows.loc[ds]
                if kind == "mean":
                    m = sub[e["column"]].astype(float).mean()
                    ok = (m < e["below"]) if "below" in e else (m > e["above"]); det = f"mean {m:.3f}"
                elif kind == "value":
                    vals = sub[e["column"]].tolist()
                    if "between" in e:
                        lo, hi = e["between"]; ok = all(lo <= float(v) <= hi for v in vals)
                    else:
                        ok = all(v == e["equals"] for v in vals)
                    det = f"values {vals}"
                elif kind == "flag":
                    notes = sub["quality_notes"].fillna("").tolist()
                    ok = all(e["note_contains"] in n for n in notes); det = f"notes {notes}"
                elif kind == "empty":
                    vals = sub[e["column"]].tolist(); ok = all(_isnan(v) for v in vals); det = f"values {vals}"
                elif kind == "usable":
                    vals = sub[e["column"]].astype(bool).tolist(); ok = all(v == e["equals"] for v in vals); det = f"{vals}"
                else:
                    out.append(Result(label, "warn", f"unknown expectation type '{kind}'")); continue
            out.append(Result(label, "pass" if ok else "fail", det))
        except Exception as ex:  # a broken expectation is reported, not crashed on
            out.append(Result(label, "warn", f"could not evaluate: {ex}"))
    return out
