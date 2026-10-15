"""
Size limits: oversized requests and zips get a clear 413 instead of being read.
The limits are lowered for these tests so they stay fast.

    python -m pytest -q tests/test_limits.py
"""

import io
import json
import zipfile

import main
import pytest
from conftest import SAMPLE_DATA, SAMPLES
from fastapi.testclient import TestClient

from app.core import db, limits
from app.services import apple_export

client = TestClient(main.app)


def test_the_real_limits():
    assert limits.MAX_EXPORT_UPLOAD_BYTES == 500 * limits.MB
    assert limits.MAX_JSON_BYTES == 20 * limits.MB
    assert limits.MAX_UNZIPPED_BYTES == 4 * limits.GB
    assert set(limits.LIMITS_BY_PATH) == {"/api/import", "/upload", "/api/hae", "/api/shortcut"}


def test_oversized_json_request_gets_413(monkeypatch):
    monkeypatch.setitem(limits.LIMITS_BY_PATH, "/api/hae", 1000)
    payload = {
        "data": {
            "metrics": [
                {
                    "name": "heart_rate",
                    "data": [{"date": "2026-09-30 23:14:05 -0500", "Avg": 52, "source": "Apple Watch"}] * 100,
                }
            ]
        }
    }
    r = client.post("/api/hae?user_id=big", json=payload, headers={"Origin": "http://localhost:8081"})
    assert r.status_code == 413
    assert r.json()["detail"].startswith("This request is too big.")
    assert r.headers.get("access-control-allow-origin") == "*"  # the app in a browser can read the message
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM samples WHERE user_id = 'big'").fetchone()[0] == 0


def test_oversized_request_without_a_declared_size_gets_413(monkeypatch):
    monkeypatch.setitem(limits.LIMITS_BY_PATH, "/upload", 1000)
    body = json.dumps(
        {
            "user_id": "streamed",
            "samples": [
                {"uuid": f"s{i}", "metric": "heart_rate", "value": 50.0, "start_ms": i, "end_ms": i, "tz_offset_min": 0}
                for i in range(100)
            ],
        }
    ).encode()

    def chunks():  # streamed, so no Content-Length is sent
        for i in range(0, len(body), 200):
            yield body[i : i + 200]

    r = client.post("/upload", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413 and "too big" in r.json()["detail"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM samples WHERE user_id = 'streamed'").fetchone()[0] == 0


def test_requests_under_the_limit_still_work():
    r = client.post(
        "/api/shortcut",
        data={
            "user": "small",
            "metric": "heart_rate",
            "rows": "2026-09-30T23:30:00-05:00 | 2026-09-30T23:30:00-05:00 | 52 | Apple Watch",
        },
    )
    assert r.status_code == 200 and "new 1" in r.text


def test_oversized_export_upload_gets_413(monkeypatch):
    monkeypatch.setitem(limits.LIMITS_BY_PATH, "/api/import", 10 * 1024)
    with open(SAMPLE_DATA / SAMPLES["sam"], "rb") as f:
        r = client.post(
            "/api/import",
            files={"file": ("export.zip", f, "application/zip")},
            data={"user_id": "toolarge", "since_days": "0"},
        )
    assert r.status_code == 413
    assert r.json()["detail"].startswith("This file is too big. The limit is")


def big_zip() -> bytes:
    """A small zip that unpacks to 5 MB (spaces compress very well)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("apple_health_export/export.xml", "<HealthData>" + " " * (5 * 1024 * 1024) + "</HealthData>")
    return buf.getvalue()


def test_zip_that_unpacks_too_big_gets_413(monkeypatch):
    monkeypatch.setattr(limits, "MAX_UNZIPPED_BYTES", 1024 * 1024)
    data = big_zip()
    assert len(data) < 100 * 1024
    r = client.post(
        "/api/import",
        files={"file": ("export.zip", data, "application/zip")},
        data={"user_id": "bomb", "since_days": "0"},
    )
    assert r.status_code == 413 and "unzips to" in r.json()["detail"]
    assert client.get("/api/import/status").json().get("user_id") != "bomb"  # never started


def test_zip_size_is_checked_before_reading(monkeypatch, tmp_path):
    monkeypatch.setattr(limits, "MAX_UNZIPPED_BYTES", 1024 * 1024)
    path = tmp_path / "export.zip"
    path.write_bytes(big_zip())
    opened = []
    real_iterparse = apple_export.ET.iterparse
    monkeypatch.setattr(apple_export.ET, "iterparse", lambda *a, **k: opened.append(1) or real_iterparse(*a, **k))
    with db.connect() as conn, pytest.raises(apple_export.ExportTooLarge):
        apple_export.import_export(path, conn, "bomb_cli")
    assert not opened


def test_bad_zip_is_a_clear_400():
    r = client.post(
        "/api/import",
        files={"file": ("export.zip", b"not really a zip", "application/zip")},
        data={"user_id": "broken", "since_days": "0"},
    )
    assert r.status_code == 400 and "can't be opened" in r.json()["detail"]
