"""
Round 6 on the server: the confidence line, the name for the greeting, "Was this helpful?" and the
"Yesterday's run" hydration panel on Today.

    python -m pytest -q tests/test_round6.py
"""

import math

import main
import pytest
from fastapi.testclient import TestClient

from app.readiness.scoring import _confidence

client = TestClient(main.app)
SAM = "/api/v1/users/demo-sam"
ALL = {"z_hrv": 0.1, "z_rhr": 0.2, "z_tst": 0.3, "z_eff": 0.4, "z_frag": 0.5}


@pytest.fixture(scope="module", autouse=True)
def demo():
    assert client.post("/api/v1/demo-users/sam").status_code == 200
    assert client.post("/api/v1/demo-users/sam/sweat").status_code == 200


@pytest.mark.parametrize(
    "missing, level, reason",
    [
        ((), "high", None),
        (("z_eff",), "medium", "Medium confidence: no sleep efficiency to compare last night."),
        (("z_eff", "z_frag"), "medium", "Medium confidence: no sleep efficiency or awakenings to compare last night."),
        (("z_hrv", "z_tst", "z_eff"), "low", "Low confidence: only 2 of 5 readings to compare last night."),
        (("z_hrv", "z_rhr"), "sleep_only", "No HRV or resting heart rate last night, so only sleep counted."),
    ],
)
def test_confidence_says_why(missing, level, reason):
    row = {k: (math.nan if k in missing else v) for k, v in ALL.items()}
    assert _confidence(row, 5 - len(missing)) == (level, reason)


def test_today_carries_the_confidence_reason():
    r = client.get(f"{SAM}/today").json()["readiness"]
    assert "confidence_reason" in r
    assert (r["confidence_reason"] is None) == (r["confidence"] == "high")


def test_name_is_tidied_and_reaches_today():
    assert client.patch(f"{SAM}/settings", json={"name": "  Sam   Lee "}).json()["name"] == "Sam Lee"
    assert client.get(f"{SAM}/today").json()["name"] == "Sam Lee"
    assert client.patch(f"{SAM}/settings", json={"name": "   "}).json()["name"] is None
    assert client.patch(f"{SAM}/settings", json={"name": "x" * 41}).status_code == 422


def test_was_this_helpful_is_saved_and_can_change():
    night = client.get(f"{SAM}/today").json()["night_date"]
    assert client.get(f"{SAM}/today").json()["helpful"] is None
    assert client.put(f"{SAM}/nights/{night}/feedback", json={"helpful": True}).json() == {
        "night_date": night,
        "helpful": True,
    }
    assert client.get(f"{SAM}/today").json()["helpful"] is True
    client.put(f"{SAM}/nights/{night}/feedback", json={"helpful": False})
    assert client.get(f"{SAM}/today").json()["helpful"] is False


def test_was_this_helpful_refuses_bad_answers():
    night = client.get(f"{SAM}/today").json()["night_date"]
    assert client.put(f"{SAM}/nights/{night}/feedback", json={"helpful": "yes"}).status_code == 422
    assert client.put(f"{SAM}/nights/2020-01-01/feedback", json={"helpful": True}).status_code == 404
    assert client.put("/api/v1/users/nobody-r6/nights/2026-09-30/feedback", json={"helpful": True}).status_code == 404


def test_today_shows_yesterdays_run():
    # The demo clock is 1 Oct 8:30 am, and the 30 Sep run picked up sweat.
    h = client.get(f"{SAM}/today").json()["hydration"]
    assert h["title"] == "Yesterday's easy run"  # the demo workout is called "Easy run"
    assert h["fluid_ml"] > 0 and h["duration_min"] > 0
    assert h["line"].startswith("Yesterday's easy run cost about")
