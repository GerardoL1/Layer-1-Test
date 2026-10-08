"""
Daily updates: process only new data, one night at a time.

The first sync loads the whole history and processes every night (a backfill).
Every later sync:
  1. cleans only the records that just arrived and adds them to the saved raw data
  2. works out which nights are READY: the clock is past the user's update time the next day,
     or the user tapped "Update now" and last night's sleep has ended
  3. processes every ready night that hasn't been processed yet  (catches up skipped days)
  4. re-processes the night(s) before those                     (picks up late-arriving data)
     RECOMPUTE_NIGHTS = 3 means: the newest night, plus 2 nights already processed
  5. computes nightly metrics from only those nights' raw data
  6. builds their baselines and z-scores from the SAVED nightly rows of earlier nights,
     never re-reading old raw data

The same step functions as pipeline.py are used, so day-by-day results equal a full
reprocessing of the same data. tests/test_incremental.py checks this.

In the real system the "saved" tables live in the server database; here they are kept
in memory so the test platform can show each run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

import config as C
import pipeline as P

KEY = ["metric", "stage", "value", "source", "start_utc", "end_utc"]  # what makes a record unique


@dataclass
class RunReport:
    run: int
    sync_time: datetime
    received: dict                 # records that arrived this sync, by data type
    duplicates_skipped: int        # already saved from an earlier sync
    removed_by_cleaning: int
    new_nights: list               # processed for the first time
    recomputed_nights: list        # processed again
    changed: dict                  # recomputed night -> columns whose value changed
    ready_through: date | None     # latest night that is ready
    raw_rows_read: int = 0         # saved raw records read to compute this run
    raw_rows_saved: int = 0        # all raw records saved so far

    @property
    def kind(self) -> str:
        if self.run == 1:
            return "Initial load"
        return "Catch-up" if len(self.new_nights) > 1 else "Daily update"


def scheduled_ready_night(sync_time: datetime, update_time=C.DEFAULT_UPDATE_TIME) -> date:
    """The newest night whose next day has passed the user's update time."""
    h, m = update_time
    return (sync_time - timedelta(hours=h, minutes=m)).date() - timedelta(days=1)


def latest_ready_night(sync_time: datetime, sleep_stages: pd.DataFrame | None = None,
                       update_time=C.DEFAULT_UPDATE_TIME, update_now: bool = False) -> date:
    """
    The newest night that is ready to process at sync_time.

    Normally: every night whose next day has passed the user's update time.
    With update_now (the user tapped "Update now"): also any later night whose main sleep has
    already ended by sync_time.
    """
    ready = scheduled_ready_night(sync_time, update_time)
    if not update_now or sleep_stages is None or sleep_stages.empty:
        return ready
    lo = pd.Timestamp(datetime.combine(ready + timedelta(days=1), time(0)))
    recent = sleep_stages[(sleep_stages["end_local"] >= lo) & (sleep_stages["start_local"] <= pd.Timestamp(sync_time))]
    if recent.empty:
        return ready
    sessions, st = P.find_sleep_windows(recent)
    if sessions.empty:
        return ready
    session_end = st.groupby("session_id")["end_local"].max()     # includes trailing awake pieces
    for _, s in sessions[sessions["is_main"]].sort_values("night_date").iterrows():
        if ready < s["night_date"] <= sync_time.date() and session_end[s["session_id"]] <= pd.Timestamp(sync_time):
            ready = s["night_date"]
    return ready


