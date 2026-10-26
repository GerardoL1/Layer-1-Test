"""
Layer 3 on the server: Nix import (preview, then save), manual entry, matching to a workout,
the more precise data winning, the Hydration line, the Trends chart and the daily ML table.

    python -m pytest -q tests/test_sweat.py
"""

from datetime import date, datetime, timezone

import main
import pytest
from fastapi.testclient import TestClient

from app.core import db, limits
from app.core.urls import USER
from app.services import sweat
from layer3 import config as C3
from layer3 import samples as S

client = TestClient(main.app)
CDT = -300  # minutes, US Central summer time
HOUR = 3600 * 1000

METRIC_SWEAT = S.sample_path("nix_metric_sweat.xlsx").read_bytes()  # Oct 20, 2026, 6 to 7 pm, 682 ml
METRIC_DRY = S.sample_path("nix_metric_no_sweat.xlsx").read_bytes()  # Oct 25, 2026, 2:55 to 5:08 pm
CUSTOMARY_DRY = S.sample_path("nix_customary_no_sweat.xlsx").read_bytes()  # the same workout in oz


def local_ms(y, mo, d, h, mi, offset=CDT):
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000) - offset * 60 * 1000


SWEAT_START = local_ms(2026, 10, 20, 18, 0)
SWEAT_END = local_ms(2026, 10, 20, 19, 0)


def person(name, **settings):
    settings.setdefault("timezone", "America/Chicago")
    r = client.patch(f"/api/v1/users/{name}/settings", json={"units": "metric", **settings})
    assert r.status_code == 200, r.text
    return f"/api/v1/users/{name}"


def workout(u, wid, start, end, type_="Run"):
    body = {"id": wid, "start_ms": start, "end_ms": end, "start_tz_min": CDT, "end_tz_min": CDT, "type": type_}
    r = client.post(f"{u}/workouts", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def preview(u, data=METRIC_SWEAT, **form):
    return client.post(f"{u}/sweat/nix/preview", files={"file": ("workout.xlsx", data)}, data=form)


def save(u, data=METRIC_SWEAT, **form):
    return client.post(f"{u}/sweat/nix", files={"file": ("workout.xlsx", data)}, data=form)


def count(table, user_id):
    with db.connect() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user_id,)).fetchone()[0]


# ---------------------------------------------------------------- preview and save


def test_preview_matches_the_overlapping_workout_and_saves_nothing():
    u = person("sw_preview")
    workout(u, "run1", SWEAT_START - 5 * 60000, SWEAT_END + 5 * 60000)
    workout(u, "other", SWEAT_START - 30 * HOUR, SWEAT_START - 29 * HOUR)
    r = preview(u)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["matched_workout"]["id"] == "run1"
    s = p["session"]
    assert s["start_ms"] == SWEAT_START and s["end_ms"] == SWEAT_END
    assert s["start_tz_min"] == CDT and s["start_local"] == "2026-10-20T18:00"
    assert s["fluid_loss_ml"] == 682 and s["sodium_mg"] == 540
    assert s["sweat_rate_l_h"] == pytest.approx(0.682)
    assert s["sweat_detected"] is True and s["unit_system"] == "metric"
    assert s["workout_id"] == "run1"
    assert p["existing"] == "none"
    assert count("sweat_sessions", "sw_preview") == 0
    assert count("sweat_minutes", "sw_preview") == 0


def test_save_links_to_the_matched_workout():
    u = person("sw_save", weight_kg=70)
    workout(u, "run1", SWEAT_START, SWEAT_END)
    r = save(u)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["workout_id"] == "run1" and s["source"] == "nix"
    assert s["fluid_loss_pct_body_weight"] == pytest.approx(682 / 70000 * 100, abs=0.01)
    assert s["imported_at_ms"] is not None
    assert client.get(f"{u}/workouts/run1/sweat").json()["fluid_loss_ml"] == 682
    assert count("sweat_minutes", "sw_save") == 60
    listed = client.get(f"{u}/sweat/sessions", params={"days": 3650}).json()  # counted back from the real clock
    assert [x["workout_id"] for x in listed] == ["run1"]


def test_no_match_lists_nearby_workouts_closest_first():
    u = person("sw_nearby")
    workout(u, "two_days_before", SWEAT_START - 48 * HOUR, SWEAT_START - 47 * HOUR)
    workout(u, "day_after", SWEAT_START + 20 * HOUR, SWEAT_START + 21 * HOUR)
    workout(u, "month_before", SWEAT_START - 30 * 24 * HOUR, SWEAT_START - 30 * 24 * HOUR + HOUR)
    p = preview(u).json()
    assert p["matched_workout"] is None
    assert p["session"]["workout_id"] is None
    assert [w["id"] for w in p["nearby_workouts"]] == ["day_after", "two_days_before"]


