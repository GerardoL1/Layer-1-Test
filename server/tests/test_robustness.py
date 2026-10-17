"""
Bad or simultaneous input gets a clear answer instead of a crash, and only one import runs at a time.

    python -m pytest -q tests/test_robustness.py
"""

import sqlite3

import main
import pytest
from conftest import SAMPLE_DATA, SAMPLES
from fastapi.testclient import TestClient

from app.core import db
from app.routers import imports
from app.services import apple_export, import_jobs
from app.services.apple_export import parse_date
from app.services.shortcuts import shortcut_date

client = TestClient(main.app)

HAE = "/api/v1/users/{}/readings/health-auto-export"
NOT_A_ZIP = {"file": ("export.zip", b"not really a zip", "application/zip")}

# ---------------------------------------------------------------- Health Auto Export bodies


@pytest.mark.parametrize(
    "body", ["not json", "", "[1, 2]", '{"data": "heart rate"}', '{"data": {"metrics": "heart_rate"}}']
)
def test_health_auto_export_bodies_it_cannot_read_get_a_400(body):
    r = client.post(HAE.format("hae_bad"), content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["detail"]


def test_health_auto_export_values_that_are_not_numbers_are_unreadable():
    rows = [
        {"date": "2026-09-30 23:14:05 -0500", "Avg": "fast"},
        {"date": "2026-09-30 23:15:05 -0500", "Avg": 52},
        "not a row",
    ]
    r = client.post(HAE.format("hae_values"), json={"data": {"metrics": [{"name": "heart_rate", "data": rows}]}})
    assert r.status_code == 200
    assert r.json()["samples"] == 1 and r.json()["new"] == 1 and r.json()["unreadable"] == 2


# ---------------------------------------------------------------- impossible UTC offsets


def test_impossible_offsets_are_unreadable_on_every_route():
    with pytest.raises(ValueError):
        parse_date("2026-09-30 23:14:05 +2300")
    with pytest.raises(ValueError):
        shortcut_date("2026-09-30T23:14:05+23:00")
    assert parse_date("2026-09-30 23:14:05 +1400")[1] == 840  # the furthest real offset still works

    hae = {"data": {"metrics": [{"name": "heart_rate", "data": [{"date": "2026-09-30 23:14:05 +2300", "Avg": 52}]}]}}
    r = client.post(HAE.format("offsets"), json=hae).json()
    assert r["new"] == 0 and r["unreadable"] == 1

    rows = "2026-09-30T23:30:00+23:00 | 2026-09-30T23:30:00+23:00 | 52 | Apple Watch"
    r = client.post("/api/v1/users/offsets/readings/shortcuts", data={"metric": "heart_rate", "rows": rows})
    assert "new 0" in r.text and "1 lines could not be read" in r.text


# ---------------------------------------------------------------- one import at a time


def test_only_one_upload_can_take_the_import_slot():
    previous = import_jobs.reserve("first", "export.zip")
    try:
        with pytest.raises(import_jobs.Busy):
            import_jobs.reserve("second", "export.zip")
    finally:
        import_jobs.release(previous)
    assert not import_jobs.is_busy()


def test_the_slot_is_taken_before_the_upload_is_read(monkeypatch):
    busy_while_copying = []
    real_copy = imports.shutil.copyfileobj

    def copy(src, dst):
        busy_while_copying.append(import_jobs.is_busy())  # a second upload arriving now gets a 409
        real_copy(src, dst)

    monkeypatch.setattr(imports.shutil, "copyfileobj", copy)
    r = client.post("/api/v1/users/slot/imports", files=NOT_A_ZIP)
    assert busy_while_copying == [True]
    assert r.status_code == 400


def test_a_refused_upload_frees_the_slot_and_keeps_the_last_status():
    before = dict(import_jobs.IMPORT_STATUS)
    r = client.post("/api/v1/users/refused/imports", files=NOT_A_ZIP)
    assert r.status_code == 400
    assert import_jobs.IMPORT_STATUS == before and not import_jobs.is_busy()


# ---------------------------------------------------------------- many people at once


def test_the_database_lets_people_read_while_others_write():
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert db.LOCK_WAIT_SECONDS >= 30


def test_an_import_batch_is_retried_when_the_database_is_busy(monkeypatch):
    real_add, calls = db.add_readings, []

    def busy_once(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_add(*args, **kwargs)

    monkeypatch.setattr(db, "add_readings", busy_once)
    monkeypatch.setattr(apple_export.time, "sleep", lambda s: None)
    with db.connect() as conn:
        counts = apple_export.import_export(SAMPLE_DATA / SAMPLES["sam"], conn, "busy_import")
    assert counts["new"] > 0 and len(calls) > 1


# ---------------------------------------------------------------- Shortcuts and Health Auto Export


def test_shortcuts_takes_a_first_sync_bigger_than_1_mb():
    times = [f"2026-09-{1 + i // 1440:02d}T{i // 60 % 24:02d}:{i % 60:02d}:00-05:00" for i in range(20000)]
    rows = "\n".join(f"{t} | {t} | 52 | Test Apple Watch" for t in times)
    assert len(rows) > 1024 * 1024
    for url, data in (
        ("/api/v1/users/big_sc/readings/shortcuts", {"metric": "heart_rate", "rows": rows}),
        ("/api/shortcut", {"user": "big_sc_old", "metric": "heart_rate", "rows": rows}),
    ):
        r = client.post(url, data=data)
        assert r.status_code == 200 and "new 20000" in r.text, url


def test_a_shortcuts_sleep_batch_with_unreadable_lines_is_refused_whole():
    # German stage names: only REM would match by accident, leaving a fake short night.
    rows = "\n".join(
        [
            "2026-09-20T23:00:00+02:00 | 2026-09-21T02:00:00+02:00 | Kern | Apple Watch",
            "2026-09-21T02:00:00+02:00 | 2026-09-21T03:00:00+02:00 | Tief | Apple Watch",
            "2026-09-21T03:00:00+02:00 | 2026-09-21T04:20:00+02:00 | REM | Apple Watch",
        ]
    )
    r = client.post("/api/v1/users/german/readings/shortcuts", data={"metric": "sleep", "rows": rows})
    assert r.status_code == 400 and "Nothing was saved" in r.json()["detail"] and "number" in r.json()["detail"]
    with db.connect() as conn:
        assert db.load_records(conn, "german").empty


def test_aggregated_sleep_from_health_auto_export_is_refused_with_a_note():
    summary = {
        "date": "2026-09-30 00:00:00 -0500",
        "sleepStart": "2026-09-29 23:00:00 -0500",
        "sleepEnd": "2026-09-30 07:00:00 -0500",
        "asleep": 7.5,
        "inBed": 8,
    }
    body = {"data": {"metrics": [{"name": "sleep_analysis", "data": [summary]}]}}
    r = client.post(HAE.format("aggregated"), json=body).json()
    assert r["sleep_stages"] == 0 and r["unreadable"] == 1
    assert len(r["notes"]) == 1 and "Aggregate sleep data" in r["notes"][0]


@pytest.mark.parametrize(
    "body",
    [
        '{"data": {"metrics": [{"name": ["heart_rate"], "data": []}]}}',
        '{"data": {"metrics": [{"name": "heart_rate", "data": [{"date": "2026-09-30 23:14:05 -0500", "Avg": '
        + "9" * 400
        + "}]}]}}",
        '{"data": {"metrics": [{"name": "heart_rate", "data": '
        '[{"date": "2026-09-30 23:14:05 -0500", "Avg": 52, "source": {"x": 1}}]}]}}',
        "[" * 100000 + "]" * 100000,
    ],
    ids=["name is a list", "400-digit number", "source is an object", "nested too deep"],
)
def test_health_auto_export_odd_bodies_never_crash(body):
    r = client.post(HAE.format("odd"), content=body, headers={"Content-Type": "application/json"})
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        assert r.json()["new"] == 0 and r.json()["unreadable"] >= 1


def test_health_auto_export_sleep_names_are_read_or_counted():
    def phase(value, start, end):
        return {"value": value, "startDate": f"2026-09-30 {start} -0500", "endDate": f"2026-09-30 {end} -0500"}

    rows = [
        phase("Core Sleep", "01:00:00", "02:00:00"),
        phase("asleepDeep", "02:00:00", "03:00:00"),
        phase("Snoozing", "03:00:00", "04:00:00"),
    ]
    r = client.post(HAE.format("sleep_names"), json={"data": {"metrics": [{"name": "sleep_analysis", "data": rows}]}})
    assert r.json()["sleep_stages"] == 2 and r.json()["unreadable"] == 1
