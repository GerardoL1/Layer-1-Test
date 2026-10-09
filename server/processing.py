"""
Runs the Layer 1 preprocessing on the server.

It reuses DailyProcessor from preprocessing/ unchanged, so the server gives the
same nightly table as the tested pipeline. Between runs the processor's memory
lives in the database: the nightly rows in `nights` and what each run did in `runs`.

A run happens after new data arrives, and before the app reads results, but only
when something changed: new readings, or the clock passing the user's update time.
"""
import json
import math
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
import pandas as pd

import db

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "preprocessing"))
import config as C  # noqa: E402
import incremental as I  # noqa: E402
import pipeline as P  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS nights (
    user_id     TEXT NOT NULL,
    night_date  TEXT NOT NULL,      -- YYYY-MM-DD, the evening the night started
    data        TEXT NOT NULL,      -- every column DailyProcessor keeps, as JSON
    PRIMARY KEY (user_id, night_date)
);
CREATE TABLE IF NOT EXISTS runs (
    user_id          TEXT NOT NULL,
    run              INTEGER NOT NULL,
    run_at_ms        INTEGER NOT NULL,   -- real UTC time of the run
    sync_local       TEXT NOT NULL,      -- the user's local clock the run used
    update_now       INTEGER NOT NULL,
    ready_through    TEXT,
    new_nights       TEXT NOT NULL,      -- JSON lists of dates
    recomputed       TEXT NOT NULL,
    changed          TEXT NOT NULL,      -- JSON {night: [columns that changed]}
    data_changed_ms  INTEGER,            -- users.data_changed_ms this run had seen
    PRIMARY KEY (user_id, run)
);
"""

DATE_COLUMNS = ("night_date",)
TIME_COLUMNS = ("sleep_onset", "final_wake")
TEXT_COLUMNS = ("tib_source", "quality_notes")

# One run at a time per user, since data can arrive while the app is reading.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


def init_db():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


# ---------------------------------------------------------------- the user's clock

def parse_update_time(text: str | None) -> tuple[int, int]:
    try:
        h, m = (int(x) for x in str(text).split(":"))
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except (TypeError, ValueError):
        pass
    return C.DEFAULT_UPDATE_TIME


def local_now(conn, user_id: str, now_utc: datetime) -> datetime:
    """
    The user's wall-clock time, without a time zone (the pipeline works in local time).
    Uses the time zone from their settings, or else the offset of their newest reading.
    """
    row = conn.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row and row["timezone"]:
        try:
            return now_utc.astimezone(ZoneInfo(row["timezone"])).replace(tzinfo=None)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    latest = conn.execute(
        "SELECT tz FROM (SELECT start_ms, tz_offset_min AS tz FROM samples WHERE user_id = ? "
        "UNION ALL SELECT start_ms, end_tz_min FROM sleep_stages WHERE user_id = ?) "
        "ORDER BY start_ms DESC LIMIT 1", (user_id, user_id)).fetchone()
    offset = latest["tz"] if latest else 0
    return (now_utc + timedelta(minutes=offset)).replace(tzinfo=None)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- saving and loading nightly rows

def _to_json_value(v):
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, np.floating):
        return None if np.isnan(v) else float(v)
    if pd.isna(v):
        return None
    return v


def save_nights(conn, user_id: str, nights: pd.DataFrame):
    rows = []
    for rec in nights.to_dict(orient="records"):
        data = {k: _to_json_value(v) for k, v in rec.items()}
        rows.append((user_id, data["night_date"], json.dumps(data)))
    conn.execute("DELETE FROM nights WHERE user_id = ?", (user_id,))
    conn.executemany("INSERT INTO nights VALUES (?,?,?)", rows)


def load_nights(conn, user_id: str) -> pd.DataFrame:
    """The saved nightly rows, typed the way DailyProcessor left them."""
    rows = conn.execute("SELECT data FROM nights WHERE user_id = ? ORDER BY night_date", (user_id,)).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame([json.loads(r["data"]) for r in rows])
    for col in df.columns:
        if col in DATE_COLUMNS:
            df[col] = [date.fromisoformat(v) for v in df[col]]
        elif col in TIME_COLUMNS:
            df[col] = pd.to_datetime(df[col])
        elif col in TEXT_COLUMNS:
            df[col] = df[col].astype(object)
        elif col.startswith(("flag_", "usable_")):
            df[col] = df[col].fillna(False).astype(bool)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df


def ml_table(conn, user_id: str) -> pd.DataFrame:
    """The ML-ready table (one row per night) from the saved rows."""
    nights = load_nights(conn, user_id)
    if nights.empty:
        return pd.DataFrame(columns=list(P.ML_COLUMNS))
    return P.build_ml_table(nights, user_id)


# ---------------------------------------------------------------- deciding when to run

def _last_run(conn, user_id: str):
    return conn.execute("SELECT * FROM runs WHERE user_id = ? ORDER BY run DESC LIMIT 1", (user_id,)).fetchone()


def needs_processing(conn, user_id: str, now_utc: datetime | None = None) -> bool:
    """True when new readings arrived, or a new night became ready, since the last run."""
    user = conn.execute("SELECT data_changed_ms, update_time FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user is None or user["data_changed_ms"] is None:
        return False
    last = _last_run(conn, user_id)
    if last is None or (last["data_changed_ms"] or 0) < user["data_changed_ms"]:
        return True
    if last["ready_through"] is None:
        return False   # nothing to process until sleep data arrives
    sync = local_now(conn, user_id, now_utc or utc_now())
    ready = I.scheduled_ready_night(sync, parse_update_time(user["update_time"]))
    return ready > date.fromisoformat(last["ready_through"])


# ---------------------------------------------------------------- one run

def _dates(text) -> list:
    return [date.fromisoformat(d) for d in json.loads(text or "[]")]


def process_user(user_id: str, now_utc: datetime | None = None, update_now: bool = False,
                 force: bool = False) -> I.RunReport | None:
    """
    Process a user's ready nights with DailyProcessor and save the result.
    Skips the work when nothing changed, unless update_now or force is set.
    """
    now_utc = now_utc or utc_now()
    with _lock(user_id), db.connect() as conn:
        if not (force or update_now or needs_processing(conn, user_id, now_utc)):
            return None
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if user is None:
            return None
        seen_change = user["data_changed_ms"]
        records = db.load_records(conn, user_id)
        if records.empty:
            return None

        proc = I.DailyProcessor(user_id, update_time=parse_update_time(user["update_time"]))
        proc.nights = load_nights(conn, user_id)
        last = _last_run(conn, user_id)
        if last is not None:
            # DailyProcessor redoes the nights its previous run added for the first time.
            # The server may run several times a day, so remember the last run that added
            # nights, not just the last run. That only ever redoes more, never less.
            added = conn.execute("SELECT new_nights FROM runs WHERE user_id = ? AND new_nights != '[]' "
                                 "ORDER BY run DESC LIMIT 1", (user_id,)).fetchone()
            proc.reports = [I.RunReport(last["run"], datetime.fromisoformat(last["sync_local"]), {}, 0, 0,
                                        _dates(added["new_nights"]) if added else [], [], {}, None)]

        sync = local_now(conn, user_id, now_utc)
        # All saved readings go in as one batch. The processor cleans them and keeps
        # only what it needs, so this matches feeding them in day by day.
        report = proc.sync(records, sync, update_now=update_now)

        if len(proc.nights):
            save_nights(conn, user_id, proc.nights)
        run = (last["run"] + 1) if last is not None else 1
        conn.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)", (
            user_id, run, int(now_utc.timestamp() * 1000), sync.isoformat(), int(update_now),
            report.ready_through.isoformat() if report.ready_through else None,
            json.dumps([d.isoformat() for d in report.new_nights]),
            json.dumps([d.isoformat() for d in report.recomputed_nights]),
            json.dumps({d.isoformat(): cols for d, cols in report.changed.items()}),
            seen_change))
        report.run = run
        return report


def ensure_processed(user_id: str, now_utc: datetime | None = None) -> I.RunReport | None:
    """Call before reading results. Does nothing when the saved results are current."""
    return process_user(user_id, now_utc)
