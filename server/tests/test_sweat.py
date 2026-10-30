"""
Layer 3 on the server: Nix import (preview, then save), manual entry, matching to a workout,
the more precise data winning, the Hydration line, the Trends chart and the daily ML table.

    python -m pytest -q tests/test_sweat.py
"""

import threading
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


def test_sodium_counts_only_when_every_sweaty_workout_has_it():
    # Same rule as Today's hydration panel: a total from some of the workouts would look complete but isn't.
    u = person("sw_sodium_rule", weight_kg=70)
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    save(u)  # Nix file with 540 mg of sodium
    noon = local_ms(2026, 10, 20, 12, 0)
    workout(u, "ride", noon, noon + 45 * 60000, "Ride")
    assert client.put(f"{u}/workouts/ride/sweat", json={"fluid_loss_ml": 400}).status_code == 200  # no sodium
    fix_clock("sw_sodium_rule", "2026-10-26T08:30:00")
    day = {x["date"]: x for x in client.get(f"{u}/sweat/daily", params={"nights": 14}).json()["days"]}["2026-10-20"]
    assert day["fluid_loss_ml"] == 1082 and day["sodium_mg"] is None
    with db.connect() as conn:
        rows = {r["night_date"]: r for r in sweat.daily_sweat_table(conn, "sw_sodium_rule").to_dict("records")}
    oct20 = rows["2026-10-20"]
    assert oct20["fluid_loss_pct_bw_1d"] == pytest.approx(1082 / 70000 * 100, abs=0.001)
    assert oct20["sodium_mg_1d"] != oct20["sodium_mg_1d"]  # NaN, not 540


# ---------------------------------------------------------------- findings from the batch 2 testing pass

CST = -360  # US Central winter time


def nix_file(start, end, duration="01:00:00", units="metric"):
    """The fake sweat workout with other times, to test clock changes."""
    t = S.sweat_workout()
    t.start, t.end, t.duration = start, end, duration
    return S.nix_export(t, units)


def workout_at(u, wid, start, end, start_tz=CDT, end_tz=CDT, type_="Run", source="manual"):
    body = {
        "id": wid,
        "start_ms": start,
        "end_ms": end,
        "start_tz_min": start_tz,
        "end_tz_min": end_tz,
        "type": type_,
        "source": source,
    }
    r = client.post(f"{u}/workouts", json=body)
    assert r.status_code == 200, r.text


def duration_warnings(session):
    return [w for w in session["warnings"] if w.startswith("The duration")]