def test_no_match_and_no_choice_is_refused():
    u = person("sw_nochoice")
    r = save(u)
    assert r.status_code == 400
    assert r.json()["detail"] == sweat.ERR_PICK_WORKOUT
    assert count("sweat_sessions", "sw_nochoice") == 0


def test_save_to_a_picked_workout():
    u = person("sw_pick")
    workout(u, "picked", SWEAT_START - 48 * HOUR, SWEAT_START - 47 * HOUR)
    r = save(u, workout_id="picked")
    assert r.status_code == 200 and r.json()["workout_id"] == "picked"
    assert save(u, workout_id="nope").status_code == 404


def test_save_as_a_new_workout_only_once():
    u = person("sw_new")
    first = save(u, new_workout="true")
    assert first.status_code == 200, first.text
    wid = first.json()["workout_id"]
    assert wid == f"nix-{SWEAT_START}"
    w = client.get(f"{u}/workouts/{wid}").json()
    assert (w["source"], w["type"], w["start_ms"], w["end_ms"]) == ("manual", "Running", SWEAT_START, SWEAT_END)
    assert save(u, new_workout="true").status_code == 200  # sending again can't make a second workout
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM workouts WHERE user_id = 'sw_new'").fetchone()[0] == 1
    assert count("sweat_sessions", "sw_new") == 1


# ---------------------------------------------------------------- time zones


def test_time_zone_setting_is_used_for_the_file_times():
    u = person("sw_tz_tokyo", timezone="Asia/Tokyo")
    s = preview(u).json()["session"]
    assert s["start_tz_min"] == 540
    assert s["start_local"] == "2026-10-20T18:00"
    assert s["start_ms"] == local_ms(2026, 10, 20, 18, 0, offset=540)


def test_without_a_time_zone_the_newest_reading_offset_is_used():
    u = person("sw_tz_reading", timezone=None)
    with db.connect() as conn:
        reading = ("hr1", "heart_rate", 60.0, SWEAT_START, SWEAT_START, -240, "W")
        db.add_readings(conn, "sw_tz_reading", samples=[reading])
    assert preview(u, tz_offset_min="60").json()["session"]["start_tz_min"] == -240


def test_without_either_the_phone_offset_is_used():
    u = person("sw_tz_phone", timezone=None)
    assert preview(u, tz_offset_min="-420").json()["session"]["start_tz_min"] == -420
    r = preview(u)
    assert r.status_code == 400 and r.json()["detail"] == sweat.ERR_NO_TIME_ZONE
    assert preview(u, tz_offset_min="9999").status_code == 400


# ---------------------------------------------------------------- the more precise data wins


def test_metric_replaces_customary_but_not_the_other_way_round():
    u = person("sw_precise")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000, "Lifting")
    assert save(u, CUSTOMARY_DRY).json()["unit_system"] == "customary"

    p = preview(u, METRIC_DRY).json()
    assert p["existing"] == "replaces_less_precise"
    assert save(u, METRIC_DRY).json()["unit_system"] == "metric"

    p = preview(u, CUSTOMARY_DRY).json()
    assert p["existing"] == "keeps_more_precise"
    r = save(u, CUSTOMARY_DRY)
    assert r.status_code == 409 and r.json()["detail"] == sweat.ERR_MORE_PRECISE
    assert client.get(f"{u}/workouts/lift/sweat").json()["unit_system"] == "metric"
    assert count("sweat_sessions", "sw_precise") == 1


def test_the_same_file_twice_changes_nothing():
    u = person("sw_twice")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    first = save(u).json()
    assert preview(u).json()["existing"] == "same"
    second = save(u).json()
    assert {k: v for k, v in first.items() if k != "imported_at_ms"} == {
        k: v for k, v in second.items() if k != "imported_at_ms"
    }
    assert count("sweat_sessions", "sw_twice") == 1 and count("sweat_minutes", "sw_twice") == 60


# ---------------------------------------------------------------- manual entry


def manual(u, wid, **body):
    return client.put(f"{u}/workouts/{wid}/sweat", json=body)


