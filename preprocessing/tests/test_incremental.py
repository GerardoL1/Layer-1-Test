"""
Daily updates must give exactly the same table as processing everything at once.

    python -m pytest -q tests/test_incremental.py
"""
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import config as C  # noqa: E402
import incremental as I  # noqa: E402
import pipeline as P  # noqa: E402
from run_pipeline import SAMPLES  # noqa: E402


def replay(person, late_hrv=False, recompute=C.RECOMPUTE_NIGHTS, first_load_days=24, step_days=1):
    """Feed a sample file to DailyProcessor one sync at a time; return processor + all mismatches."""
    recs, _ = P.load_export(HERE / "sample_data" / SAMPLES[person], days=None)
    arrive = I.arrival_times(recs, late_hrv)
    first_day = recs["start_local"].min().date()
    end = recs["end_local"].max().date() + timedelta(days=1)
    proc = I.DailyProcessor(person, recompute)
    prev, sync, problems = None, datetime.combine(first_day + timedelta(days=first_load_days),
                                                  time(C.SIM_SYNC_HOUR)), []
    while sync.date() <= end:
        new = (arrive <= sync) if prev is None else ((arrive > prev) & (arrive <= sync))
        report = proc.sync(recs[new], sync)
        full = I.full_reprocessing(recs[arrive <= sync], person, report.ready_through)
        problems.append(I.compare(proc.ml_table, full))
        prev, sync = sync, sync + timedelta(days=step_days)
    return proc, [p for p in problems if len(p)]


@pytest.mark.parametrize("person", ["sam", "alex", "jordan"])
def test_day_by_day_equals_all_at_once(person):
    proc, problems = replay(person)
    assert not problems
    assert proc.reports[0].kind == "Initial load"
    # Every night is processed as new exactly once (a late wake-up can push a night to the next sync).
    seen = [d for r in proc.reports for d in r.new_nights]
    assert len(seen) == len(set(seen)) == len(proc.nights)
    assert all(len(r.new_nights) <= 2 for r in proc.reports[1:])


def test_skipped_days_are_caught_up():
    proc, problems = replay("jordan", step_days=3)
    assert not problems
    assert any(r.kind == "Catch-up" and len(r.new_nights) == 3 for r in proc.reports)


def test_late_hrv_is_fixed_by_recomputing_recent_nights():
    proc, problems = replay("alex", late_hrv=True)
    assert not problems
    assert any("hrv_night_ms" in cols for r in proc.reports for cols in r.changed.values())


def test_late_hrv_is_missed_without_recompute():
    _, problems = replay("alex", late_hrv=True, recompute=1)
    assert problems                                    # proves the redo rule matters


def _morning(day_offset=10):
    """sam's records, the morning to test, last night's date and when that night's sleep ended."""
    recs, _ = P.load_export(HERE / "sample_data" / SAMPLES["sam"], days=None)
    morning = recs["start_local"].min().date() + timedelta(days=day_offset)
    night = morning - timedelta(days=1)
    sleep = recs[recs["stage"].notna()
                 & (recs["start_local"] >= pd.Timestamp(datetime.combine(night, time(18))))
                 & (recs["start_local"] <= pd.Timestamp(datetime.combine(morning, time(14))))]
    return recs, night, sleep["end_local"].max().to_pydatetime()


def _sync_at(recs, when, update_now=False, update_time=C.DEFAULT_UPDATE_TIME):
    proc = I.DailyProcessor("sam", update_time=update_time)
    return proc, proc.sync(recs[recs["end_local"] <= pd.Timestamp(when)], when, update_now=update_now)


def _at(day, hm):
    return datetime.combine(day, time(*hm))


def test_night_waits_for_the_update_time():
    recs, night, _ = _morning()
    h, m = C.DEFAULT_UPDATE_TIME
    _, early = _sync_at(recs, _at(night + timedelta(days=1), (h - 1, m)))
    assert night not in early.new_nights and early.ready_through == night - timedelta(days=1)
    _, on_time = _sync_at(recs, _at(night + timedelta(days=1), (h, m)))
    assert night in on_time.new_nights and on_time.ready_through == night


def test_update_now_processes_last_night_early():
    recs, night, woke = _morning()
    when = woke + timedelta(minutes=5)
    assert when < _at(night + timedelta(days=1), C.DEFAULT_UPDATE_TIME)      # before the update time
    _, normal = _sync_at(recs, when)
    assert night not in normal.new_nights
    _, tapped = _sync_at(recs, when, update_now=True)
    assert night in tapped.new_nights


def test_update_now_before_bed_does_not_create_tonight():
    recs, night, _ = _morning()
    evening = _at(night + timedelta(days=1), (21, 0))     # the next evening, not asleep yet
    _, report = _sync_at(recs, evening, update_now=True)
    assert report.ready_through == night                   # last night yes, tonight no


def test_users_own_update_time():
    recs, night, _ = _morning()
    morning = night + timedelta(days=1)
    _, noon = _sync_at(recs, _at(morning, (12, 0)), update_time=(17, 0))   # e.g. a night-shift worker
    assert night not in noon.new_nights
    _, five = _sync_at(recs, _at(morning, (17, 0)), update_time=(17, 0))
    assert night in five.new_nights


def test_night_without_sleep_gets_a_row_at_the_update_time():
    recs, night, _ = _morning()
    lo = pd.Timestamp(datetime.combine(night, time(12)))
    hi = pd.Timestamp(datetime.combine(night + timedelta(days=1), time(12)))
    no_sleep = recs[~(recs["stage"].notna() & (recs["start_local"] >= lo) & (recs["start_local"] < hi))]
    proc, report = _sync_at(no_sleep, _at(night + timedelta(days=1), C.DEFAULT_UPDATE_TIME))
    assert night in report.new_nights
    assert not proc.nights.set_index("night_date").loc[night, "usable_sleep"]   # flagged, not filled in


def test_resending_the_same_data_changes_nothing():
    recs, _ = P.load_export(HERE / "sample_data" / SAMPLES["sam"], days=None)
    sync = datetime.combine(recs["start_local"].min().date() + timedelta(days=12), time(C.SIM_SYNC_HOUR))
    sent = recs[recs["end_local"] <= sync]
    proc = I.DailyProcessor("sam")
    proc.sync(sent, sync)
    before = proc.ml_table.copy()
    again = proc.sync(sent, sync)
    assert again.duplicates_skipped == len(sent) - again.removed_by_cleaning
    assert not again.new_nights
    assert I.compare(proc.ml_table, before).empty
