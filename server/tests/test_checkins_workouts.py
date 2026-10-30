"""
Body weight, morning check-ins and workouts: what's stored, the night a check-in labels, and the training load.

    python -m pytest -q tests/test_checkins_workouts.py
"""

import json
import time

import main
import pytest
from fastapi.testclient import TestClient

from app.core import db

client = TestClient(main.app)
CDT = -300  # minutes, US Central summer time
HOUR = 3600 * 1000


def user(name):
    assert client.patch(f"/api/v1/users/{name}/settings", json={"units": "metric"}).status_code == 200
    return f"/api/v1/users/{name}"


def local_ms(y, mo, d, h, mi, offset=CDT):
    """UTC milliseconds for a local wall-clock time."""
    from datetime import datetime, timezone

    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000) - offset * 60 * 1000


ANSWERS = {"ready_to_train": 7, "sleep_quality": 6, "sore_muscles": ["quads", "glutes", "quads"], "unusual": []}


# ---------------------------------------------------------------- body weight


def test_weight_is_saved_in_kg_and_checked():
    u = user("weight_person")
    r = client.patch(f"{u}/settings", json={"weight_kg": 72.36})
    assert r.status_code == 200 and r.json()["weight_kg"] == 72.4
    assert client.get(f"{u}/profile").json()["settings"]["weight_kg"] == 72.4
    for bad in (25, 301):
        assert client.patch(f"{u}/settings", json={"weight_kg": bad}).status_code == 422
    assert client.patch(f"{u}/settings", json={"weight_kg": None}).json()["weight_kg"] is None


# ---------------------------------------------------------------- morning check-ins


def morning(u, ms, answers=ANSWERS, offset=CDT):
    return client.post(
        f"{u}/checkins/morning", json={"answered_at_ms": ms, "tz_offset_min": offset, "answers": answers}
    )


def test_a_check_in_labels_the_night_just_slept():
    u = user("checkin_person")
    r = morning(u, local_ms(2025, 10, 9, 7, 30))
    assert r.status_code == 200
    body = r.json()
    assert body["night_date"] == "2025-10-08" and body["survey_version"] == "v2"
    assert body["answers"]["sore_muscles"] == ["quads", "glutes"]  # each muscle once
    assert body["answers"]["unusual"] == [] and body["answers"]["energy"] is None  # "None" picked vs not answered
    # Just after midnight still belongs to the night before.
    assert morning(u, local_ms(2025, 10, 11, 0, 30)).json()["night_date"] == "2025-10-10"


def test_a_late_answer_still_labels_the_night_it_describes():
    # Answered at 7:30 am on 10 Oct, but the phone was offline and only sent it the next morning.
    u = user("checkin_late")
    r = morning(u, local_ms(2025, 10, 10, 7, 30))
    assert r.status_code == 200 and r.json()["night_date"] == "2025-10-09"


def test_a_rating_from_the_future_or_older_than_the_saved_one_is_not_kept():
    u = user("rate_order")
    start = local_ms(2025, 10, 9, 18, 0)
    client.post(
        f"{u}/workouts",
        json={
            "id": "w1",
            "start_ms": start,
            "end_ms": start + 3600000,
            "start_tz_min": CDT,
            "end_tz_min": CDT,
            "type": "Run",
        },
    )
    rate = lambda ms, effort: client.put(f"{u}/workouts/w1/rating", json={"effort": effort, "answered_at_ms": ms})  # noqa: E731
    assert rate(start + 4 * 3600000, 8).json()["effort"] == 8
    # A retry of an earlier answer that arrives late keeps the newer one.
    assert rate(start + 2 * 3600000, 3).json()["effort"] == 8
    assert rate(int(time.time() * 1000) + 3600000, 5).status_code == 400


def test_the_night_follows_the_persons_clock_not_the_phones():
    # A demo clock fixed at 1 Oct, answered now from a phone in Tokyo: the night is the one Today shows.
    u = user("checkin_clock")
    with db.connect() as conn:
        conn.execute("UPDATE users SET clock_local = '2026-10-01T08:30' WHERE user_id = 'checkin_clock'")
    body = {"answered_at_ms": int(time.time() * 1000), "tz_offset_min": 540, "answers": ANSWERS}
    assert client.post(f"{u}/checkins/morning", json=body).json()["night_date"] == "2026-09-30"