def test_manual_entry_then_nix_replaces_it():
    u = person("sw_manual")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    r = manual(u, "run1", fluid_loss_ml=900, sodium_mg=640)
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["source"], s["unit_system"], s["sweat_detected"]) == ("manual", "manual", True)
    assert (s["start_ms"], s["end_ms"], s["fluid_loss_ml"], s["sodium_mg"]) == (SWEAT_START, SWEAT_END, 900, 640)
    assert s["sweat_rate_l_h"] is None

    assert preview(u).json()["existing"] == "replaces_less_precise"
    assert save(u).json()["source"] == "nix"
    assert count("sweat_sessions", "sw_manual") == 1

    r = manual(u, "run1", fluid_loss_ml=500)
    assert r.status_code == 409 and r.json()["detail"] == sweat.ERR_MORE_PRECISE


def test_manual_entry_again_replaces_the_earlier_one():
    u = person("sw_manual2")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    manual(u, "run1", fluid_loss_ml=900)
    assert manual(u, "run1", fluid_loss_ml=750, sweat_rate_l_h=0.75).json()["fluid_loss_ml"] == 750
    assert count("sweat_sessions", "sw_manual2") == 1


@pytest.mark.parametrize(
    "body",
    [
        {"fluid_loss_ml": True},
        {"fluid_loss_ml": "900"},
        {"fluid_loss_ml": -1},
        {"fluid_loss_ml": 40000},
        {"fluid_loss_ml": 900, "sodium_mg": -5},
        {"fluid_loss_ml": 900, "sweat_rate_l_h": 50},
        {"sodium_mg": 300},
        {"fluid_loss_ml": 900, "extra": 1},
    ],
)
def test_manual_entry_is_checked(body):
    u = person("sw_manual_bad")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    assert manual(u, "run1", **body).status_code == 422


def test_manual_entry_refuses_nan_and_infinity():
    u = person("sw_manual_nan")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    for raw in ('{"fluid_loss_ml": NaN}', '{"fluid_loss_ml": Infinity}'):
        r = client.put(f"{u}/workouts/run1/sweat", content=raw, headers={"content-type": "application/json"})
        assert r.status_code == 422


def test_manual_entry_needs_a_real_workout():
    u = person("sw_manual_404")
    assert manual(u, "nope", fluid_loss_ml=900).status_code == 404
    assert client.get(f"{u}/workouts/nope/sweat").status_code == 404


def test_workout_without_sweat_data():
    u = person("sw_none")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    r = client.get(f"{u}/workouts/run1/sweat")
    assert r.status_code == 404 and r.json()["detail"] == sweat.ERR_NO_SWEAT_DATA


# ---------------------------------------------------------------- no sweat, errors, unknown people


def test_no_sweat_session_is_stored_with_missing_salt():
    u = person("sw_dry", weight_kg=73)
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    s = save(u, METRIC_DRY).json()
    assert s["sweat_detected"] is False
    assert s["sodium_mg"] is None and s["electrolytes_mg"] is None and s["sweat_composition_mg_l"] is None
    assert s["fluid_loss_pct_body_weight"] is None  # breathing loss isn't sweat data
    assert s["warnings"] == [C3.WARN_NO_SWEAT]
    with db.connect() as conn:
        q = "SELECT COUNT(*) FROM sweat_minutes WHERE user_id = 'sw_dry' AND total_sodium_mg IS NOT NULL"
        assert conn.execute(q).fetchone()[0] == 0
    assert count("sweat_minutes", "sw_dry") == 133


@pytest.mark.parametrize(
    "name, message_start",
    [
        ("broken_pdf_renamed.xlsx", "This is a PDF"),
        ("broken_unknown_unit.xlsx", "We don't recognise the unit in 'Total Fluid Loss (gal)'"),
        ("broken_missing_sheet.xlsx", "This file has no 'Timeseries Data' sheet"),
    ],
)
def test_unreadable_files_get_a_plain_400(name, message_start):
    u = person("sw_bad")
    data = S.sample_path(name).read_bytes()
    for send in (preview, save):
        r = send(u, data)
        assert r.status_code == 400 and r.json()["detail"].startswith(message_start)


def test_a_file_dated_in_the_future_is_refused():
    u = person("sw_future")
    t = S.sweat_workout()
    t.start, t.end = "Jan 1, 2099 at 6:00 PM", "Jan 1, 2099 at 7:00 PM"
    r = preview(u, S.nix_export(t, "metric"))
    assert r.status_code == 400 and "in the future" in r.json()["detail"]


def test_unknown_person():
    r = preview("/api/v1/users/sw_nobody")
    assert r.status_code == 404


def test_weight_suggestion_only_when_settings_have_none():
    u = person("sw_weight")
    assert preview(u).json()["weight_suggestion_kg"] == 70
    client.patch(f"{u}/settings", json={"weight_kg": 80})
    assert preview(u).json()["weight_suggestion_kg"] is None


