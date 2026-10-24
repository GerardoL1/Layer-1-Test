"""
App endpoints: Today, Trends, Profile, Settings, Update now and demo mode.

    python -m pytest -q tests
"""

from datetime import datetime, timedelta

import main
import pandas as pd
import pytest
from conftest import SAMPLE_DATA, SAMPLES
from fastapi.testclient import TestClient

from app.core import db
from app.readiness import scoring
from layer1 import config as C
from layer1 import pipeline as P

client = TestClient(main.app)


@pytest.fixture(scope="module")
def demo():
    """Load all three demo people once."""
    for person in ("sam", "alex", "jordan"):
        assert client.post(f"/api/v1/demo-users/{person}").status_code == 200
    return {
        p: P.run_pipeline(SAMPLE_DATA / SAMPLES[p], f"demo-{p}", days=None).ml_table.set_index("night_date")
        for p in ("sam", "alex", "jordan")
    }


def test_demo_today_shows_last_night(demo):
    t = client.get("/api/v1/users/demo-sam/today").json()
    assert t["now_local"] == "2026-10-01T08:30"
    assert t["night_date"] == "2026-09-30" and t["is_last_night"] and t["message"] is None
    assert t["readiness"]["placeholder"] and 0 <= t["readiness"]["score"] <= 100
    hrv = next(m for m in t["metrics"] if m["key"] == "hrv")
    assert hrv["value"] == round(demo["sam"].loc["2026-09-30", "hrv_night_ms"], 1)
    assert hrv["usual_low"] < hrv["usual_high"]
    assert t["sleep"]["total_min"] == round(demo["sam"].loc["2026-09-30", "tst_min"], 1)


def test_overreach_scores_lower_than_steady(demo):
    sam = client.get("/api/v1/users/demo-sam/today").json()["readiness"]
    alex = client.get("/api/v1/users/demo-alex/today").json()
    assert alex["readiness"]["score"] < sam["score"]
    assert alex["readiness"]["status"] == "low"
    rhr = next(m for m in alex["metrics"] if m["key"] == "rhr")
    assert rhr["direction"] == "worse"  # resting HR climbed during the hard block


def test_readiness_placeholder_math():
    row = {"z_hrv": 1.0, "z_rhr": -1.0, "z_tst": 0.0, "z_eff": float("nan"), "z_frag": 1.0, "usable_sleep": True}
    # (1 + 1 + 0 - 1) / 4 = 0.25 -> 50 + 2.5 = 52.5 -> 52 (rounded to even)
    assert scoring.readiness(row) == {"score": 52, "status": "moderate", "z_count": 4, "placeholder": True}
    assert scoring.readiness({"usable_sleep": True})["status"] == "building_baseline"
    assert scoring.readiness({"z_hrv": -9.0})["score"] == 0


@pytest.mark.parametrize("n", [14, 28, 90])
def test_trends_ranges(demo, n):
    rows = client.get("/api/v1/users/demo-jordan/trends", params={"nights": n}).json()["rows"]
    assert rows[-1]["night_date"] == "2026-09-30"
    # Every calendar night up to last night gets a row, even jordan's missed 30 Sep.
    first = pd.Timestamp(demo["jordan"].index[0])
    assert len(rows) == min(n, (pd.Timestamp("2026-09-30") - first).days + 1)
    missing = [r for r in rows if not r["usable_sleep"]]
    assert missing and all(r["quality_notes"] for r in missing)  # jordan has gaps, and they say why


def test_trends_rejects_other_ranges(demo):
    assert client.get("/api/v1/users/demo-sam/trends", params={"nights": 7}).status_code == 422


def test_profile(demo):
    p = client.get("/api/v1/users/demo-sam/profile").json()
    assert p["nights_total"] == len(demo["sam"])
    assert p["last_night"] == "2026-09-30"
    assert any("Apple Watch" in s for s in p["sources"])
    hrv = next(u for u in p["usual_ranges"] if u["key"] == "hrv")
    assert hrv["baseline_nights"] >= 7 and hrv["usual_low"] < hrv["usual_high"]


def test_settings_round_trip_and_validation():
    user = "settings_user"
    r = client.patch(
        f"/api/v1/users/{user}/settings",
        json={
            "timezone": "America/Chicago",
            "update_time": "7:5",
            "age": 21,
            "training": "strength",
            "training_days": [4, 0, 2, 2],
            "units": "imperial",
        },
    )
    assert r.status_code == 200
    assert r.json() == {
        "timezone": "America/Chicago",
        "update_time": "07:05",
        "age": 21,
        "training": "strength",
        "training_days": [0, 2, 4],
        "units": "imperial",
        "weight_kg": None,
    }
    # Only the fields sent change.
    assert client.patch(f"/api/v1/users/{user}/settings", json={"age": 22}).json()["update_time"] == "07:05"
    for bad in (
        {"timezone": "Mars/Base"},
        {"update_time": "25:00"},
        {"age": 5},
        {"training_days": [7]},
        {"units": "stones"},
    ):
        assert client.patch(f"/api/v1/users/{user}/settings", json=bad).status_code == 422


def test_unknown_user_is_404():
    for path in ("today", "profile", "settings"):
        assert client.get(f"/api/v1/users/nobody/{path}").status_code == 404
    assert client.post("/api/v1/users/nobody/processing-runs").status_code == 404


