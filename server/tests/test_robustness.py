"""
Bad or simultaneous input gets a clear answer instead of a crash, and only one import runs at a time.

    python -m pytest -q tests/test_robustness.py
"""

import main
import pytest
from fastapi.testclient import TestClient

from app.routers import imports
from app.services import import_jobs
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
