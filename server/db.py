"""
The server's SQLite database. It keeps only what Layer 1 needs: heart rate,
resting heart rate, HRV, sleep stages and each user's settings.

Every reading keeps its UTC offset, because which night a reading belongs to
depends on the person's local clock, not on UTC.
"""
import hashlib
import os
import sqlite3
import time
from pathlib import Path

import pandas as pd

# Tests point this somewhere else.
DB_PATH = os.environ.get("RECOVERY_DB", str(Path(__file__).with_name("platform.db")))

METRICS = {"heart_rate": "count/min", "resting_heart_rate": "count/min", "hrv_sdnn": "ms"}
STAGES = ("in_bed", "awake", "core", "deep", "rem", "asleep_unspecified")

# Back to Apple's names, so rows read from here look like rows read from an export.
HK_SLEEP_NAMES = {
    "in_bed": "HKCategoryValueSleepAnalysisInBed",
    "asleep_unspecified": "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "awake": "HKCategoryValueSleepAnalysisAwake",
    "core": "HKCategoryValueSleepAnalysisAsleepCore",
    "deep": "HKCategoryValueSleepAnalysisAsleepDeep",
    "rem": "HKCategoryValueSleepAnalysisAsleepREM",
}

# Real UTC offsets run from -12:00 to +14:00.
MIN_OFFSET_MIN, MAX_OFFSET_MIN = -12 * 60, 14 * 60

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id          TEXT PRIMARY KEY,
    timezone         TEXT,                          -- IANA name, e.g. America/Chicago
    update_time      TEXT NOT NULL DEFAULT '08:00', -- local time last night gets processed
    age              INTEGER,
    training         TEXT,
    training_days    TEXT,                          -- JSON list of weekdays
    units            TEXT,
    data_changed_ms  INTEGER,                       -- when new readings last arrived
    clock_local      TEXT                           -- demo users only: a fixed local clock
);
CREATE TABLE IF NOT EXISTS samples (
    id             TEXT NOT NULL,     -- HealthKit UUID, or a stable hash when there is none
    user_id        TEXT NOT NULL,
    metric         TEXT NOT NULL,     -- heart_rate, resting_heart_rate, hrv_sdnn
    value          REAL NOT NULL,
    start_ms       INTEGER NOT NULL,  -- UTC milliseconds
    end_ms         INTEGER NOT NULL,
    tz_offset_min  INTEGER NOT NULL,  -- local time = UTC + this
    source         TEXT,
    -- Per user: the same phone can sync under two tester names, with the same HealthKit UUIDs.
    PRIMARY KEY (user_id, id)
);
CREATE TABLE IF NOT EXISTS sleep_stages (
    id            TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    stage         TEXT NOT NULL,      -- in_bed, awake, core, deep, rem, asleep_unspecified
    start_ms      INTEGER NOT NULL,
    end_ms        INTEGER NOT NULL,
    start_tz_min  INTEGER NOT NULL,   -- two offsets since a night can cross a clock change
    end_tz_min    INTEGER NOT NULL,
    source        TEXT,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS idx_samples_user ON samples(user_id, start_ms);
CREATE INDEX IF NOT EXISTS idx_sleep_user ON sleep_stages(user_id, start_ms);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)
        # Databases made before a column existed get it added here.
        have = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
        if "clock_local" not in have:
            conn.execute("ALTER TABLE users ADD COLUMN clock_local TEXT")
        # Early databases keyed readings by id alone. Rebuild those tables keyed by (user_id, id).
        for table in ("samples", "sleep_stages"):
            key = [r["name"] for r in sorted(conn.execute(f"PRAGMA table_info({table})"), key=lambda r: r["pk"])
                   if r["pk"]]
            if key == ["id"]:
                conn.execute(f"ALTER TABLE {table} RENAME TO {table}_old")
                conn.executescript(SCHEMA)
                conn.execute(f"INSERT OR IGNORE INTO {table} SELECT * FROM {table}_old")
                conn.execute(f"DROP TABLE {table}_old")
                conn.executescript(SCHEMA)   # the index went with the old table, so make it again