def test_oversized_upload_gets_413(monkeypatch):
    monkeypatch.setitem(limits.LIMITS_BY_PATH, USER + "/sweat/nix/preview", 1000)
    r = preview(person("sw_big"))
    assert r.status_code == 413


def test_upload_limits_are_set():
    for path in ("/sweat/nix/preview", "/sweat/nix"):
        assert limits.limit_for(f"/api/v1/users/sam{path}") == (USER + path, limits.MAX_NIX_UPLOAD_BYTES)
    assert limits.limit_for("/api/v1/users/sam/workouts/w1/sweat") == (
        USER + "/workouts/{workout_id}/sweat",
        limits.MAX_SMALL_JSON_BYTES,
    )


# ---------------------------------------------------------------- Hydration line, Trends chart, daily ML table


def test_hydration_line_for_the_night_after_a_sweaty_workout():
    u = person("sw_hyd")
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    save(u)
    line = sweat.hydration_line("sw_hyd", date(2026, 10, 20))
    assert line == "Yesterday's run cost about 0.7 L of sweat. Drink a little more than usual this morning."
    assert sweat.hydration_line("sw_hyd", date(2026, 10, 21)) is None
    assert sweat.hydration_line("sw_hyd", date(2026, 10, 19)) is None


def test_hydration_line_in_imperial_units():
    u = person("sw_hyd_us", units="imperial")
    client.patch(f"{u}/settings", json={"units": "imperial"})
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    save(u)
    assert sweat.hydration_line("sw_hyd_us", date(2026, 10, 20)) == (
        "Yesterday's run cost about 23 oz of sweat. Drink a little more than usual this morning."
    )


def test_no_hydration_line_without_sweat():
    u = person("sw_hyd_dry")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    save(u, METRIC_DRY)
    assert sweat.hydration_line("sw_hyd_dry", date(2026, 10, 25)) is None
    assert sweat.hydration_line("sw_unknown_person", date(2026, 10, 25)) is None


def test_two_workouts_in_one_day():
    u = person("sw_hyd_two")
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    workout(u, "lift", SWEAT_START - 6 * HOUR, SWEAT_START - 5 * HOUR, "Lifting")
    save(u)
    manual(u, "lift", fluid_loss_ml=400)
    line = sweat.hydration_line("sw_hyd_two", date(2026, 10, 20))
    assert line == "Yesterday's workouts cost about 1.1 L of sweat. Drink a little more than usual this morning."


def fix_clock(user_id, text):
    with db.connect() as conn:
        conn.execute("UPDATE users SET clock_local = ? WHERE user_id = ?", (text, user_id))


def test_daily_sweat_for_the_trends_chart():
    u = person("sw_daily")
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    save(u)
    fix_clock("sw_daily", "2026-10-26T08:30:00")
    r = client.get(f"{u}/sweat/daily", params={"nights": 14})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["nights"] == 14 and d["placeholder"] is True
    days = d["days"]
    assert len(days) == 14
    assert days[0]["date"] == "2026-10-12" and days[-1]["date"] == "2026-10-25"
    by_date = {x["date"]: x for x in days}
    assert by_date["2026-10-20"]["fluid_loss_ml"] == 682 and by_date["2026-10-20"]["has_sweat_data"] is True
    assert by_date["2026-10-21"]["fluid_loss_ml"] is None and by_date["2026-10-21"]["has_sweat_data"] is False
    assert "0.7 L" in d["summary"]
    assert client.get(f"{u}/sweat/daily", params={"nights": 15}).status_code == 422


def test_daily_ml_table():
    u = person("sw_table", weight_kg=70)
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    save(u)
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    save(u, METRIC_DRY)
    with db.connect() as conn:
        t = sweat.daily_sweat_table(conn, "sw_table")
    assert list(t.columns) == sweat.DAILY_COLUMNS
    rows = {r["night_date"]: r for r in t.to_dict("records")}
    oct20, oct21 = rows["2026-10-20"], rows["2026-10-21"]
    assert oct20["person_id"] == "sw_table" and oct20["has_sweat_data"] is True
    assert oct20["fluid_loss_pct_bw_1d"] == pytest.approx(682 / 70000 * 100, abs=0.001)
    assert oct20["sodium_mg_1d"] == 540
    assert oct21["fluid_loss_pct_bw_1d"] != oct21["fluid_loss_pct_bw_1d"]  # NaN: nothing that day, never 0
    assert oct21["fluid_loss_pct_bw_2d"] == pytest.approx(682 / 70000 * 100, abs=0.001)
    oct25 = rows["2026-10-25"]
    assert oct25["has_sweat_data"] is False  # breathing loss only
    assert oct25["sodium_mg_1d"] != oct25["sodium_mg_1d"]