class DailyProcessor:
    """Keeps the saved data between syncs and processes only what each sync needs."""

    def __init__(self, person_id: str = "tester1", recompute_nights: int = C.RECOMPUTE_NIGHTS,
                 update_time=C.DEFAULT_UPDATE_TIME):
        self.person_id = person_id
        self.update_time = update_time          # the user's daily update time (hour, minute)
        self.recompute_nights = recompute_nights
        self.saved: dict[str, pd.DataFrame] | None = None   # cleaned raw data received so far
        self.nights = pd.DataFrame()                          # saved nightly rows (all columns)
        self.reports: list[RunReport] = []
        self.last_raw_rows_read = 0

    # ------------------------------------------------------------ saving raw data
    def _save(self, cleaned_new: dict[str, pd.DataFrame]) -> int:
        """Add newly arrived cleaned records; returns how many were already saved."""
        if self.saved is None:
            self.saved = {k: v.copy() for k, v in cleaned_new.items()}
            return 0
        skipped = 0
        for k, new in cleaned_new.items():
            old = self.saved[k]
            if new.empty:
                continue
            overlap = old[old["end_utc"] >= new["start_utc"].min()]   # only rows that could repeat
            seen = set(map(tuple, overlap[KEY].astype(str).values))
            fresh = ~new[KEY].astype(str).apply(tuple, axis=1).isin(seen)
            skipped += int((~fresh).sum())
            self.saved[k] = pd.concat([old, new[fresh]], ignore_index=True).sort_values("start_utc",
                                                                                    ignore_index=True)
        return skipped

    # ------------------------------------------------------------ nightly metrics from only those nights' raw data
    def _metrics_for(self, nights: list) -> pd.DataFrame:
        """Nightly metrics for the given nights, reading only the raw data around them."""
        lo = pd.Timestamp(datetime.combine(min(nights), time(0))) - pd.Timedelta(hours=6)
        hi = pd.Timestamp(datetime.combine(max(nights), time(0))) + pd.Timedelta(days=2, hours=6)
        sub = {k: v[(v["end_local"] >= lo) & (v["start_local"] <= hi)] for k, v in self.saved.items()}
        self.last_raw_rows_read = sum(len(v) for v in sub.values())
        sessions, stages = P.find_sleep_windows(sub["sleep_stages"])
        if sessions.empty:
            return pd.DataFrame(columns=P.NIGHT_COLUMNS)
        return P.nightly_metrics(sessions[sessions["night_date"].isin(nights)], stages, sub)

    # ------------------------------------------------------------ one sync
    def sync(self, new_records: pd.DataFrame, sync_time: datetime, update_now: bool = False) -> RunReport:
        """Save what arrived and process every ready night. update_now = the user tapped \"Update now\"."""
        received = (new_records.assign(data=new_records["stage"].fillna(new_records["metric"]))
                    .groupby("data").size().to_dict()) if len(new_records) else {}
        cleaned_new, removal_log, _ = P.clean(new_records)
        skipped = self._save(cleaned_new)

        stages = self.saved["sleep_stages"]
        ready_through = latest_ready_night(sync_time, stages, self.update_time, update_now)
        asleep = stages[stages["stage"].isin(C.ASLEEP_STAGES)]
        if asleep.empty and self.nights.empty:
            report = RunReport(len(self.reports) + 1, sync_time, received, skipped,
                               int(removal_log["removed"].sum()) if len(removal_log) else 0,
                               [], [], {}, None)
            self.reports.append(report)
            return report

        # Which nights to process: every ready night not yet processed, plus the last few again.
        first = (self.nights["night_date"].min() if len(self.nights) else
                 (asleep["start_local"].min() - pd.Timedelta(hours=C.NIGHT_SHIFT_HOURS)).date())
        ready = [d.date() for d in pd.date_range(first, ready_through, freq="D")] if first <= ready_through else []
        done = set(self.nights["night_date"]) if len(self.nights) else set()
        new_nights = [d for d in ready if d not in done]
        # "Recompute the last 2 nights" = the newest night plus the 1 before it. During a catch-up
        # the newest nights are all new, so the redo always targets nights processed in earlier runs.
        redo = max(self.recompute_nights - 1, 0)
        recompute = sorted(d for d in done if d <= ready_through)[-redo:] if redo else []
        # Also redo every night the previous run processed for the first time. After a catch-up
        # (two or more new nights at once), late data for the older ones would otherwise be missed.
        # Only recent nights: late data arrives within a day or so, not weeks later.
        if redo and self.reports:
            recent = ready_through - timedelta(days=C.LATE_DATA_DAYS)
            recompute = sorted(set(recompute) | {d for d in self.reports[-1].new_nights if d in done and d >= recent})
        targets = sorted(set(new_nights) | set(recompute))

        if targets:
            metrics = self._metrics_for(targets)
            fresh = P.flag_quality(metrics, first_night=targets[0], last_night=targets[-1])
            before = self.nights.set_index("night_date") if len(self.nights) else None
            kept = self.nights[~self.nights["night_date"].isin(targets)] if len(self.nights) else self.nights
            table = pd.concat([kept, fresh], ignore_index=True).sort_values("night_date", ignore_index=True)
            # Baselines only for the nights processed now, using the saved rows before them.
            self.nights = P.add_baselines(table, only_dates=targets)
            changed = self._changes(before, recompute)
        else:
            changed = {}

        report = RunReport(len(self.reports) + 1, sync_time, received, skipped,
                           int(removal_log["removed"].sum()) if len(removal_log) else 0,
                           new_nights, recompute, changed, ready_through,
                           self.last_raw_rows_read if targets else 0,
                           sum(len(v) for v in self.saved.values()))
        self.reports.append(report)
        return report

    def _changes(self, before: pd.DataFrame | None, nights: list) -> dict:
        if before is None or not nights:
            return {}
        after = self.nights.set_index("night_date")
        cols = [c for c in P.ML_COLUMNS if c in after.columns and c in before.columns]
        out = {}
        for d in nights:
            diffs = []
            for c in cols:
                a, b = before.at[d, c], after.at[d, c]
                if (pd.isna(a) and pd.isna(b)):
                    continue
                if pd.isna(a) != pd.isna(b) or (isinstance(a, (int, float, np.number)) and not np.isclose(a, b)) \
                        or (not isinstance(a, (int, float, np.number)) and a != b):
                    diffs.append(c)
            if diffs:
                out[d] = diffs
        return out

    # ------------------------------------------------------------ outputs
    @property
    def ml_table(self) -> pd.DataFrame:
        if self.nights.empty:
            return pd.DataFrame(columns=list(P.ML_COLUMNS))
        return P.build_ml_table(self.nights, self.person_id)