def test_double_tap_on_save_never_fails():
    # 1. Two saves at once both saw "nothing saved yet", and the second hit the UNIQUE constraint (a 500).
    u = person("sw_race")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    quiet = TestClient(main.app, raise_server_exceptions=False)
    statuses = []

    def go(i):
        if i % 3 == 2:
            r = quiet.put(f"{u}/workouts/run1/sweat", json={"fluid_loss_ml": 900})
        else:
            r = quiet.post(f"{u}/sweat/nix", files={"file": ("w.xlsx", METRIC_SWEAT)}, data={"workout_id": "run1"})
        statuses.append(r.status_code)

    for _ in range(3):
        threads = [threading.Thread(target=go, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert set(statuses) <= {200, 409}, statuses
    assert count("sweat_sessions", "sw_race") == 1


def test_time_in_the_spring_forward_gap_is_refused():
    # 2. 2:45 AM doesn't exist on 8 Mar 2026 in Chicago, and the session was saved ending before it started.
    u = person("sw_gap")
    workout_at(u, "w", local_ms(2026, 3, 7, 20, 0, CST), local_ms(2026, 3, 7, 21, 0, CST), CST, CST)
    r = save(u, nix_file("Mar 8, 2026 at 2:45 AM", "Mar 8, 2026 at 3:10 AM", "00:25:00"), workout_id="w")
    assert r.status_code == 400
    assert r.json()["detail"] == sweat.ERR_CLOCK_GAP
    assert count("sweat_sessions", "sw_gap") == 0


def test_workout_across_the_fall_back_hour():
    # 7. 1:50 AM summer time to 1:10 AM winter time is a real 20 minutes, and was refused.
    u = person("sw_fallback")
    start = local_ms(2025, 11, 2, 1, 50, CDT)
    workout_at(u, "w", start, start + 20 * 60000, CDT, CST)
    r = save(u, nix_file("Nov 2, 2025 at 1:50 AM", "Nov 2, 2025 at 1:10 AM", "00:20:00"), workout_id="w")
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["start_tz_min"], s["end_tz_min"]) == (CDT, CST)
    assert s["end_ms"] - s["start_ms"] == 20 * 60000
    assert s["duration_min"] == 20
    assert duration_warnings(s) == []


@pytest.mark.parametrize(
    "start, end, duration",
    [
        ("Mar 9, 2025 at 1:50 AM", "Mar 9, 2025 at 3:10 AM", "00:20:00"),  # clocks went forward
        ("Nov 2, 2025 at 12:30 AM", "Nov 2, 2025 at 2:30 AM", "03:00:00"),  # clocks went back
    ],
)
def test_duration_warning_uses_the_real_times(start, end, duration):
    # 7. The reader compared local times, so a clock change looked like a wrong duration.
    s = preview(person("sw_dst_warn"), nix_file(start, end, duration)).json()["session"]
    assert duration_warnings(s) == []


def test_repeated_hour_picks_the_copy_that_matches_a_workout():
    # 7. A time in the repeated hour always meant the first (summer time) copy.
    u = person("sw_repeat")
    workout_at(u, "cst", local_ms(2025, 11, 2, 1, 10, CST), local_ms(2025, 11, 2, 1, 55, CST), CST, CST)
    p = preview(u, nix_file("Nov 2, 2025 at 1:10 AM", "Nov 2, 2025 at 1:55 AM", "00:45:00")).json()
    assert p["matched_workout"]["id"] == "cst"
    assert p["session"]["start_tz_min"] == CST


def test_early_morning_workout_counts_once():
    # 3. A workout before the update time counted for two mornings.
    u = person("sw_early", weight_kg=70)
    workout(u, "dawn", local_ms(2026, 10, 21, 5, 30), local_ms(2026, 10, 21, 6, 30), "Run")
    manual(u, "dawn", fluid_loss_ml=800)
    assert sweat.hydration_line("sw_early", date(2026, 10, 20)) == (
        "This morning's run cost about 0.8 L of sweat. Drink a little more than usual this morning."
    )
    assert sweat.hydration_line("sw_early", date(2026, 10, 21)) is None
    with db.connect() as conn:
        rows = {r["night_date"]: r for r in sweat.daily_sweat_table(conn, "sw_early").to_dict("records")}
    assert rows["2026-10-20"]["fluid_loss_pct_bw_1d"] == pytest.approx(800 / 70000 * 100, abs=0.001)
    assert rows["2026-10-21"]["fluid_loss_pct_bw_1d"] != rows["2026-10-21"]["fluid_loss_pct_bw_1d"]  # NaN


def test_late_evening_workout_counts_for_its_own_night_only():
    # 3. A workout ending after midnight also showed up the morning after next as "Yesterday's".
    u = person("sw_late")
    workout(u, "late", local_ms(2026, 10, 21, 23, 30), local_ms(2026, 10, 22, 0, 30), "Run")
    manual(u, "late", fluid_loss_ml=800)
    assert sweat.hydration_line("sw_late", date(2026, 10, 21)).startswith("Yesterday's run")
    assert sweat.hydration_line("sw_late", date(2026, 10, 22)) is None


def test_refused_save_as_new_leaves_no_workout_behind():
    # 4. The new workout was made before the precision check refused the file.
    u = person("sw_new409")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    assert save(u, METRIC_DRY).status_code == 200
    r = save(u, CUSTOMARY_DRY, new_workout="true")
    assert r.status_code == 409
    assert client.get(f"{u}/workouts/nix-{start}").status_code == 404


def test_save_as_new_never_changes_an_existing_workout():
    # 5. Saving as new overwrote a workout that already had the generated id.
    u = person("sw_new_keep")
    wid = f"nix-{SWEAT_START}"
    workout_at(u, wid, SWEAT_START, SWEAT_START + 3 * HOUR, type_="Leg day", source="apple_health")
    client.put(f"{u}/workouts/{wid}/rating", json={"effort": 7, "answered_at_ms": SWEAT_START + 4 * HOUR})
    r = save(u, new_workout="true")
    assert r.status_code == 200 and r.json()["workout_id"] == wid
    w = client.get(f"{u}/workouts/{wid}").json()
    assert (w["type"], w["source"], w["end_ms"], w["effort"]) == ("Leg day", "apple_health", SWEAT_START + 3 * HOUR, 7)


def test_upload_without_a_filename_isnt_echoed_back():
    # 6. Without a filename the file became a text field, and the 422 echoed all of it back.
    u = person("sw_noname")
    for path in ("/sweat/nix/preview", "/sweat/nix"):
        r = client.post(f"{u}{path}", files={"file": ("", METRIC_SWEAT)})
        assert r.status_code == 400 and r.json()["detail"] == sweat.ERR_NO_FILE
        assert len(r.content) < 300


def test_missing_file_gets_a_plain_message():
    r = client.post(f"{person('sw_nofile')}/sweat/nix/preview", data={"tz_offset_min": "60"})
    assert r.status_code == 400 and r.json()["detail"] == sweat.ERR_NO_FILE


def test_huge_form_field_gets_a_plain_message():
    # 6. Over 1 MB, Starlette's own "Part exceeded maximum size of 1024KB." came back.
    u = person("sw_hugefield")
    r = save(u, workout_id="x" * (2 * 1024 * 1024))
    assert r.status_code == 400 and r.json()["detail"] == sweat.ERR_BAD_FORM


@pytest.mark.parametrize("field, value", [("tz_offset_min", "abc"), ("tz_offset_min", "1.5"), ("new_workout", "maybe")])
def test_odd_form_values_get_a_plain_message(field, value):
    r = save(person("sw_oddform"), **{field: value})
    assert r.status_code == 400 and r.json()["detail"] == sweat.ERR_BAD_FORM


def test_typed_in_sweat_follows_its_workout():
    # 8. Moving the workout left the typed-in session at the old times.
    u = person("sw_moved")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    manual(u, "run1", fluid_loss_ml=900)
    workout(u, "run1", SWEAT_START - 48 * HOUR, SWEAT_END - 48 * HOUR)
    s = client.get(f"{u}/workouts/run1/sweat").json()
    assert (s["start_ms"], s["end_ms"]) == (SWEAT_START - 48 * HOUR, SWEAT_END - 48 * HOUR)
    assert sweat.hydration_line("sw_moved", date(2026, 10, 18)) is not None
    assert sweat.hydration_line("sw_moved", date(2026, 10, 20)) is None


@pytest.mark.parametrize(
    "body",
    [
        {"fluid_loss_ml": -0.0},
        {"fluid_loss_ml": 0},
        {"fluid_loss_ml": 0.04},
        {"fluid_loss_ml": 900, "sodium_mg": 0},
        {"fluid_loss_ml": 900, "sodium_mg": 0.04},
        {"fluid_loss_ml": 900, "sweat_rate_l_h": 0.00001},
    ],
)
def test_typed_in_amounts_too_small_to_be_real(body):
    # 9. These were stored as 0.0 (or -0.0) and counted as sweat data.
    u = person("sw_tiny")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    assert manual(u, "run1", **body).status_code == 422


def test_smallest_typed_in_amounts():
    u = person("sw_small_ok")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    s = manual(u, "run1", fluid_loss_ml=1, sodium_mg=1, sweat_rate_l_h=0.01).json()
    assert (s["fluid_loss_ml"], s["sodium_mg"], s["sweat_rate_l_h"]) == (1, 1, 0.01)


def test_more_precise_copy_on_another_workout_message():
    # 10. The message said "this workout" when the more precise copy was on a different one.
    u = person("sw_msg")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "a", start, start + 133 * 60000)
    workout(u, "b", start - 48 * HOUR, start - 47 * HOUR)
    save(u, METRIC_DRY, workout_id="a")
    r = save(u, CUSTOMARY_DRY, workout_id="b")
    assert r.status_code == 409
    assert r.json()["detail"] == "More precise sweat data for this session is already saved, so it was kept."