def stable_id(*parts) -> str:
    """Exports, Health Auto Export and Shortcuts have no HealthKit UUIDs, so build a repeatable one."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def sample_id(user_id, metric, start_ms, end_ms, value, source) -> str:
    return stable_id(user_id, metric, start_ms, end_ms, round(float(value), 3), source)


def sleep_id(user_id, stage, start_ms, end_ms, source) -> str:
    return stable_id(user_id, "sleep", stage, start_ms, end_ms, source)


def valid_offset(minutes) -> bool:
    return isinstance(minutes, int) and MIN_OFFSET_MIN <= minutes <= MAX_OFFSET_MIN


def add_readings(conn: sqlite3.Connection, user_id: str, samples=(), stages=()) -> int:
    """
    Save readings and return how many were new. Repeats are ignored, so sending
    the same data twice is safe.

    samples: (id, metric, value, start_ms, end_ms, tz_offset_min, source)
    stages:  (id, stage, start_ms, end_ms, start_tz_min, end_tz_min, source)
    """
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    before = conn.total_changes
    conn.executemany("INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?)",
                     [(s[0], user_id, *s[1:]) for s in samples])
    conn.executemany("INSERT OR IGNORE INTO sleep_stages VALUES (?,?,?,?,?,?,?,?)",
                     [(s[0], user_id, *s[1:]) for s in stages])
    added = conn.total_changes - before
    if added:
        # Step 2 uses this to reprocess only when something actually changed.
        conn.execute("UPDATE users SET data_changed_ms = ? WHERE user_id = ?",
                     (int(time.time() * 1000), user_id))
    return added


def _local(ms: pd.Series, offset_min: pd.Series) -> pd.Series:
    return (pd.to_datetime(ms, unit="ms") + pd.to_timedelta(offset_min, unit="min"))


def load_records(conn: sqlite3.Connection, user_id: str, since_ms: int | None = None,
                 sleep_only: bool = False) -> pd.DataFrame:
    """
    A user's readings in the same shape as preprocessing's load_export(), so the
    tested pipeline runs on database rows without any changes.
    since_ms and sleep_only are for quick looks at recent sleep, not for processing.
    """
    since = since_ms if since_ms is not None else -2**62
    q = pd.read_sql_query("SELECT metric, value, start_ms, end_ms, tz_offset_min AS start_tz, "
                          "tz_offset_min AS end_tz, source FROM samples WHERE user_id = ? AND end_ms >= ?"
                          + (" AND 0" if sleep_only else ""),
                          conn, params=(user_id, since))
    q["kind"] = "quantity"
    q["stage"] = None
    q["unit"] = q["metric"].map(METRICS)
    q["raw_value"] = q["value"].astype(str)

    s = pd.read_sql_query("SELECT stage, start_ms, end_ms, start_tz_min AS start_tz, end_tz_min AS end_tz, "
                          "source FROM sleep_stages WHERE user_id = ? AND end_ms >= ?",
                          conn, params=(user_id, since))
    s["kind"] = "sleep"
    s["metric"] = "sleep_analysis"
    s["value"] = float("nan")
    s["unit"] = None
    s["raw_value"] = s["stage"].map(HK_SLEEP_NAMES)

    df = pd.concat([q, s], ignore_index=True) if len(s) else q
    df["source"] = df["source"].fillna("")
    df["value"] = df["value"].astype(float)
    df["stage"] = df["stage"].where(df["kind"] == "sleep")  # NaN for non-sleep rows, like load_export
    for side in ("start", "end"):
        df[f"{side}_utc"] = pd.to_datetime(df[f"{side}_ms"], unit="ms", utc=True)
        df[f"{side}_local"] = _local(df[f"{side}_ms"], df[f"{side}_tz"])
    cols = ["kind", "metric", "raw_value", "unit", "source", "start_utc", "end_utc",
            "start_local", "end_local", "value", "stage"]
    # Stable order so every run sees the rows the same way.
    df = df.sort_values(["start_utc", "end_utc", "metric", "source"], kind="stable")
    return df[cols].reset_index(drop=True)