def test_answering_again_replaces_and_the_morning_score_is_linked():
    u = user("checkin_again")
    morning(u, local_ms(2025, 10, 9, 7, 30))
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO readiness_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "checkin_again",
                "2025-10-08",
                1,
                "2025-10-09T08:00",
                0,
                "placeholder-1",
                44,
                "moderate",
                "high",
                "[]",
                0,
                json.dumps({}),
            ),
        )
    r = morning(u, local_ms(2025, 10, 9, 9, 0), {**ANSWERS, "ready_to_train": 3})
    assert r.json()["answers"]["ready_to_train"] == 3
    assert r.json()["snapshot"] == {"score": 44, "status": "moderate", "model_version": "placeholder-1"}
    listed = client.get(f"{u}/checkins/morning").json()
    assert [c["night_date"] for c in listed] == ["2025-10-08"]
    assert client.get(f"{u}/checkins/morning/2025-10-08").json()["answers"]["ready_to_train"] == 3
    assert client.get(f"{u}/checkins/morning/2025-10-01").status_code == 404


@pytest.mark.parametrize(
    "answers",
    [
        {"sleep_quality": 5},  # the main label is missing
        {"ready_to_train": 11},
        {"ready_to_train": 0},
        {"ready_to_train": 5, "sore_muscles": ["neck"]},
        {"ready_to_train": 5, "unusual": ["hangover"]},
        {"ready_to_train": 5, "rehydrated": "a lot"},
    ],
)
def test_bad_answers_are_refused(answers):
    u = user("checkin_bad")
    assert morning(u, local_ms(2025, 10, 9, 7, 30), answers).status_code == 422


def test_check_in_dates_and_users_are_checked():
    u = user("checkin_dates")
    assert morning(u, int(time.time() * 1000) + 3 * 24 * HOUR).status_code == 400
    assert morning(u, local_ms(1999, 5, 1, 7, 0)).status_code == 400
    assert morning(u, local_ms(2025, 10, 9, 7, 30), offset=2000).status_code == 400
    assert (
        client.post(
            "/api/v1/users/nobody_here/checkins/morning",
            json={"answered_at_ms": local_ms(2025, 10, 9, 7, 30), "tz_offset_min": CDT, "answers": ANSWERS},
        ).status_code
        == 404
    )


# ---------------------------------------------------------------- workouts


def workout(u, wid, start, minutes, **extra):
    body = {
        "id": wid,
        "start_ms": start,
        "end_ms": start + minutes * 60000,
        "start_tz_min": CDT,
        "end_tz_min": CDT,
        "type": "Leg day",
        **extra,
    }
    return client.post(f"{u}/workouts", json=body)


def test_a_rated_workout_has_a_training_load():
    u = user("workout_person")
    start = local_ms(2025, 10, 8, 18, 10)
    w = workout(u, "w1", start, 58).json()
    assert w["duration_min"] == 58 and w["effort"] is None and w["load"] is None
    assert w["start_local"] == "2025-10-08T18:10" and w["source"] == "manual"
    rated = client.put(f"{u}/workouts/w1/rating", json={"effort": 8, "satisfaction": 6, "answered_at_ms": start + HOUR})
    assert rated.json()["load"] == 8 * 58 and rated.json()["satisfaction"] == 6
    # Sending the workout again (say with a better type) keeps the rating.
    again = workout(u, "w1", start, 58, type="Squats").json()
    assert again["type"] == "Squats" and again["effort"] == 8


def test_bad_workouts_are_refused():
    u = user("workout_bad")
    start = local_ms(2025, 10, 8, 18, 10)
    assert workout(u, "back", start, -5).status_code == 400
    assert workout(u, "long", start, 25 * 60).status_code == 400
    assert workout(u, "old", local_ms(1999, 1, 1, 9, 0), 30).status_code == 400
    assert workout(u, "", start, 30).status_code == 422
    assert client.put(f"{u}/workouts/missing/rating", json={"effort": 5, "answered_at_ms": start}).status_code == 404
    workout(u, "ok", start, 30)
    assert client.put(f"{u}/workouts/ok/rating", json={"effort": 0, "answered_at_ms": start}).status_code == 422
    assert client.get(f"{u}/workouts/missing").status_code == 404


def test_recent_workouts_are_listed_oldest_first():
    u = user("workout_list")
    now = int(time.time() * 1000)
    workout(u, "b", now - 2 * 24 * HOUR, 40)
    workout(u, "a", now - 5 * 24 * HOUR, 40)
    workout(u, "old", now - 60 * 24 * HOUR, 40)
    assert [w["id"] for w in client.get(f"{u}/workouts").json()] == ["a", "b"]
    assert [w["id"] for w in client.get(f"{u}/workouts?days=90").json()] == ["old", "a", "b"]
