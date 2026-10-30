"""
The training table export: each night's first-shown snapshot joined with that morning's check-in
and the training load up to that evening. Catch-up nights are left out unless asked for.

    python -m pytest -q tests/test_training_table.py
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import main
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_checkins_workouts import local_ms, morning
from test_processing import load, store, to_utc

from app.core import db
from app.services import processing, training_table

client = TestClient(main.app)
LA = -420
SERVER = Path(__file__).resolve().parent.parent


def ms_at(day, hour, minute=0):
    """UTC milliseconds for a Los Angeles wall-clock time."""
    return local_ms(day.year, day.month, day.day, hour, minute, offset=LA)


@pytest.fixture(scope="module")
def person():
    """Sam's first 12 days in one go (a catch-up), then two normal mornings, with check-ins and workouts."""
    user = "train_table"
    recs = load("sam")
    first_morning = recs["start_local"].min().normalize() + pd.Timedelta(days=12, hours=9)
    for i in range(3):
        stop = first_morning + pd.Timedelta(days=i)
        store(user, recs[recs["end_local"] <= stop])
        processing.process_user(user, to_utc(stop.to_pydatetime(), LA))
    with db.connect() as conn:
        snaps = [
            dict(r)
            for r in conn.execute("SELECT * FROM readiness_snapshots WHERE user_id = ? ORDER BY night_date", (user,))
        ]
    shown = [s for s in snaps if not s["catch_up"]]
    night = datetime.fromisoformat(shown[-1]["night_date"]).date()
    u = f"/api/v1/users/{user}"
    client.patch(f"{u}/settings", json={"weight_kg": 70})
    # The morning after that night: the label.
    answers = {"ready_to_train": 4, "fatigue": 3, "sore_muscles": ["quads", "glutes"], "unusual": []}
    morning(u, ms_at(night + timedelta(days=1), 7, 30), answers, offset=LA)
    # Workouts that evening (rated 8, 60 min) and two days before (rated 5, 30 min), plus one never rated.
    for wid, day, minutes, effort in (
        ("w_today", night, 60, 8),
        ("w_before", night - timedelta(days=2), 30, 5),
        ("w_unrated", night, 45, None),
    ):
        start = ms_at(day, 18)
        client.post(
            f"{u}/workouts",
            json={
                "id": wid,
                "start_ms": start,
                "end_ms": start + minutes * 60000,
                "start_tz_min": LA,
                "end_tz_min": LA,
                "type": "Gym",
            },
        )
        if effort:
            client.put(f"{u}/workouts/{wid}/rating", json={"effort": effort, "answered_at_ms": start + 3600000})
    return {"user": user, "snaps": snaps, "shown": shown, "night": night.isoformat()}


def table(person, **kw):
    with db.connect() as conn:
        return training_table.build(conn, [person["user"]], **kw)


def test_one_row_per_shown_night_with_its_snapshot(person):
    t = table(person)
    assert list(t.columns) == training_table.COLUMNS
    assert list(t["night_date"]) == [s["night_date"] for s in person["shown"]]
    assert len(table(person, include_catch_up=True)) == len(person["snaps"])
    last, snap = t.iloc[-1], person["shown"][-1]
    assert last["placeholder_score"] == snap["score"] and last["model_version"] == "placeholder-1"
    features = json.loads(snap["features"])
    assert last["tst_min"] == pytest.approx(features["tst_min"]) and last["weight_kg"] == 70


def test_the_check_in_labels_the_night_before_it(person):
    t = table(person).set_index("night_date")
    row = t.loc[person["night"]]
    assert row["checkin_ready_to_train"] == 4 and row["checkin_fatigue"] == 3
    assert row["checkin_sore_muscles"] == "quads;glutes" and row["checkin_unusual"] == "none"
    assert pd.isna(row["checkin_energy"]) and pd.isna(row["checkin_rehydrated"])
    others = t.drop(index=person["night"])
    assert others["checkin_ready_to_train"].isna().all()


def test_training_load_counts_rated_workouts_up_to_that_evening(person):
    row = table(person).set_index("night_date").loc[person["night"]]
    assert row["load_1d"] == 8 * 60  # the unrated workout adds nothing
    assert row["load_3d"] == row["load_7d"] == row["load_28d"] == 8 * 60 + 5 * 30
    assert row["rated_workouts_7d"] == 2


def test_the_command_writes_a_csv_but_never_inside_the_repo(person, tmp_path):
    env = {**os.environ}
    inside = subprocess.run(
        [sys.executable, "export_training_table.py", "training.csv"],
        cwd=SERVER,
        env=env,
        capture_output=True,
        text=True,
    )
    assert inside.returncode != 0 and "Refusing" in inside.stderr
    assert not (SERVER / "training.csv").exists()
    out = tmp_path / "training.csv"
    done = subprocess.run(
        [sys.executable, "export_training_table.py", str(out), "--user", person["user"], "--labelled-only"],
        cwd=SERVER,
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
    csv = pd.read_csv(out)
    assert list(csv["night_date"]) == [person["night"]] and "1 with a check-in" in done.stdout
