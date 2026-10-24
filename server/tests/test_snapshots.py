"""
readiness_snapshots keeps the first score each night got, with its inputs, for training the readiness model.
Late data and rebuilds change the saved nights and Today, but never the snapshot.

    python -m pytest -q tests/test_snapshots.py
"""

import json
from datetime import timedelta

import pandas as pd
from test_processing import load, store, to_utc

from app.core import db
from app.readiness.features import build_features
from app.readiness.model import get_model
from app.services import processing

LA = -420  # mock data is Los Angeles summer time


def snapshots(user):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM readiness_snapshots WHERE user_id = ? ORDER BY night_date", (user,))
        return [dict(r) for r in rows]


def morning_after(recs, days):
    return recs["start_local"].min().normalize() + pd.Timedelta(days=days, hours=9)


def test_each_new_night_gets_one_snapshot_scored_from_what_today_reads():
    user = "snap_first"
    recs = load("sam")
    stop = morning_after(recs, 12)
    store(user, recs[recs["end_local"] <= stop])
    report = processing.process_user(user, to_utc(stop.to_pydatetime(), LA))
    snaps = snapshots(user)
    assert [s["night_date"] for s in snaps] == [d.isoformat() for d in sorted(report.new_nights)]
    # The first run catches up on many nights, and only the newest was shown on Today that morning.
    assert [s["catch_up"] for s in snaps] == [1] * (len(snaps) - 1) + [0]
    with db.connect() as conn:
        nights = processing.load_nights(conn, user)
    want = get_model().score(build_features(nights))
    last = snaps[-1]
    assert (last["score"], last["status"], last["confidence"]) == (want.score, want.status, want.confidence)
    assert json.loads(last["features"]) == build_features(nights)
    assert last["model_version"] == "placeholder-1" and last["taken_local"].startswith(stop.date().isoformat())


def test_late_data_changes_today_but_not_the_snapshot():
    user = "snap_late"
    recs = load("alex")
    stop = morning_after(recs, 20)
    last_night = (stop - pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=12)
    # Last night's HRV is held back, as when it syncs late.
    late = (recs["metric"] == "hrv_sdnn") & (recs["start_local"] >= last_night)
    store(user, recs[(recs["end_local"] <= stop) & ~late])
    processing.process_user(user, to_utc(stop.to_pydatetime(), LA))
    first = snapshots(user)[-1]
    assert json.loads(first["features"])["z_hrv"] is None

    store(user, recs[(recs["end_local"] <= stop) & late])
    processing.process_user(user, to_utc(stop.to_pydatetime() + timedelta(hours=2), LA))
    with db.connect() as conn:
        nights = processing.load_nights(conn, user)
    assert pd.notna(nights.iloc[-1]["z_hrv"])  # the saved night now has its HRV
    assert snapshots(user)[-1] == first  # but the snapshot still shows what the model saw that morning


def test_a_rebuild_adds_no_snapshots_and_changes_none():
    user = "snap_rebuild"
    store(user, load("jordan"))
    processing.process_user(user, force=True)
    before = snapshots(user)
    assert before and any(s["score"] is None for s in before)  # no-score nights are kept too, with their status
    processing.process_user(user, force=True)
    assert snapshots(user) == before
