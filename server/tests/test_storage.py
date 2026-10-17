"""
Storage and ingestion routes. The main check: data that goes through the
database comes out in exactly the shape the tested pipeline expects.

    python -m pytest -q tests
"""

import main
import pandas as pd
import pytest
from conftest import SAMPLE_DATA, SAMPLES
from fastapi.testclient import TestClient

from app.core import db
from app.services.apple_export import import_export
from layer1 import pipeline as P

client = TestClient(main.app)


def pipeline_from_records(records: pd.DataFrame, person: str) -> pd.DataFrame:
    cleaned, _, _ = P.clean(records)
    sessions, stages = P.find_sleep_windows(cleaned["sleep_stages"])
    nights = P.add_baselines(P.flag_quality(P.nightly_metrics(sessions, stages, cleaned)))
    return P.build_ml_table(nights, person)


@pytest.mark.parametrize("person", list(SAMPLES))
def test_export_through_database_matches_pipeline(person):
    zip_path = SAMPLE_DATA / SAMPLES[person]
    user = f"db_{person}"
    with db.connect() as conn:
        import_export(zip_path, conn, user)
        records = db.load_records(conn, user)

    # Same records as reading the file directly, once cleaned (the database already drops exact repeats).
    direct, _ = P.load_export(zip_path, days=None)
    from_db, _, _ = P.clean(records)
    from_file, _, _ = P.clean(direct)
    for table in from_file:
        a = from_db[table][["metric", "stage", "value", "source", "start_utc", "end_utc", "start_local", "end_local"]]
        b = from_file[table][a.columns]
        key = ["start_utc", "end_utc", "metric", "source"]
        pd.testing.assert_frame_equal(
            a.sort_values(key, ignore_index=True),
            b.sort_values(key, ignore_index=True),
            check_dtype=False,
            check_index_type=False,
        )

    expected = P.run_pipeline(zip_path, person, days=None).ml_table
    pd.testing.assert_frame_equal(pipeline_from_records(records, person), expected, check_dtype=False)


def test_import_keeps_utc_offset_and_ignores_repeats():
    zip_path = SAMPLE_DATA / SAMPLES["sam"]
    with db.connect() as conn:
        import_export(zip_path, conn, "offsets")
        again = import_export(zip_path, conn, "offsets")
        offsets = {r[0] for r in conn.execute("SELECT DISTINCT tz_offset_min FROM samples WHERE user_id='offsets'")}
        sleep_offsets = {
            r[0] for r in conn.execute("SELECT DISTINCT start_tz_min FROM sleep_stages WHERE user_id='offsets'")
        }
    assert again["new"] == 0
    assert offsets == sleep_offsets == {-420}  # mock data is Los Angeles summer time


def phone_sample(**changes):
    s = {
        "uuid": "hk-1",
        "metric": "heart_rate",
        "value": 55.0,
        "start_ms": 1790000000000,
        "end_ms": 1790000000000,
        "tz_offset_min": -300,
        "source": "Sam’s Apple Watch",
    }
    s.update(changes)
    return s


def count(table, user):
    with db.connect() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", (user,)).fetchone()[0]


def test_phone_upload_requires_offset():
    r = client.post("/api/v1/users/phone_bad/readings", json={"samples": [phone_sample(tz_offset_min=None)]})
    assert r.status_code == 400 and "tz_offset_min" in r.json()["detail"]
    r = client.post("/api/v1/users/phone_bad/readings", json={"samples": [phone_sample(tz_offset_min=5000)]})
    assert r.status_code == 400
    r = client.post("/api/v1/users/phone_bad/readings", json={"samples": [phone_sample(metric="steps")]})
    assert r.status_code == 400
    assert count("samples", "phone_bad") == 0


def test_phone_upload_stores_samples_and_sleep():
    body = {
        "samples": [phone_sample()],
        "sleep": [
            {
                "uuid": "hk-2",
                "stage": "deep",
                "start_ms": 1790000000000,
                "end_ms": 1790001800000,
                "start_tz_min": -300,
                "end_tz_min": -300,
                "source": "Sam’s Apple Watch",
            }
        ],
    }
    assert client.post("/api/v1/users/phone/readings", json=body).json() == {"received": 2, "new": 2}
    assert client.post("/api/v1/users/phone/readings", json=body).json() == {"received": 2, "new": 0}
    with db.connect() as conn:
        rec = db.load_records(conn, "phone")
    hr = rec[rec["metric"] == "heart_rate"].iloc[0]
    assert hr["start_local"] == hr["start_utc"].tz_localize(None) - pd.Timedelta(hours=5)


