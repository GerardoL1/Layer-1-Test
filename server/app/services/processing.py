"""
Runs the Layer 1 preprocessing on the server.

It reuses DailyProcessor from preprocessing/ unchanged, so the server gives the
same nightly table as the tested pipeline. Between runs the processor's memory
lives in the database: the nightly rows in `nights` and what each run did in `runs`.

A run happens after new data arrives, and before the app reads results, but only
when something changed: new readings, or the clock passing the user's update time.
"""

import json
import threading
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from app.core import db
from app.core.json_values import clean
from app.readiness.features import build_features
from app.readiness.model import get_model
from layer1 import config as C
from layer1 import incremental as I
from layer1 import pipeline as P

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
-- The first score each night got, with the exact inputs behind it, for training the readiness model.
-- Written once when a night first appears and never overwritten, even when late data redoes the night.
CREATE TABLE IF NOT EXISTS readiness_snapshots (
    user_id        TEXT NOT NULL,
    night_date     TEXT NOT NULL,
    taken_at_ms    INTEGER NOT NULL,   -- real UTC time of the run that added the night
    taken_local    TEXT NOT NULL,      -- the user's local clock at that run
    catch_up       INTEGER NOT NULL,   -- 1 when a newer night came in the same run, so Today never showed this one
    model_version  TEXT NOT NULL,
    score          INTEGER,
    status         TEXT NOT NULL,
    confidence     TEXT,
    contributions  TEXT NOT NULL,      -- JSON list
    illness_flag   INTEGER NOT NULL,
    features       TEXT NOT NULL,      -- JSON, exactly what the model was given
    PRIMARY KEY (user_id, night_date)
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
    Demo users have a fixed clock instead.
    """
    row = conn.execute("SELECT timezone, clock_local FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row and row["clock_local"]:
        return datetime.fromisoformat(row["clock_local"])
    if row and row["timezone"]:
        try:
            return now_utc.astimezone(ZoneInfo(row["timezone"])).replace(tzinfo=None)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    latest = conn.execute(
        "SELECT tz FROM (SELECT start_ms, tz_offset_min AS tz FROM samples WHERE user_id = ? "
        "UNION ALL SELECT start_ms, end_tz_min FROM sleep_stages WHERE user_id = ?) "
        "ORDER BY start_ms DESC LIMIT 1",
        (user_id, user_id),
    ).fetchone()
    offset = latest["tz"] if latest else 0
    return (now_utc + timedelta(minutes=offset)).replace(tzinfo=None)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- saving and loading nightly rows


def save_nights(conn, user_id: str, nights: pd.DataFrame):
    rows = []
    for rec in nights.to_dict(orient="records"):
        data = {k: clean(v) for k, v in rec.items()}
        rows.append((user_id, data["night_date"], json.dumps(data)))
    conn.execute("DELETE FROM nights WHERE user_id = ?", (user_id,))
    conn.executemany("INSERT INTO nights VALUES (?,?,?)", rows)


def snapshot_new_nights(conn, user_id: str, new_nights: list, now_utc: datetime, sync: datetime):
    """
    Scores each night that just appeared and keeps that first result, with its inputs, in readiness_snapshots.
    It's scored from the saved rows, exactly as Today reads them. A night that's already there is left alone,
    so what the model saw that morning survives late data and rebuilds.
    """
    if not new_nights:
        return
    nights = load_nights(conn, user_id)
    dates = list(nights["night_date"])
    # Today shows the newest saved night, so only that one counts as shown. A history import that adds older
    # nights after it has been shown makes every one of them catch-up.
    newest = dates[-1]
    model = get_model()
    rows = []
    for night in new_nights:
        if night not in dates:
            continue
        i = dates.index(night)
        features = build_features(nights.iloc[: i + 1])
        result = model.score(features)
        rows.append(
            (
                user_id,
                night.isoformat(),
                int(now_utc.timestamp() * 1000),
                sync.isoformat(),
                int(night != newest),
                result.model_version,
                result.score,
                result.status,
                result.confidence,
                json.dumps([asdict(c) for c in result.contributions]),
                int(result.illness_flag),
                json.dumps(features),
            )
        )
    conn.executemany("INSERT OR IGNORE INTO readiness_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)


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


def last_run(conn, user_id: str):
    return conn.execute("SELECT * FROM runs WHERE user_id = ? ORDER BY run DESC LIMIT 1", (user_id,)).fetchone()


def needs_processing(conn, user_id: str, now_utc: datetime | None = None) -> bool:
    """True when new readings arrived, or a new night became ready, since the last run."""
    user = conn.execute("SELECT data_changed_ms, update_time FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user is None or user["data_changed_ms"] is None:
        return False
    last = last_run(conn, user_id)
    if last is None or (last["data_changed_ms"] or 0) < user["data_changed_ms"]:
        return True
    if last["ready_through"] is None:
        return False  # nothing to process until sleep data arrives
    sync = local_now(conn, user_id, now_utc or utc_now())
    ready = I.scheduled_ready_night(sync, parse_update_time(user["update_time"]))
    return ready > date.fromisoformat(last["ready_through"])


# ---------------------------------------------------------------- one run


def _dates(text) -> list:
    return [date.fromisoformat(d) for d in json.loads(text or "[]")]


def _reaches_back(changed_from_ms: int | None, last) -> bool:
    """
    True when readings that arrived since the last run could belong to a night the next run
    won't redo. That happens when data comes in pieces (a first sync in chunks, an import that
    someone reads halfway, sleep and heart rate sent separately). Those nights must be rebuilt,
    or they'd keep what was worked out from half the data.
    """
    if changed_from_ms is None or last is None or last["ready_through"] is None:
        return False
    # A reading belongs to a night up to a day and a half earlier (nights are labelled onset minus 12 h).
    earliest_night = (datetime(1970, 1, 1) + timedelta(milliseconds=changed_from_ms) - timedelta(hours=36)).date()
    # Each run redoes the newest processed night and the RECOMPUTE_NIGHTS - 2 before it.
    oldest_redone = date.fromisoformat(last["ready_through"]) - timedelta(days=C.RECOMPUTE_NIGHTS - 2)
    return earliest_night < oldest_redone


def process_user(
    user_id: str, now_utc: datetime | None = None, update_now: bool = False, force: bool = False
) -> I.RunReport | None:
    """
    Process a user's ready nights with DailyProcessor and save the result.
    Skips the work when nothing changed, unless update_now or force is set.
    force also starts over from all saved readings instead of the saved nights.
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
        last = last_run(conn, user_id)
        # Start over when asked to, or when new readings reach back past the nights a run redoes.
        # Otherwise carry on from the saved nights, which only redoes the last few.
        rebuild = force or _reaches_back(user["changed_from_ms"], last)
        if not rebuild:
            proc.nights = load_nights(conn, user_id)
        # A rebuild works every night out again. Only nights that weren't saved before count as new.
        saved_before = (
            {
                date.fromisoformat(r[0])
                for r in conn.execute("SELECT night_date FROM nights WHERE user_id = ?", (user_id,))
            }
            if rebuild
            else set()
        )
        if last is not None and not rebuild:
            # DailyProcessor redoes the nights its previous run added for the first time.
            # The server may run several times a day, so remember the last run that added
            # nights, not just the last run. That only ever redoes more, never less.
            added = conn.execute(
                "SELECT new_nights FROM runs WHERE user_id = ? AND new_nights != '[]' ORDER BY run DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            proc.reports = [
                I.RunReport(
                    last["run"],
                    datetime.fromisoformat(last["sync_local"]),
                    {},
                    0,
                    0,
                    _dates(added["new_nights"]) if added else [],
                    [],
                    {},
                    None,
                )
            ]

        sync = local_now(conn, user_id, now_utc)
        # A rebuild starts from nothing, so on its own it would only keep nights up to the scheduled
        # update time. If Update now already processed last night, rebuild the same way so it stays.
        scheduled = I.scheduled_ready_night(sync, parse_update_time(user["update_time"]))
        early = rebuild and last is not None and last["ready_through"] is not None
        keep_early = early and date.fromisoformat(last["ready_through"]) > scheduled
        # All saved readings go in as one batch. The processor cleans them and keeps
        # only what it needs, so this matches feeding them in day by day.
        report = proc.sync(records, sync, update_now=update_now or keep_early)
        if saved_before:
            report.new_nights = [d for d in report.new_nights if d not in saved_before]

        if len(proc.nights):
            save_nights(conn, user_id, proc.nights)
            snapshot_new_nights(conn, user_id, report.new_nights, now_utc, sync)
        run = (last["run"] + 1) if last is not None else 1
        conn.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                user_id,
                run,
                int(now_utc.timestamp() * 1000),
                sync.isoformat(),
                int(update_now),
                report.ready_through.isoformat() if report.ready_through else None,
                json.dumps([d.isoformat() for d in report.new_nights]),
                json.dumps([d.isoformat() for d in report.recomputed_nights]),
                json.dumps({d.isoformat(): cols for d, cols in report.changed.items()}),
                seen_change,
            ),
        )
        # These readings are now in the saved nights. Readings that arrived during this run keep
        # their mark, so the next run still knows how far back they reach.
        conn.execute(
            "UPDATE users SET changed_from_ms = NULL WHERE user_id = ? AND data_changed_ms IS ?", (user_id, seen_change)
        )
        report.run = run
        return report


def ensure_processed(user_id: str, now_utc: datetime | None = None) -> I.RunReport | None:
    """Call before reading results. Does nothing when the saved results are current."""
    return process_user(user_id, now_utc)
