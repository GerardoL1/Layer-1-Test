"""
App endpoints: Today, Trends, Profile, Settings, Update now and demo mode.

    python -m pytest -q tests
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import api
import db
import main
import pipeline as P
from conftest import SAMPLE_DATA, SAMPLES

client = TestClient(main.app)


@pytest.fixture(scope="module")
def demo():
    """Load all three demo people once."""
    for person in ("sam", "alex", "jordan"):
        assert client.post(f"/api/demo/{person}").status_code == 200
    return {p: P.run_pipeline(SAMPLE_DATA / SAMPLES[p], f"demo-{p}", days=None).ml_table.set_index("night_date")
            for p in ("sam", "alex", "jordan")}


def test_demo_today_shows_last_night(demo):
    t = client.get("/api/today", params={"user_id": "demo-sam"}).json()
    assert t["now_local"] == "2026-10-01T08:30"
    assert t["night_date"] == "2026-09-30" and t["is_last_night"] and t["message"] is None
    assert t["readiness"]["placeholder"] and 0 <= t["readiness"]["score"] <= 100
    hrv = next(m for m in t["metrics"] if m["key"] == "hrv")
    assert hrv["value"] == round(demo["sam"].loc["2026-09-30", "hrv_night_ms"], 1)
    assert hrv["usual_low"] < hrv["usual_high"]
    assert t["sleep"]["total_min"] == round(demo["sam"].loc["2026-09-30", "tst_min"], 1)


def test_overreach_scores_lower_than_steady(demo):
    sam = client.get("/api/today", params={"user_id": "demo-sam"}).json()["readiness"]
    alex = client.get("/api/today", params={"user_id": "demo-alex"}).json()
    assert alex["readiness"]["score"] < sam["score"]
    assert alex["readiness"]["status"] == "low"
    rhr = next(m for m in alex["metrics"] if m["key"] == "rhr")
    assert rhr["direction"] == "worse"   # resting HR climbed during the hard block


def test_readiness_placeholder_math():
    row = {"z_hrv": 1.0, "z_rhr": -1.0, "z_tst": 0.0, "z_eff": float("nan"), "z_frag": 1.0, "usable_sleep": True}
    # (1 + 1 + 0 - 1) / 4 = 0.25 -> 50 + 2.5 = 52.5 -> 52 (rounded to even)
    assert api.readiness(row) == {"score": 52, "status": "moderate", "z_count": 4, "placeholder": True}
    assert api.readiness({"usable_sleep": True})["status"] == "building_baseline"
    assert api.readiness({"z_hrv": -9.0})["score"] == 0


@pytest.mark.parametrize("n", [14, 28, 90])
def test_trends_ranges(demo, n):
    rows = client.get("/api/trends", params={"user_id": "demo-jordan", "nights": n}).json()["rows"]
    assert rows[-1]["night_date"] == "2026-09-30"
    # Every calendar night up to last night gets a row, even jordan's missed 30 Sep.
    first = pd.Timestamp(demo["jordan"].index[0])
    assert len(rows) == min(n, (pd.Timestamp("2026-09-30") - first).days + 1)
    missing = [r for r in rows if not r["usable_sleep"]]
    assert missing and all(r["quality_notes"] for r in missing)   # jordan has gaps, and they say why


def test_trends_rejects_other_ranges(demo):
    assert client.get("/api/trends", params={"user_id": "demo-sam", "nights": 7}).status_code == 422


def test_profile(demo):
    p = client.get("/api/profile", params={"user_id": "demo-sam"}).json()
    assert p["nights_total"] == len(demo["sam"])
    assert p["last_night"] == "2026-09-30"
    assert any("Apple Watch" in s for s in p["sources"])
    hrv = next(u for u in p["usual_ranges"] if u["key"] == "hrv")
    assert hrv["baseline_nights"] >= 7 and hrv["usual_low"] < hrv["usual_high"]


def test_settings_round_trip_and_validation():
    user = "settings_user"
    r = client.put("/api/settings", params={"user_id": user},
                   json={"timezone": "America/Chicago", "update_time": "7:5", "age": 21,
                         "training": "strength", "training_days": [4, 0, 2, 2], "units": "imperial"})
    assert r.status_code == 200
    assert r.json() == {"timezone": "America/Chicago", "update_time": "07:05", "age": 21, "training": "strength",
                        "training_days": [0, 2, 4], "units": "imperial"}
    # Only the fields sent change.
    assert client.put("/api/settings", params={"user_id": user}, json={"age": 22}).json()["update_time"] == "07:05"
    for bad in ({"timezone": "Mars/Base"}, {"update_time": "25:00"}, {"age": 5},
                {"training_days": [7]}, {"units": "stones"}):
        assert client.put("/api/settings", params={"user_id": user}, json=bad).status_code == 422


def test_unknown_user_is_404():
    for path in ("/api/today", "/api/profile", "/api/settings"):
        assert client.get(path, params={"user_id": "nobody"}).status_code == 404
    assert client.post("/api/update-now", params={"user_id": "nobody"}).status_code == 404


def test_update_now_from_the_app():
    """Before the update time last night waits. After waking, Update now processes it."""
    user = "tapper"
    recs, _ = P.load_export(SAMPLE_DATA / SAMPLES["sam"], days=None)
    day = recs["start_local"].min().date() + timedelta(days=10)
    night = day - timedelta(days=1)
    sleep = recs[recs["stage"].notna() & (recs["start_local"].dt.date == night)
                 & (recs["start_local"].dt.hour >= 18)]
    woke = recs[recs["stage"].notna() & (recs["start_local"] >= sleep["start_local"].min())
                & (recs["start_local"] <= pd.Timestamp(day) + pd.Timedelta(hours=14))]["end_local"].max()
    clock = (woke + pd.Timedelta(minutes=10)).to_pydatetime()
    assert clock.hour < 8

    from apple_export import import_export
    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, clock.isoformat()))
        import_export(SAMPLE_DATA / SAMPLES["sam"], conn, user)
        # Keep only what had arrived by the clock time.
        cut = int((clock - datetime(1970, 1, 1)).total_seconds() * 1000) + 7 * 3600 * 1000
        conn.execute("DELETE FROM samples WHERE user_id = ? AND end_ms > ?", (user, cut))
        conn.execute("DELETE FROM sleep_stages WHERE user_id = ? AND end_ms > ?", (user, cut))

    t = client.get("/api/today", params={"user_id": user}).json()
    assert t["night_date"] == (night - timedelta(days=1)).isoformat()
    assert t["can_update_now"] and "Update now" in t["message"]
    r = client.post("/api/update-now", params={"user_id": user}).json()
    assert r["processed"] and r["new_nights"] == [night.isoformat()]
    t = client.get("/api/today", params={"user_id": user}).json()
    assert t["night_date"] == night.isoformat() and t["is_last_night"] and not t["can_update_now"]
    assert not client.post("/api/update-now", params={"user_id": user}).json()["processed"]


def test_demo_reload_starts_fresh(demo):
    with db.connect() as conn:
        conn.execute("UPDATE users SET update_time = '11:00' WHERE user_id = 'demo-sam'")
    client.post("/api/demo/sam")
    assert client.get("/api/settings", params={"user_id": "demo-sam"}).json()["update_time"] == "08:00"
    assert client.post("/api/demo/someone").status_code == 422
