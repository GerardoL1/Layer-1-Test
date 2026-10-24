"""
Fixes from agent testing round 4: catch-up after a history import, size limits, late retries, workout ids,
the export guard, unanswered body maps, contributions that add up, and strict answers.

    python -m pytest -q tests/test_round4_fixes.py
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import main
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from test_checkins_workouts import ANSWERS, local_ms, morning, user, workout
from test_processing import load, store, to_utc

from app.core import db
from app.readiness import scoring
from app.services import processing, training_table

client = TestClient(main.app)
SERVER = Path(__file__).resolve().parent.parent


def test_a_history_import_after_today_was_shown_is_all_catch_up():
    who = "r4_backfill"
    recs = load("sam")
    morning_25 = recs["start_local"].min().normalize() + pd.Timedelta(days=25, hours=9)
    recent = recs["start_local"] >= morning_25 - pd.Timedelta(days=5)
    store(who, recs[recent & (recs["end_local"] <= morning_25)])
    processing.process_user(who, to_utc(morning_25.to_pydatetime(), -420))
    store(who, recs[~recent])  # the import of everything older
    report = processing.process_user(who, to_utc(morning_25.to_pydatetime() + pd.Timedelta(hours=3), -420))
    assert report.new_nights
    with db.connect() as conn:
        added = {d.isoformat() for d in report.new_nights}
        rows = conn.execute("SELECT night_date, catch_up FROM readiness_snapshots WHERE user_id = ?", (who,))
        flags = {r["night_date"]: r["catch_up"] for r in rows if r["night_date"] in added}
    assert flags and set(flags.values()) == {1}


def test_small_routes_refuse_big_bodies():
    u = user("r4_big")
    big = {
        "answered_at_ms": local_ms(2025, 10, 9, 7, 30),
        "tz_offset_min": -300,
        "answers": {**ANSWERS, "unusual": ["alcohol"] * 200_000},
    }
    assert client.post(f"{u}/checkins/morning", json=big).status_code == 413
    too_many = {**ANSWERS, "unusual": ["alcohol"] * 6 + ["travel"]}  # 7 items, but only 2 once repeats are dropped
    assert morning(u, local_ms(2025, 10, 9, 7, 30), too_many).json()["answers"]["unusual"] == ["alcohol", "travel"]


def test_a_late_retry_of_an_older_answer_does_not_win():
    u = user("r4_retry")
    morning(u, local_ms(2025, 10, 9, 7, 0), {"ready_to_train": 3})
    morning(u, local_ms(2025, 10, 9, 7, 5), {"ready_to_train": 8})
    late = morning(u, local_ms(2025, 10, 9, 7, 0), {"ready_to_train": 3})
    assert late.status_code == 200 and late.json()["answers"]["ready_to_train"] == 8


@pytest.mark.parametrize("bad", ["a/b", "..", ".", " ", " w", "w ", "a\\b", "a\x00b"])
def test_workout_ids_that_break_urls_are_refused(bad):
    u = user("r4_ids")
    assert workout(u, bad, local_ms(2025, 10, 8, 18, 0), 30).status_code == 422


def test_the_export_guard_sees_other_spellings_of_the_repo(tmp_path):
    if sys.platform != "win32":
        pytest.skip("these path spellings only exist on Windows")
    sneaky = "\\\\?\\" + str(SERVER / "r4_sneaky.csv")
    run = subprocess.run(
        [sys.executable, "export_training_table.py", sneaky], cwd=SERVER, capture_output=True, text=True
    )
    assert run.returncode != 0 and "Refusing" in run.stderr
    assert not (SERVER / "r4_sneaky.csv").exists()


def test_an_unanswered_body_map_stays_empty_in_the_export():
    u = user("r4_body")
    body = morning(u, local_ms(2025, 10, 9, 7, 30), {"ready_to_train": 6}).json()["answers"]
    assert body["sore_muscles"] is None and body["unusual"] is None
    picked_none = morning(u, local_ms(2025, 10, 10, 7, 30), {"ready_to_train": 6, "sore_muscles": []})
    assert picked_none.json()["answers"]["sore_muscles"] == []
    assert training_table._list(None) is None and training_table._list([]) == "none"


@pytest.mark.parametrize(
    ("zs", "score"),
    [
        ({"z_hrv": -8.0, "z_rhr": 8.0, "z_tst": -8.0, "z_eff": -8.0, "z_frag": 8.0}, 0),
        ({"z_hrv": 9.0, "z_rhr": -9.0, "z_tst": 9.0, "z_eff": 9.0, "z_frag": -9.0}, 100),
        ({"z_hrv": 1.0, "z_tst": 1.0, "z_eff": 1.0}, 60),
        ({"z_hrv": 0.01, "z_rhr": 0.0, "z_tst": -0.01}, 50),
    ],
)
def test_contributions_add_up_to_the_shown_score(zs, score):
    result = scoring.PlaceholderModel().score({**zs, "usable_sleep": True})
    assert result.score == score
    assert sum(c.points for c in result.contributions) == pytest.approx(score - 50, abs=1e-9)
    assert all(str(c.points) != "-0.0" for c in result.contributions)


@pytest.mark.parametrize(
    "change",
    [
        {"answers": {"ready_to_train": True}},
        {"answers": {"ready_to_train": "7"}},
        {"answers": {"ready_to_train": 7.0}},
        {"tz_offset_min": True},
        {"survey_version": ""},
    ],
)
def test_answers_must_be_real_numbers(change):
    u = user("r4_strict")
    body = {"answered_at_ms": local_ms(2025, 10, 9, 7, 30), "tz_offset_min": -300, "answers": ANSWERS, **change}
    assert client.post(f"{u}/checkins/morning", json=body).status_code == 422


def test_future_check_ins_blank_types_and_early_ratings_are_refused():
    u = user("r4_dates")
    soon = int(time.time() * 1000) + 20 * 3600 * 1000
    assert morning(u, soon).status_code == 400
    start = local_ms(2025, 10, 8, 18, 0)
    assert workout(u, "blank", start, 30, type="   ").status_code == 422
    assert workout(u, "w", start, 30).status_code == 200
    early = client.put(f"{u}/workouts/w/rating", json={"effort": 5, "answered_at_ms": start - 3600 * 1000})
    assert early.status_code == 400
    assert client.put(f"{u}/workouts/w/rating", json={"effort": True, "answered_at_ms": start}).status_code == 422
    stored = json.dumps(client.get(f"{u}/workouts/w").json())
    assert '"effort": null' in stored