def test_unknown_person_comes_before_a_bad_file():
    # 10. Save read the file first, so an unknown person with a bad file got 400 instead of 404.
    pdf = S.sample_path("broken_pdf_renamed.xlsx").read_bytes()
    assert save("/api/v1/users/sw_nobody_at_all", pdf).status_code == 404


def test_hydration_line_keeps_capitals():
    # 10. "HIIT" became "hiit".
    u = person("sw_caps")
    workout(u, "h", SWEAT_START, SWEAT_END, "HIIT")
    manual(u, "h", fluid_loss_ml=800)
    assert sweat.hydration_line("sw_caps", date(2026, 10, 20)).startswith("Yesterday's HIIT cost")


def test_daily_with_a_broken_demo_clock():
    # 10. A garbled clock_local gave a 500.
    u = person("sw_badclock")
    fix_clock("sw_badclock", "not a time")
    assert client.get(f"{u}/sweat/daily").status_code == 200


# ---------------------------------------------------------------- findings from the batch 3b testing pass


def test_preview_for_a_chosen_workout_reports_that_workout():
    # The preview only knew about the workout the file matched, so picking another one showed the wrong note.
    u = person("sw_target")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    workout(u, "legs", SWEAT_START - 48 * HOUR, SWEAT_START - 47 * HOUR)
    manual(u, "legs", fluid_loss_ml=500)
    p = preview(u, workout_id="legs").json()
    assert p["session"]["workout_id"] == "legs"
    assert p["matched_workout"]["id"] == "run1"  # still says which workout the file's times match
    assert p["existing"] == "replaces_less_precise"
    assert p["moves_from_workout"] is None
    assert preview(u, workout_id="nope").status_code == 404


