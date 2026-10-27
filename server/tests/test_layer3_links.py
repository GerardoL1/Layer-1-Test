"""
Where Layer 3 meets Layer 1: a demo reload starts clean, the workout list follows the person's clock,
and the training table carries the sweat columns.

    python -m pytest -q tests/test_layer3_links.py
"""

import math
from datetime import datetime, timezone

import main
from fastapi.testclient import TestClient

from app.core import db
from app.services import training_table

client = TestClient(main.app)
SAM = "/api/v1/users/demo-sam"
CDT = -300


def ms(y, mo, d, h):
    return int(datetime(y, mo, d, h, tzinfo=timezone.utc).timestamp() * 1000) - CDT * 60000


def workout(wid, start):
    return client.post(
        f"{SAM}/workouts",
        json={
            "id": wid,
            "start_ms": start,
            "end_ms": start + 3600000,
            "start_tz_min": CDT,
            "end_tz_min": CDT,
            "type": "Gym",
        },
    )


def test_a_demo_reload_clears_workouts_check_ins_and_snapshots():
    client.post("/api/v1/demo-users/sam")
    assert workout("left_behind", ms(2026, 9, 29, 18)).status_code == 200
    client.post(
        f"{SAM}/checkins/morning",
        json={"answered_at_ms": ms(2026, 9, 30, 7), "tz_offset_min": CDT, "answers": {"ready_to_train": 5}},
    )
    client.post("/api/v1/demo-users/sam")
    with db.connect() as conn:
        for table in ("workouts", "checkins", "sweat_sessions"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = 'demo-sam'").fetchone()[0] == 0
    assert client.get(f"{SAM}/workouts/left_behind").status_code == 404


def test_the_workout_list_counts_back_from_the_demo_clock():
    client.post("/api/v1/demo-users/sam")  # clock fixed at 1 Oct 2026, 8:30
    workout("recent", ms(2026, 9, 28, 18))
    workout("older", ms(2026, 9, 10, 18))
    assert [w["id"] for w in client.get(f"{SAM}/workouts?days=7").json()] == ["recent"]


def test_the_training_table_carries_sweat_and_never_fills_in_zeros():
    client.post("/api/v1/demo-users/sam")
    client.patch(f"{SAM}/settings", json={"weight_kg": 70})
    assert client.post("/api/v1/demo-users/sam/sweat").status_code == 200
    with db.connect() as conn:
        t = training_table.build(conn, ["demo-sam"], include_catch_up=True)
    assert set(training_table.SWEAT_COLUMNS) <= set(t.columns)
    with_sweat = t[t["has_sweat_data"] == True]  # noqa: E712
    without = t[t["has_sweat_data"] == False]  # noqa: E712
    assert len(with_sweat) and len(without)
    assert (with_sweat["fluid_loss_pct_bw_2d"] > 0).all()
    assert all(math.isnan(v) for v in without["fluid_loss_pct_bw_1d"])