# ======================================================================= simulation helpers

def arrival_times(records: pd.DataFrame, late_hrv: bool = False) -> pd.Series:
    """
    When each record reaches the phone/server, in local time. Normally right after it
    ends; with late_hrv, HRV readings show up 26 hours later (after the next sync).
    """
    arrive = records["end_local"].copy()
    if late_hrv:
        hrv = records["metric"] == "hrv_sdnn"
        arrive[hrv] = arrive[hrv] + pd.Timedelta(hours=26)
    return arrive


def full_reprocessing(received: pd.DataFrame, person_id: str, ready_through: date) -> pd.DataFrame:
    """Reference: process everything received so far in one go (the original pipeline)."""
    cleaned, _, _ = P.clean(received)
    sessions, stages = P.find_sleep_windows(cleaned["sleep_stages"])
    nights = P.flag_quality(P.nightly_metrics(sessions, stages, cleaned), last_night=ready_through)
    nights = nights[nights["night_date"] <= ready_through].reset_index(drop=True)
    nights = P.add_baselines(nights)
    return P.build_ml_table(nights, person_id)


def compare(daily: pd.DataFrame, full: pd.DataFrame) -> pd.DataFrame:
    """Rows where day-by-day and all-at-once disagree (empty means identical)."""
    if daily.empty and full.empty:
        return pd.DataFrame()
    a = daily.set_index("night_date")
    b = full.set_index("night_date")
    nights = a.index.intersection(b.index)
    problems = []
    for n in nights:
        for c in a.columns:
            x, y = a.at[n, c], b.at[n, c]
            same = (pd.isna(x) and pd.isna(y)) or (
                not (pd.isna(x) or pd.isna(y)) and
                (np.isclose(float(x), float(y), rtol=1e-9, atol=1e-9) if isinstance(x, (int, float, np.number))
                 and not isinstance(x, bool) else x == y))
            if not same:
                problems.append({"night": n, "column": c, "day_by_day": x, "all_at_once": y})
    missing = sorted(set(a.index) ^ set(b.index))
    for n in missing:
        problems.append({"night": n, "column": "(whole row)",
                         "day_by_day": "present" if n in a.index else "missing",
                         "all_at_once": "present" if n in b.index else "missing"})
    return pd.DataFrame(problems)
