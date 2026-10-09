"""
Server-side processing. The main check: running DailyProcessor through the
database, several times a day, gives the same table as processing everything at once.

    python -m pytest -q tests
"""
from datetime import datetime, time, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import db
import incremental as I
import main
import pipeline as P
import processing
from conftest import SAMPLE_DATA, SAMPLES

client = TestClient(main.app)


def store(user: str, recs: pd.DataFrame):
    """Put pipeline-style records into the database, keeping each one's UTC offset."""
    def ms(col):
        return (recs[col] - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(milliseconds=1)

    def offset(side):
        return ((recs[f"{side}_local"] - recs[f"{side}_utc"].dt.tz_localize(None)) // pd.Timedelta(minutes=1))

    start, end, s_tz, e_tz = ms("start_utc"), ms("end_utc"), offset("start"), offset("end")
    samples, stages = [], []
    for i, r in enumerate(recs.itertuples()):
        a, b, sz, ez = int(start.iloc[i]), int(end.iloc[i]), int(s_tz.iloc[i]), int(e_tz.iloc[i])
        if r.kind == "sleep":
            if isinstance(r.stage, str):
                stages.append((db.sleep_id(user, r.stage, a, b, r.source), r.stage, a, b, sz, ez, r.source))
        elif pd.notna(r.value):
            samples.append((db.sample_id(user, r.metric, a, b, r.value, r.source),
                            r.metric, float(r.value), a, b, sz, r.source))
    with db.connect() as conn:
        db.add_readings(conn, user, samples, stages)


def load(person, offset_hours=None):
    recs, _ = P.load_export(SAMPLE_DATA / SAMPLES[person], days=None)
    if offset_hours is not None:   # same moments, but lived in another time zone
        for side in ("start", "end"):
            recs[f"{side}_local"] = recs[f"{side}_utc"].dt.tz_localize(None) + pd.Timedelta(hours=offset_hours)
    return recs


def to_utc(local: datetime, offset_min: int) -> datetime:
    return (local - timedelta(minutes=offset_min)).replace(tzinfo=timezone.utc)


def last_ready(user):
    with db.connect() as conn:
        row = conn.execute("SELECT ready_through FROM runs WHERE user_id = ? ORDER BY run DESC LIMIT 1",
                           (user,)).fetchone()
    return datetime.fromisoformat(row["ready_through"]).date() if row and row["ready_through"] else None


def saved_table(user):
    with db.connect() as conn:
        return processing.ml_table(conn, user)


def replay(person, user, late_hrv=False, hours=(8, 16, 23), first_load_days=24):
    recs = load(person)
    arrive = I.arrival_times(recs, late_hrv)
    offset = -420   # mock data is Los Angeles summer time
    day = recs["start_local"].min().date() + timedelta(days=first_load_days)
    end = recs["end_local"].max().date() + timedelta(days=1)
    prev, problems, runs = None, [], 0
    while day <= end:
        for h in hours:
            sync = datetime.combine(day, time(h))
            new = (arrive <= sync) if prev is None else ((arrive > prev) & (arrive <= sync))
            store(user, recs[new])
            if processing.process_user(user, to_utc(sync, offset)):
                runs += 1
            full = I.full_reprocessing(recs[arrive <= sync], user, last_ready(user))
            problems.append(I.compare(saved_table(user), full))
            prev = sync
        day += timedelta(days=1)
    return runs, [p for p in problems if len(p)]


@pytest.mark.parametrize("person", list(SAMPLES))
def test_server_runs_equal_all_at_once(person):
    runs, problems = replay(person, f"replay_{person}")
    assert not problems
    assert runs > 0


def test_late_hrv_is_picked_up():
    _, problems = replay("alex", "replay_late", late_hrv=True)
    assert not problems


def test_runs_only_when_something_changed():
    user = "lazy"
    recs = load("sam")
    stop = recs["start_local"].min().normalize() + pd.Timedelta(days=12, hours=9)
    store(user, recs[recs["end_local"] <= stop])
    morning = stop.to_pydatetime()
    assert processing.process_user(user, to_utc(morning, -420)) is not None
    # Same data, same morning: nothing to do.
    assert processing.process_user(user, to_utc(morning + timedelta(hours=2), -420)) is None
    # The next morning passes the update time, so a new night is ready.
    with db.connect() as conn:
        assert processing.needs_processing(conn, user, to_utc(morning + timedelta(days=1), -420))
    # New readings also trigger a run.
    store(user, recs[(recs["end_local"] > stop) & (recs["end_local"] <= stop + pd.Timedelta(hours=3))])
    assert processing.process_user(user, to_utc(morning + timedelta(hours=3), -420)) is not None


def test_update_time_and_update_now():
    user = "clock"
    recs = load("sam")
    day = recs["start_local"].min().date() + timedelta(days=10)
    night = day - timedelta(days=1)
    sleep = recs[recs["stage"].notna() & (recs["start_local"] >= pd.Timestamp(datetime.combine(night, time(18))))
                 & (recs["start_local"] <= pd.Timestamp(datetime.combine(day, time(14))))]
    woke = sleep["end_local"].max().to_pydatetime()
    store(user, recs[recs["end_local"] <= pd.Timestamp(woke)])
    with db.connect() as conn:
        conn.execute("UPDATE users SET update_time = '17:00' WHERE user_id = ?", (user,))

    early = processing.process_user(user, to_utc(woke + timedelta(minutes=5), -420))
    assert night not in early.new_nights                 # before 17:00, last night waits
    now = processing.process_user(user, to_utc(woke + timedelta(minutes=6), -420), update_now=True)
    assert night in now.new_nights                       # "Update now" after waking processes it


def test_nights_follow_the_users_time_zone():
    # Same moments as sam's data, but stored as if lived in Tokyo (+9 h instead of -7 h).
    user = "tokyo"
    recs = load("sam", offset_hours=9)
    store(user, recs)
    with db.connect() as conn:
        conn.execute("UPDATE users SET timezone = 'Asia/Tokyo' WHERE user_id = ?", (user,))
        tokyo = processing.local_now(conn, user, datetime(2026, 10, 2, 0, 0, tzinfo=timezone.utc))
    assert tokyo == datetime(2026, 10, 2, 9, 0)
    processing.process_user(user, datetime(2026, 10, 3, 0, 0, tzinfo=timezone.utc))
    full = I.full_reprocessing(recs, user, last_ready(user))
    assert I.compare(saved_table(user), full).empty


def test_new_data_starts_processing():
    with open(SAMPLE_DATA / SAMPLES["jordan"], "rb") as f:
        client.post("/api/import", files={"file": ("export.zip", f, "application/zip")},
                    data={"user_id": "auto", "since_days": "0"})
    assert client.get("/api/import/status").json()["state"] == "done"
    # The real clock is past the mock data, so every night is ready. Nights after the data ends
    # get flagged empty rows, just like the full pipeline run up to the same night.
    recs, _ = P.load_export(SAMPLE_DATA / SAMPLES["jordan"], days=None)
    expected = I.full_reprocessing(recs, "auto", last_ready("auto"))
    assert I.compare(saved_table("auto"), expected).empty