def test_health_auto_export_keeps_offset():
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "heart_rate",
                    "units": "count/min",
                    "data": [{"date": "2026-09-30 23:14:05 -0500", "Avg": 52, "source": "Apple Watch"}],
                },
                {
                    "name": "sleep_analysis",
                    "data": [
                        {
                            "startDate": "2026-09-30 23:30:00 -0500",
                            "endDate": "2026-10-01 00:10:00 -0500",
                            "value": "Core",
                            "source": "Apple Watch",
                        }
                    ],
                },
                {"name": "step_count", "data": [{"date": "2026-09-30 23:14:05 -0500", "qty": 10}]},
            ]
        }
    }
    r = client.post("/api/v1/users/hae/readings/health-auto-export", json=payload).json()
    assert r["new"] == 2 and r["ignored_metrics"] == ["step_count"]
    with db.connect() as conn:
        rec = db.load_records(conn, "hae")
    assert str(rec.iloc[0]["start_local"]) == "2026-09-30 23:14:05"


def test_shortcut_keeps_offset():
    rows = "2026-09-30T23:30:00-05:00 | 2026-10-01T00:10:00-05:00 | 3 | Apple Watch\nnot a valid line"
    r = client.post("/api/v1/users/sc/readings/shortcuts", data={"metric": "sleep", "rows": rows})
    assert r.status_code == 200 and "new 1" in r.text and "1 lines could not be read" in r.text
    with db.connect() as conn:
        rec = db.load_records(conn, "sc")
    assert rec.iloc[0]["stage"] == "core"
    assert str(rec.iloc[0]["end_local"]) == "2026-10-01 00:10:00"


def test_import_route_runs_in_background():
    with open(SAMPLE_DATA / SAMPLES["alex"], "rb") as f:
        r = client.post(
            "/api/v1/users/route/imports",
            files={"file": ("export.zip", f, "application/zip")},
            data={"since_days": "0"},
        )
    assert r.status_code == 202 and r.json()["state"] == "queued"
    import_id = r.json()["import_id"]
    assert r.headers["location"] == f"/api/v1/users/route/imports/{import_id}"
    status = client.get(r.headers["location"]).json()
    assert status["state"] == "done" and status["counts"]["new"] > 0
    assert [job["import_id"] for job in client.get("/api/v1/users/route/imports").json()] == [import_id]
    assert client.get(f"/api/v1/users/someone_else/imports/{import_id}").status_code == 404
    # What the import screen shows: the file, how far through it the reader got, and nights ready.
    assert status["file_name"] == "export.zip" and status["file_bytes"] > 0
    assert status["read_fraction"] == 1.0 and status["nights_ready"] > 0


def test_import_reports_position_through_the_file(monkeypatch):
    from app.services import apple_export

    monkeypatch.setattr(apple_export, "TICK_EVERY", 500)  # the mock file is small, so report often
    seen = []
    with db.connect() as conn:
        import_export(
            SAMPLE_DATA / SAMPLES["jordan"],
            conn,
            "ticks",
            on_position=lambda share, reading: seen.append((share, reading)),
        )
    shares = [s for s, _ in seen]
    assert len(seen) > 3 and shares == sorted(shares) and shares[-1] == 1.0
    assert all(0 <= s <= 1 for s in shares)
    assert {"heart rate", "sleep"} & {r for _, r in seen}


def test_dashboard_endpoints_are_gone():
    for path in ("/", "/api/samples", "/api/sleep", "/api/summary"):
        assert client.get(path).status_code == 404


def test_imports_keep_everything_by_default():
    # One reading from 2024, far more than 90 days back. Without since_days it must still come in.
    xml = (
        '<?xml version="1.0"?><HealthData><Record type="HKQuantityTypeIdentifierHeartRate" '
        'sourceName="Test’s Apple Watch" unit="count/min" startDate="2024-01-01 23:00:00 -0500" '
        'endDate="2024-01-01 23:00:00 -0500" value="52"/></HealthData>'
    )
    r = client.post("/api/v1/users/old_export/imports", files={"file": ("export.xml", xml.encode(), "text/xml")})
    assert r.status_code == 202
    status = client.get(r.headers["location"]).json()
    assert status["state"] == "done" and status["counts"]["heart_rate"] == 1