def test_preview_says_when_the_file_moves_off_another_workout():
    # Saving the same file to a second workout deletes it from the first, and nothing said so.
    u = person("sw_moves")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    workout(u, "legs", SWEAT_START - 48 * HOUR, SWEAT_START - 47 * HOUR)
    save(u, workout_id="legs")
    p = preview(u, workout_id="run1").json()
    assert p["moves_from_workout"]["id"] == "legs"
    assert p["existing"] == "replaces"
    assert preview(u, workout_id="legs").json()["moves_from_workout"] is None


def test_preview_as_a_new_workout():
    u = person("sw_target_new")
    workout(u, "legs", SWEAT_START - 48 * HOUR, SWEAT_START - 47 * HOUR)
    save(u, workout_id="legs")
    p = preview(u, new_workout="true").json()
    assert p["session"]["workout_id"] == f"nix-{SWEAT_START}"
    assert p["moves_from_workout"]["id"] == "legs"


def test_no_sweat_file_never_replaces_sweat_data():
    # Breathing-only Nix data replaced real typed-in numbers, because Nix counted as more precise.
    u = person("sw_dry_vs_typed")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    manual(u, "lift", fluid_loss_ml=900)
    assert preview(u, METRIC_DRY).json()["existing"] == "keeps_sweat_data"
    r = save(u, METRIC_DRY)
    assert r.status_code == 409 and r.json()["detail"] == sweat.ERR_KEEPS_SWEAT
    assert client.get(f"{u}/workouts/lift/sweat").json()["fluid_loss_ml"] == 900