def test_update_now_from_the_app():
    """Before the update time last night waits. After waking, Update now processes it."""
    user = "tapper"
    recs, _ = P.load_export(SAMPLE_DATA / SAMPLES["sam"], days=None)
    day = recs["start_local"].min().date() + timedelta(days=10)
    night = day - timedelta(days=1)
    sleep = recs[recs["stage"].notna() & (recs["start_local"].dt.date == night) & (recs["start_local"].dt.hour >= 18)]
    woke = recs[
        recs["stage"].notna()
        & (recs["start_local"] >= sleep["start_local"].min())
        & (recs["start_local"] <= pd.Timestamp(day) + pd.Timedelta(hours=14))
    ]["end_local"].max()
    # Update now needs the sleep to have been over for a while (UPDATE_NOW_QUIET_MIN).
    clock = (woke + pd.Timedelta(minutes=C.UPDATE_NOW_QUIET_MIN + 10)).to_pydatetime()
    assert clock.hour < 8

    from app.services.apple_export import import_export

    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, clock.isoformat()))
        import_export(SAMPLE_DATA / SAMPLES["sam"], conn, user)
        # Keep only what had arrived by the clock time.
        cut = int((clock - datetime(1970, 1, 1)).total_seconds() * 1000) + 7 * 3600 * 1000
        conn.execute("DELETE FROM samples WHERE user_id = ? AND end_ms > ?", (user, cut))
        conn.execute("DELETE FROM sleep_stages WHERE user_id = ? AND end_ms > ?", (user, cut))

    t = client.get(f"/api/v1/users/{user}/today").json()
    assert t["night_date"] == (night - timedelta(days=1)).isoformat()
    assert t["can_update_now"] and "Update now" in t["message"]
    r = client.post(f"/api/v1/users/{user}/processing-runs").json()
    assert r["processed"] and r["new_nights"] == [night.isoformat()]
    t = client.get(f"/api/v1/users/{user}/today").json()
    assert t["night_date"] == night.isoformat() and t["is_last_night"] and not t["can_update_now"]
    assert not client.post(f"/api/v1/users/{user}/processing-runs").json()["processed"]


def test_demo_reload_starts_fresh(demo):
    with db.connect() as conn:
        conn.execute("UPDATE users SET update_time = '11:00' WHERE user_id = 'demo-sam'")
    client.post("/api/v1/demo-users/sam")
    assert client.get("/api/v1/users/demo-sam/settings").json()["update_time"] == "08:00"
    assert client.post("/api/v1/demo-users/someone").status_code == 422


def test_today_has_deltas_awakenings_and_placeholder_text(demo):
    t = client.get("/api/v1/users/demo-alex/today").json()
    rows = {m["key"]: m for m in t["metrics"]}
    assert (
        rows["hrv"]["usual_mean"] and rows["hrv"]["usual_low"] < rows["hrv"]["usual_mean"] < rows["hrv"]["usual_high"]
    )
    assert rows["awakenings"]["value"] == demo["alex"].loc["2026-09-30", "awakenings"]
    assert t["verdict"] == "Take a recovery day." and t["text_placeholder"]
    assert "resting heart rate" in t["reason"] and t["reason"].endswith("an early night.")


def test_trend_summaries(demo):
    s = client.get("/api/v1/users/demo-alex/trends", params={"nights": 14}).json()["summaries"]
    assert set(s) == {"readiness", "hrv", "rhr", "sleep", "efficiency"}
    assert "Low" in s["readiness"]
    assert s["rhr"].startswith("Above your usual range")
    assert "less sleep" in s["sleep"]


def test_explain_templates():
    from app.readiness import explain

    verdict, reason = explain.today_text("building_baseline", [], 3, 7)
    assert verdict == "Still learning your normal." and "3 of 7" in reason
    _, reason = explain.today_text("ready", [{"key": "hrv", "direction": "usual"}], 20, 7)
    assert reason == "Your numbers are within your usual range. Your body looks recovered."
    _, reason = explain.today_text(
        "low", [{"key": "hrv", "direction": "worse"}, {"key": "sleep", "direction": "worse"}], 20, 7
    )
    assert reason.startswith("Your HRV is below your usual and you slept less than usual.")
    rows = [{"readiness": {"score": s, "status": st}} for s, st in [(80, "ready")] * 5 + [(30, "low")] * 3]
    assert explain.readiness_summary(rows) == "Slid from Ready into Low over the last 3 nights."


def test_summaries_name_the_latest_night_with_data():
    from app.readiness import explain

    def row(date, score, status, value):
        band = {"value": value, "usual_low": 40, "usual_high": 60}
        return {"night_date": date, "readiness": {"score": score, "status": status}, "hrv": band}

    rows = [row(f"2026-09-{d}", 55, "moderate", 30) for d in range(20, 30)]
    rows.append(row("2026-09-30", None, "no_data", None))  # last night: nothing recorded
    assert explain.readiness_summary(rows) == "Moderate for the 10 nights to Sep 29."
    assert explain.band_summary(rows, "hrv") == "Below your usual range for the 10 nights to Sep 29."


def test_update_now_says_when_last_night_is_already_done(demo):
    r = client.post("/api/v1/users/demo-sam/processing-runs").json()
    assert r["processed"] is False and r["message"] == "Last night is already up to date."
