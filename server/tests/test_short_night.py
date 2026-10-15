"""
A recorded but short night (scenario 04's 2.5 h night) is "short_sleep" with its own wording,
not "No sleep recorded". A night with no sleep data at all stays "no_data".

    python -m pytest -q tests/test_short_night.py
"""

from datetime import date, datetime, timedelta

import api
import db
import explain
import main
import processing
from apple_export import import_export
from conftest import ROOT
from fastapi.testclient import TestClient

from agent_testing.scenario_builder import build, load_spec

client = TestClient(main.app)
SCENARIOS = ROOT / "preprocessing" / "agent_testing" / "scenarios"


def load_scenario(name: str, user: str, tmp_path, night: int) -> tuple[dict, str]:
    """Import a scenario through the server with the clock on the morning after the given night."""
    sc = build(load_spec(SCENARIOS / f"{name}.json"))
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(sc.export_zip())
    night_date = sc.truth["nights"][night - 1]["night_date"]
    clock = datetime.combine(date.fromisoformat(night_date) + timedelta(days=1), datetime.min.time()).replace(hour=9)
    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, clock.isoformat()))
        import_export(zip_path, conn, user)
    processing.process_user(user, force=True)
    return sc.truth["nights"][night - 1], night_date


def test_short_night_gets_its_own_status_and_wording(tmp_path):
    truth, night_date = load_scenario("04_short_and_late_nights", "short", tmp_path, night=12)
    t = client.get("/api/today", params={"user_id": "short"}).json()
    assert t["night_date"] == night_date and t["is_last_night"]
    assert t["readiness"]["status"] == "short_sleep" and t["readiness"]["score"] is None
    assert t["verdict"] == "Short night."
    assert t["reason"] == (
        f"You slept {explain.sleep_length(truth['tst_min'])}, too little to compare with your usual. Keep today light."
    )
    assert t["reason"].startswith("You slept 2 h 30 min")
    assert "No sleep recorded" not in t["verdict"]


def test_short_night_stays_out_of_the_baselines(tmp_path):
    _, night_date = load_scenario("04_short_and_late_nights", "short_base", tmp_path, night=14)
    with db.connect() as conn:
        nights = processing.load_nights(conn, "short_base").set_index("night_date")
    short = nights.loc[date.fromisoformat(night_date) - timedelta(days=2)]
    assert short["flag_short_sleep"] and not short["usable_sleep"]
    # Two nights later the TST baseline still counts only usable nights, so the short one is left out.
    after = nights.loc[date.fromisoformat(night_date)]
    usable_before = nights[(nights.index < date.fromisoformat(night_date))]["usable_sleep"].sum()
    assert after["tst_min_base_n"] == usable_before


def test_night_without_sleep_is_still_no_data(tmp_path):
    _, night_date = load_scenario("03_missed_nights_and_hrv", "missed", tmp_path, night=10)
    t = client.get("/api/today", params={"user_id": "missed"}).json()
    assert t["night_date"] == night_date
    assert t["readiness"]["status"] == "no_data"
    assert t["verdict"] == "No sleep recorded for this night."


def test_readiness_status_rules():
    assert api.readiness({"usable_sleep": True})["status"] == "building_baseline"
    assert api.readiness({"usable_sleep": False, "tst_min": 150.0, "flag_short_sleep": True})["status"] == "short_sleep"
    assert (
        api.readiness({"usable_sleep": False, "tst_min": float("nan"), "flag_short_sleep": False})["status"]
        == "no_data"
    )


def test_sleep_length_wording():
    assert explain.sleep_length(150) == "2 h 30 min"
    assert explain.sleep_length(120) == "2 h"
    assert explain.sleep_length(45.4) == "45 min"