def test_typed_in_sweat_replaces_a_no_sweat_nix_session():
    # The other way round: real numbers typed in beat a breathing-only file.
    u = person("sw_typed_vs_dry")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    save(u, METRIC_DRY)
    r = manual(u, "lift", fluid_loss_ml=900)
    assert r.status_code == 200 and r.json()["source"] == "manual"


def test_metric_no_sweat_still_replaces_customary_no_sweat():
    u = person("sw_dry_dry")
    start = local_ms(2026, 10, 25, 14, 55)
    workout(u, "lift", start, start + 133 * 60000)
    save(u, CUSTOMARY_DRY)
    assert preview(u, METRIC_DRY).json()["existing"] == "replaces_less_precise"


# ---------------------------------------------------------------- findings from the Layer 1 tab's review

DRY_START = local_ms(2026, 10, 25, 14, 55)


def test_sweat_file_compares_precision_only_with_sweat_data():
    # S4. A breathing-only Metric copy elsewhere made a Customary sweat file lose to typed-in numbers (409).
    u = person("sw_s4")
    workout(u, "w1", DRY_START, DRY_START + 133 * 60000)
    workout(u, "w2", DRY_START - 48 * HOUR, DRY_START - 47 * HOUR)
    assert save(u, METRIC_DRY, workout_id="w1").status_code == 200
    manual(u, "w2", fluid_loss_ml=500)
    wet = nix_file("Oct 25, 2026 at 2:55 PM", "Oct 25, 2026 at 5:08 PM", "02:13:00", units="customary")
    assert preview(u, wet, workout_id="w2").json()["existing"] == "replaces_less_precise"
    r = save(u, wet, workout_id="w2")
    assert r.status_code == 200 and r.json()["unit_system"] == "customary"


def test_duration_far_from_the_real_times_is_not_trusted():
    # S5. Duration 30:00:00 on an hour-long workout saved duration_min 1800.
    u = person("sw_s5")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    s = save(u, nix_file("Oct 20, 2026 at 6:00 PM", "Oct 20, 2026 at 7:00 PM", "30:00:00"), workout_id="run1").json()
    assert s["duration_min"] == 60
    assert any(w.startswith("The duration") for w in s["warnings"])


def test_a_session_with_no_length_is_refused():
    # S6. Start equal to end previewed fine, then every way of saving failed with a confusing message.
    r = preview(person("sw_s6"), nix_file("Oct 20, 2026 at 6:00 PM", "Oct 20, 2026 at 6:00 PM", "00:00:00"))
    assert r.status_code == 400 and r.json()["detail"] == sweat.ERR_NO_LENGTH


def test_the_same_file_again_leaves_the_saved_session_alone():
    # S7. "same" in the preview, but saving deleted and re-inserted it with a new imported_at_ms.
    u = person("sw_s7")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    first = save(u).json()
    assert save(u).json()["imported_at_ms"] == first["imported_at_ms"]


def test_hydration_line_never_shows_less_than_its_threshold():
    # S9. Exactly 250 ml showed "about 0.2 L".
    u = person("sw_s9")
    workout(u, "run1", SWEAT_START, SWEAT_END, "Run")
    manual(u, "run1", fluid_loss_ml=sweat.HYDRATION_MIN_ML)
    assert "about 0.3 L" in sweat.hydration_line("sw_s9", date(2026, 10, 20))


def test_huge_minute_numbers_get_a_400_on_save():
    # S2 on the server: 10**19 minutes previewed fine, then saving crashed in SQLite with a 500.
    t = S.sweat_workout()
    rows = S.timeseries_rows(t, "metric")[1]
    rows[5][0] = 10**19
    header = S.timeseries_rows(t, "metric")[0]
    summary = [["Data", "Value"]] + [list(r) for r in S.summary_rows(t, "metric")]
    data = S.build_xlsx([("Workout Summary", summary, False), ("Timeseries Data", [list(header), *rows], True)])
    u = person("sw_s2")
    workout(u, "run1", SWEAT_START, SWEAT_END)
    assert save(u, data, workout_id="run1").status_code == 400
