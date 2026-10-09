"""
Edge cases on the server: clock changes, two runs at once, changing the update
time, and the phone and server agreeing on names.

    python -m pytest -q tests/test_edges.py
"""
import re
import threading
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

import db
import main
import processing
from conftest import ROOT

client = TestClient(main.app)

HOUR = 3600 * 1000


def ms(*args) -> int:
    return int(datetime(*args, tzinfo=timezone.utc).timestamp() * 1000)


def night_payload(user, start_ms, end_ms, start_tz, end_tz, prefix="n"):
    """One night the way the iPhone app sends it: a sleep stage plus heart rate every 5 minutes."""
    hr = [{"uuid": f"{prefix}-hr-{t}", "metric": "heart_rate", "value": 52.0, "start_ms": t, "end_ms": t,
           "tz_offset_min": start_tz if t < (start_ms + end_ms) // 2 else end_tz, "source": "Sam’s Apple Watch"}
          for t in range(start_ms, end_ms, 5 * 60 * 1000)]
    sleep = [{"uuid": f"{prefix}-core", "stage": "core", "start_ms": start_ms, "end_ms": end_ms,
              "start_tz_min": start_tz, "end_tz_min": end_tz, "source": "Sam’s Apple Watch"}]
    return {"user_id": user, "samples": hr, "sleep": sleep}


def test_night_across_the_clock_change():
    # US clocks go back at 2 am on 1 Nov 2026. Asleep 22:00 CDT (-5 h) to 06:00 CST (-6 h): 9 real hours.
    user = "dst"
    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, "2026-11-01T09:00:00"))
    r = client.post("/upload", json=night_payload(user, ms(2026, 11, 1, 3), ms(2026, 11, 1, 12), -300, -360))
    assert r.status_code == 200
    with db.connect() as conn:
        night = processing.load_nights(conn, user).set_index("night_date").loc[date(2026, 10, 31)]
    assert night["tst_min"] == 540                          # real time asleep, not 8 clock hours
    assert str(night["sleep_onset"]) == "2026-10-31 22:00:00"
    assert str(night["final_wake"]) == "2026-11-01 06:00:00"


def test_two_runs_at_once_dont_clash():
    user = "busy"
    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, "2026-10-02T09:00:00"))
    client.post("/upload", json=night_payload(user, ms(2026, 10, 1, 5), ms(2026, 10, 1, 13), -420, -420))
    errors = []

    def run():
        try:
            processing.process_user(user, force=True)
        except Exception as e:   # collected so the test can report it
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    with db.connect() as conn:
        runs = [r[0] for r in conn.execute("SELECT run FROM runs WHERE user_id = ? ORDER BY run", (user,))]
        nights = processing.load_nights(conn, user)
    assert runs == list(range(1, len(runs) + 1))           # numbered in order, none lost or doubled
    assert len(nights) == len(set(nights["night_date"]))    # one row per night


def test_changing_the_update_time():
    user = "late_riser"
    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, "2026-10-02T07:30:00"))
    client.post("/upload", json=night_payload(user, ms(2026, 10, 2, 5), ms(2026, 10, 2, 13), -420, -420))
    processing.process_user(user, force=True)

    def needs_at(clock):
        with db.connect() as conn:
            conn.execute("UPDATE users SET clock_local = ? WHERE user_id = ?", (clock, user))
            return processing.needs_processing(conn, user)

    assert needs_at("2026-10-02T08:30:00")        # passed the default 8:00
    client.put("/api/settings", params={"user_id": user}, json={"update_time": "10:00"})
    assert not needs_at("2026-10-02T08:30:00")    # now waits until 10:00
    assert needs_at("2026-10-02T10:05:00")


def test_phone_and_server_use_the_same_names():
    # mobile/src/health/convert.ts lists what the phone sends. It must match what the server accepts.
    ts = (ROOT / "mobile" / "src" / "health" / "convert.ts").read_text(encoding="utf-8")
    stages = set(re.findall(r"^\s*\d: '(\w+)',", ts, re.M))
    metrics = set(re.findall(r"'(heart_rate|resting_heart_rate|hrv_sdnn|\w+)'", ts.split("metric:")[1].split(";")[0]))
    assert stages == set(db.STAGES)
    assert metrics == set(db.METRICS)


def test_same_phone_two_tester_names():
    # HealthKit UUIDs are the same whichever tester name the phone syncs under.
    body = night_payload("first_name", ms(2026, 9, 20, 5), ms(2026, 9, 20, 13), -420, -420, prefix="same")
    assert client.post("/upload", json=body).json()["new"] > 0
    body["user_id"] = "second_name"
    assert client.post("/upload", json=body).json()["new"] > 0     # stored again for the new name
    assert client.post("/upload", json=body).json()["new"] == 0    # but repeats are still ignored


def test_old_database_is_upgraded(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("""
        CREATE TABLE samples (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, metric TEXT NOT NULL, value REAL NOT NULL,
            start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, tz_offset_min INTEGER NOT NULL, source TEXT);
        CREATE TABLE sleep_stages (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, stage TEXT NOT NULL,
            start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL, start_tz_min INTEGER NOT NULL,
            end_tz_min INTEGER NOT NULL, source TEXT);
        CREATE INDEX idx_samples_user ON samples(user_id, start_ms);
        INSERT INTO samples VALUES ('a', 'u', 'heart_rate', 50, 1, 1, 0, 'Apple Watch');
    """)
    old.commit()
    old.close()
    monkeypatch.setattr(db, "DB_PATH", str(path))
    db.init_db()
    with db.connect() as conn:
        key = [r["name"] for r in sorted(conn.execute("PRAGMA table_info(samples)"), key=lambda r: r["pk"]) if r["pk"]]
        rows = conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
        indexes = {r["name"] for r in conn.execute("PRAGMA index_list(samples)")}
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert key == ["user_id", "id"] and rows == 1
    assert "idx_samples_user" in indexes and "samples_old" not in tables
