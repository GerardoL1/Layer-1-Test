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
# A real moment (October 2025). Readings dated before 2000 are refused.
T = 1_760_000_000_000
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


def test_infinity_and_nan_are_never_stored():
    row = '{"date": "2026-09-30 23:14:05 -0500", "Avg": Infinity}'
    hae = '{"data": {"metrics": [{"name": "heart_rate", "data": [' + row + "]}]}}"
    r = client.post(HAE.format("inf"), content=hae, headers={"Content-Type": "application/json"}).json()
    assert r["new"] == 0 and r["unreadable"] == 1
    rows = "2026-09-30T23:30:00-05:00 | 2026-09-30T23:30:00-05:00 | inf | Apple Watch"
    r = client.post("/api/v1/users/inf/readings/shortcuts", data={"metric": "heart_rate", "rows": rows})
    assert "new 0" in r.text and "1 lines could not be read" in r.text
    sample = '{"uuid": "x", "metric": "heart_rate", "value": NaN, "start_ms": 1, "end_ms": 1, "tz_offset_min": 0}'
    r = client.post(
        "/api/v1/users/inf/readings",
        content='{"samples": [' + sample + "]}",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422


def test_since_days_cannot_be_negative():
    r = client.post("/api/v1/users/negative/imports", files=NOT_A_ZIP, data={"since_days": "-5"})
    assert r.status_code == 422


def test_a_damaged_export_gets_a_plain_message():
    broken = b'<?xml version="1.0"?><HealthData><Record type="HKQuantityTypeIdentifierHeartRate"'
    r = client.post("/api/v1/users/damaged/imports", files={"file": ("export.xml", broken, "text/xml")})
    status = client.get(r.headers["location"]).json()
    assert status["state"] == "error" and "damaged" in status["error"]


# ---------------------------------------------------------------- units and finding the export


def _values(user_id: str, metric: str) -> list[float]:
    with db.connect() as conn:
        rows = conn.execute("SELECT value FROM samples WHERE user_id = ? AND metric = ?", (user_id, metric))
        return sorted(r[0] for r in rows)


def test_units_are_converted_on_every_route_and_unknown_ones_refused():
    rows = [{"date": "2026-09-30 23:14:05 -0500", "qty": 0.05}]
    hae = {"data": {"metrics": [{"name": "heart_rate_variability", "units": "s", "data": rows}]}}
    assert client.post(HAE.format("units"), json=hae).json()["new"] == 1
    hae["data"]["metrics"][0]["units"] = "kHz"
    r = client.post(HAE.format("units_bad"), json=hae).json()
    assert r["new"] == 0 and r["unreadable"] == 1 and "kHz" in r["notes"][0]

    line = "2026-09-30T23:30:00-05:00 | 2026-09-30T23:30:00-05:00 | {} | Apple Watch"
    client.post("/api/v1/users/units/readings/shortcuts", data={"metric": "hrv_sdnn", "rows": line.format("0,04 s")})
    r = client.post("/api/v1/users/units/readings/shortcuts", data={"metric": "hrv_sdnn", "rows": line.format("4 kHz")})
    assert "1 lines could not be read" in r.text

    sample = {"uuid": "u1", "metric": "heart_rate", "value": 1, "unit": "count/s", "start_ms": T, "end_ms": T}
    assert client.post("/api/v1/users/units/readings", json={"samples": [{**sample, "tz_offset_min": 0}]}).is_success
    bad = {**sample, "uuid": "u2", "unit": "kHz", "tz_offset_min": 0}
    assert client.post("/api/v1/users/units/readings", json={"samples": [bad]}).status_code == 400

    assert _values("units", "hrv_sdnn") == pytest.approx([40, 50])
    assert _values("units", "heart_rate") == pytest.approx([60])


def test_export_under_another_name_is_imported_and_only_it_counts_toward_the_size_limit(monkeypatch, tmp_path):
    import zipfile

    from app.core import limits

    record = (
        '<Record type="HKQuantityTypeIdentifierHeartRate" sourceName="Apple Watch" unit="count/min" '
        'startDate="2026-09-30 23:14:05 -0500" endDate="2026-09-30 23:14:05 -0500" value="52"/>'
    )
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        cda = "<ClinicalDocument>" + " " * 2_000_000 + "</ClinicalDocument>"
        zf.writestr("apple_health_export/export_cda.xml", cda)
        zf.writestr("apple_health_export/exportar.xml", f"<HealthData>{record}</HealthData>")
    monkeypatch.setattr(limits, "MAX_UNZIPPED_BYTES", 1_000_000)  # less than the whole zip, more than the export
    with db.connect() as conn:
        counts = apple_export.import_export(path, conn, "renamed_export")
    assert counts["heart_rate"] == 1 and counts["new"] == 1


# ---------------------------------------------------------------- batch A: dates, damaged zips, units


def test_readings_dated_far_outside_real_life_are_refused_and_never_break_the_user():
    hr_row = {"date": "0001-01-02 00:00:00 +0000", "Avg": 52}
    r = client.post(HAE.format("year_one"), json={"data": {"metrics": [{"name": "heart_rate", "data": [hr_row]}]}})
    assert r.json()["new"] == 0 and r.json()["unreadable"] == 1
    line = "0001-01-01T00:00:00+14:00 | 0001-01-01T00:00:00+14:00 | 50 | Apple Watch"
    r = client.post("/api/v1/users/year_one/readings/shortcuts", data={"metric": "heart_rate", "rows": line})
    assert "new 0" in r.text
    for start_ms in (10**15, -(10**15), 10**20):
        sample = {"uuid": "far", "metric": "heart_rate", "value": 50, "start_ms": start_ms, "end_ms": start_ms}
        r = client.post("/api/v1/users/year_one/readings", json={"samples": [{**sample, "tz_offset_min": 0}]})
        assert r.status_code == 400 and "before 2000" in r.json()["detail"]
    with pytest.raises(ValueError):
        parse_date("9999-12-31 23:59:59 -1400")
    assert client.get("/api/v1/users/year_one/today").status_code != 500


def _damaged_zip(tmp_path, how: str):
    import zipfile

    path = tmp_path / f"{how}.zip"
    body = "<HealthData>" + "<Record/>" * 5000 + "</HealthData>"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("apple_health_export/export.xml", body)
    data = bytearray(path.read_bytes())
    if how == "encrypted":
        data[6] |= 1  # the "encrypted" flag in the file's local header
        central = data.find(b"PK\x01\x02")
        data[central + 8] |= 1
    else:  # corrupt compressed data
        start = 30 + len("apple_health_export/export.xml")
        for i in range(start, start + 40):
            data[i] ^= 0xFF
    return bytes(data)


@pytest.mark.parametrize("how", ["encrypted", "corrupt"])
def test_a_zip_that_cannot_be_unpacked_gets_a_clear_400(tmp_path, how):
    files = {"file": ("export.zip", _damaged_zip(tmp_path, how), "application/zip")}
    r = client.post(f"/api/v1/users/damaged_{how}/imports", files=files)
    assert r.status_code == 400 and "damaged" in r.json()["detail"]


def test_a_unit_conversion_that_overflows_is_never_stored(tmp_path):
    sample = {"uuid": "big", "metric": "hrv_sdnn", "value": 1e306, "unit": "s", "start_ms": 1, "end_ms": 1}
    sample.update(start_ms=T, end_ms=T, tz_offset_min=0)
    assert client.post("/api/v1/users/overflow/readings", json={"samples": [sample]}).status_code == 400

    record = (
        '<Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" sourceName="Apple Watch" unit="{}" '
        'startDate="2026-09-30 23:14:05 -0500" endDate="2026-09-30 23:14:05 -0500" value="{}"/>'
    )
    path = tmp_path / "export.xml"
    path.write_text(f"<HealthData>{record.format('s', '1e306')}{record.format('ms', 'inf')}</HealthData>")
    with db.connect() as conn:
        counts = apple_export.import_export(path, conn, "overflow_import")
    assert counts["new"] == 0 and counts["skipped"] == 2


@pytest.mark.parametrize("gap", ["\u00a0", "\u202f", "\t", " "])
def test_shortcuts_reads_a_unit_after_any_kind_of_space(gap):
    line = f"2026-09-30T23:30:00-05:00 | 2026-09-30T23:30:00-05:00 | 48,5{gap}ms | Apple Watch"
    r = client.post("/api/v1/users/sc_gap/readings/shortcuts", data={"metric": "hrv_sdnn", "rows": line})
    assert "could not be read" not in r.text


def test_health_auto_export_note_names_units_that_are_not_text():
    rows = [{"date": "2026-09-30 23:14:05 -0500", "Avg": 52}]
    metric = {"name": "heart_rate", "units": ["count/min"], "data": rows}
    r = client.post(HAE.format("odd_units"), json={"data": {"metrics": [metric]}}).json()
    assert "heart_rate in an unreadable unit" in r["notes"][0]
