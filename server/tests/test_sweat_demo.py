"""
Demo sweat data: a demo person gets workouts and sweat sessions before the demo clock, through the
same import code as real files. Also the rehydrate amount the workout summary shows.

    python -m pytest -q tests/test_sweat_demo.py
"""

from datetime import date

import main
import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.services import sweat, sweat_demo

client = TestClient(main.app)


@pytest.fixture(scope="module")
def sam():
    assert client.post("/api/v1/demo-users/sam").status_code == 200
    r = client.post("/api/v1/demo-users/sam/sweat")
    assert r.status_code == 200, r.text
    return r.json()


def test_demo_sweat_loads_workouts_and_sessions(sam):
    assert sam == {"user_id": "demo-sam", "workouts": 7, "sweat_sessions": 5}
    sessions = client.get("/api/v1/users/demo-sam/sweat/sessions", params={"days": 3650}).json()
    by_workout = {s["workout_id"]: s for s in sessions}
    assert set(by_workout) == {"demo-run-0930", "demo-legs-0929", "demo-upper-0927", "demo-legs-0925", "demo-long-0920"}
    assert by_workout["demo-legs-0929"]["sweat_detected"] is True
    assert by_workout["demo-upper-0927"]["sweat_detected"] is False
    assert by_workout["demo-upper-0927"]["unit_system"] == "customary"
    assert by_workout["demo-legs-0925"]["source"] == "manual"
    # Same local times as written, in the offset of the demo person's readings.
    assert by_workout["demo-legs-0929"]["start_local"] == "2026-09-29T18:10"
    assert by_workout["demo-legs-0929"]["workout_id"] == "demo-legs-0929"


def test_demo_morning_has_a_hydration_line(sam):
    # The demo clock is 1 Oct, 8:30 am, so Today shows the night of 30 Sep and yesterday's evening run.
    assert sweat.hydration_line("demo-sam", date(2026, 9, 30)).startswith("Yesterday's easy run cost about")


def test_reloading_starts_fresh(sam):
    again = client.post("/api/v1/demo-users/sam/sweat").json()
    assert again == sam
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM sweat_sessions WHERE user_id = 'demo-sam'").fetchone()[0]
        w = conn.execute("SELECT COUNT(*) FROM workouts WHERE user_id = 'demo-sam'").fetchone()[0]
    assert (n, w) == (5, 7)


def test_demo_person_must_be_loaded_first():
    with db.connect() as conn:
        conn.execute("DELETE FROM users WHERE user_id = 'demo-jordan'")
    r = client.post("/api/v1/demo-users/jordan/sweat")
    assert r.status_code == 404 and r.json()["detail"] == sweat_demo.ERR_LOAD_FIRST
    assert client.post("/api/v1/demo-users/nobody/sweat").status_code == 422


def test_demo_route_documents_its_404():
    # The app reads openapi.json for its types, so the "load the person first" reply should be listed there.
    responses = main.app.openapi()["paths"]["/api/v1/demo-users/{person}/sweat"]["post"]["responses"]
    assert "404" in responses


def test_rehydrate_amount_only_with_sweat(sam):
    s = client.get("/api/v1/users/demo-sam/workouts/demo-legs-0929/sweat").json()
    assert s["rehydrate_ml"] == round(s["fluid_loss_ml"] * sweat.REHYDRATE_FACTOR)
    dry = client.get("/api/v1/users/demo-sam/workouts/demo-upper-0927/sweat").json()
    assert dry["rehydrate_ml"] is None
