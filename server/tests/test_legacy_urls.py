"""
The URLs from before /api/v1 still work for older app builds and phone automations.
Each one must give the same answer as its new URL, log a warning and say it's deprecated.

    python -m pytest -q tests/test_legacy_urls.py
"""

import logging

import main
from conftest import SAMPLE_DATA, SAMPLES
from fastapi.testclient import TestClient

from app.core import limits
from app.routers.legacy import REPLACEMENTS

client = TestClient(main.app)

V1 = "/api/v1/users/demo-sam"


def old(method: str, path: str, caplog, **kwargs):
    """Calls an old URL and checks it says it's deprecated, in the log and (when it worked) in the reply."""
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="recovery.deprecated"):
        r = client.request(method, path, **kwargs)
    if r.is_success:  # FastAPI builds error replies itself, without the route's headers
        assert r.headers.get("deprecation", "").startswith("@"), path
    assert any("deprecated URL" in m and "switch to" in m for m in caplog.messages), path
    return r


def test_every_old_route_has_a_replacement():
    paths = main.app.openapi()["paths"]
    deprecated = {f"{m.upper()} {p}" for p, ops in paths.items() for m, op in ops.items() if op.get("deprecated")}
    assert deprecated == set(REPLACEMENTS)


def test_old_screen_urls_match_the_new_ones(caplog):
    assert old("POST", "/api/demo/sam", caplog).json() == client.post("/api/v1/demo-users/sam").json()
    q = {"user_id": "demo-sam"}
    for name in ("today", "profile", "settings"):
        assert old("GET", f"/api/{name}", caplog, params=q).json() == client.get(f"{V1}/{name}").json()
    for n in (14, 28, 90):
        got = old("GET", "/api/trends", caplog, params={**q, "nights": n}).json()
        assert got == client.get(f"{V1}/trends", params={"nights": n}).json()
    assert old("GET", "/api/trends", caplog, params={**q, "nights": 7}).status_code == 422
    assert old("PUT", "/api/settings", caplog, params=q, json={"age": 30}).json()["age"] == 30
    assert client.get(f"{V1}/settings").json()["age"] == 30
    assert old("POST", "/api/update-now", caplog, params=q).json() == client.post(f"{V1}/processing-runs").json()


def test_old_ingest_urls_still_store_data(caplog):
    sample = {"uuid": "legacy-1", "metric": "heart_rate", "value": 50.0, "start_ms": 1, "end_ms": 1}
    body = {"user_id": "legacy", "samples": [{**sample, "tz_offset_min": 0}]}
    assert old("POST", "/upload", caplog, json=body).json() == {"received": 1, "new": 1}
    assert old("POST", "/upload", caplog, json={"samples": []}).status_code == 422  # the old body needed user_id

    hae = {"data": {"metrics": [{"name": "heart_rate", "data": [{"date": "2026-09-30 23:14:05 -0500", "Avg": 52}]}]}}
    assert old("POST", "/api/hae?user_id=legacy", caplog, json=hae).json()["new"] == 1

    rows = "2026-09-30T23:30:00-05:00 | 2026-09-30T23:30:00-05:00 | 53 | Apple Watch"
    r = old("POST", "/api/shortcut", caplog, data={"user": " legacy ", "metric": "heart_rate", "rows": rows})
    assert r.text == "heart_rate: received 1, new 1"


def test_old_import_urls(caplog):
    with open(SAMPLE_DATA / SAMPLES["jordan"], "rb") as f:
        r = old(
            "POST",
            "/api/import",
            caplog,
            files={"file": ("export.zip", f, "application/zip")},
            data={"user_id": "legacy_import", "since_days": "0"},
        )
    assert r.status_code == 200 and r.json() == {"started": True}
    status = old("GET", "/api/import/status", caplog).json()
    assert status["state"] == "done" and status["user_id"] == "legacy_import"
    assert client.get(f"/api/v1/users/legacy_import/imports/{status['import_id']}").json() == status


def test_old_urls_keep_their_size_limits(monkeypatch):
    monkeypatch.setitem(limits.LIMITS_BY_PATH, "/api/hae", 100)
    r = client.post("/api/hae?user_id=big_legacy", json={"data": {"metrics": []}, "padding": "x" * 200})
    assert r.status_code == 413


def test_new_urls_are_not_deprecated():
    assert "deprecation" not in client.get(f"{V1}/settings").headers
    assert "deprecation" not in client.get("/health").headers
