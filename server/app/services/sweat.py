"""
Sweat sessions (Layer 3). A Nix export is read by layer3.nix, its local times get the person's UTC
offset, it's matched to a workout and saved, one sweat session per workout, the more precise data
winning. Also the Hydration line for Today, the daily sweat for the Trends chart, and the per-day
table the readiness model can join. See docs/layer3_spec.md.
"""

import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from datetime import time as clock_time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from fastapi import HTTPException

from app.core import db
from app.routers.workouts import save_workout
from app.routers.workouts import workout_reply as workout_out
from app.schemas.workouts import WorkoutIn
from app.services import processing
from app.services.time_checks import local_time, require_time
from app.services.users import require_user
from layer3 import config as C3
from layer3.nix import NixFileError, NixSession, read_nix

SCHEMA = """
-- One sweat session per workout, from a Nix import or typed in by hand. Numbers are in ml, L/h, mg and mg/L
-- whatever the file used. Sodium and electrolytes are NULL (never 0) when Nix picked up no sweat.
CREATE TABLE IF NOT EXISTS sweat_sessions (
    user_id                TEXT NOT NULL,
    id                     TEXT NOT NULL,     -- nix-<start>-<end> or manual-<workout id>, so a repeat replaces itself
    workout_id             TEXT NOT NULL,     -- the Layer 1 workouts table
    source                 TEXT NOT NULL,     -- nix, manual
    start_ms               INTEGER NOT NULL,
    end_ms                 INTEGER NOT NULL,
    start_tz_min           INTEGER NOT NULL,
    end_tz_min             INTEGER NOT NULL,
    duration_min           REAL NOT NULL,
    fluid_loss_ml          REAL NOT NULL,
    sweat_rate_l_h         REAL,
    sodium_mg              REAL,
    sodium_rate_mg_h       REAL,
    electrolytes_mg        REAL,
    electrolyte_rate_mg_h  REAL,
    sweat_composition_mg_l REAL,
    nix_index              REAL,
    workout_type           TEXT,
    sweat_detected         INTEGER NOT NULL,
    unit_system            TEXT NOT NULL,     -- metric, customary, manual (how precise the numbers are)
    warnings               TEXT NOT NULL,     -- JSON list
    imported_at_ms         INTEGER NOT NULL,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, workout_id)
);
-- Nix's minute-by-minute series for each imported session.
CREATE TABLE IF NOT EXISTS sweat_minutes (
    user_id               TEXT NOT NULL,
    session_id            TEXT NOT NULL,
    minute                INTEGER NOT NULL,
    sweat_rate_l_h        REAL,
    respiration_rate_l_h  REAL,
    total_fluid_ml        REAL,
    electrolyte_rate_mg_h REAL,
    total_electrolytes_mg REAL,
    sodium_rate_mg_h      REAL,
    total_sodium_mg       REAL,
    PRIMARY KEY (user_id, session_id, minute)
);
"""

HOUR_MS = 3600 * 1000
# Workouts this many days either side of a file are offered when nothing overlaps it, closest first.
NEARBY_DAYS = 7
NEARBY_MAX = 5
# Same limit as workouts, so a session always fits the workout it's saved as.
MAX_SESSION_HOURS = 24
# Placeholder until the team decides the advice: below this much sweat, Today shows no Hydration line.
HYDRATION_MIN_ML = 250
# Placeholder too: the workout summary suggests drinking this many times the fluid lost, a common sports advice.
REHYDRATE_FACTOR = 1.5

ERR_PICK_WORKOUT = "This file doesn't match any workout. Pick one, or save it as a new workout."
ERR_NO_TIME_ZONE = "We don't know your time zone yet. Set it in Profile, then import the file again."
ERR_MORE_PRECISE = "More precise sweat data for this session is already saved, so it was kept."
ERR_KEEPS_SWEAT = (
    "This workout already has sweat data, and Nix picked up no sweat in this file (breathing loss only), "
    "so the sweat data was kept."
)
ERR_NO_SWEAT_DATA = "This workout has no sweat data yet."
ERR_BAD_OFFSET = "The phone sent an impossible UTC offset."
ERR_CLOCK_GAP = (
    "This file has a time that doesn't exist on the clock (the hour skipped when clocks go forward). "
    "Export the workout again from the Nix app."
)
ERR_NO_FILE = "Choose the Nix file to upload."
ERR_NO_LENGTH = "This file's workout starts and ends at the same time. Export the workout again from the Nix app."
ERR_BAD_FORM = "Part of the upload couldn't be read. Choose the Nix file and try again."
# Text fields in an upload (time zone, workout id) are tiny. Anything bigger is refused with ERR_BAD_FORM.
MAX_FORM_FIELD_BYTES = 1024

# The reader's duration and minutes checks compare local times. These are redone here with the real times.
_LOCAL_TIME_WARNINGS = tuple(w.split("{")[0] for w in (C3.WARN_DURATION_MISMATCH, C3.WARN_MINUTES_MISMATCH))

NUMBERS = (
    "fluid_loss_ml",
    "sweat_rate_l_h",
    "sodium_mg",
    "sodium_rate_mg_h",
    "electrolytes_mg",
    "electrolyte_rate_mg_h",
    "sweat_composition_mg_l",
    "nix_index",
)
MINUTE_COLUMNS = (
    "sweat_rate_l_h",
    "respiration_rate_l_h",
    "total_fluid_ml",
    "electrolyte_rate_mg_h",
    "total_electrolytes_mg",
    "sodium_rate_mg_h",
    "total_sodium_mg",
)
# Stored to a sensible precision, finer than any sensor gives.
PLACES = {"sweat_rate_l_h": 4, "respiration_rate_l_h": 4}


def init_db():
    with db.connect() as conn:
        conn.executescript(SCHEMA)


def _round(name: str, x: float | None) -> float | None:
    return None if x is None else round(x, PLACES.get(name, 1))


# ---------------------------------------------------------------- turning a Nix file into a session


def _parse(data: bytes) -> NixSession:
    try:
        return read_nix(data)
    except NixFileError as e:
        raise HTTPException(400, str(e)) from None


def utc_offsets(conn, user_id: str, local: datetime, phone_offset: int | None) -> list[int]:
    """
    The UTC offsets a Nix time could have (it has no time zone): from the Settings time zone for that date,
    else the newest reading's, else the phone's. Two in the hour repeated when clocks go back, and a time
    in the hour skipped when clocks go forward is refused.
    """
    user = conn.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user and user["timezone"]:
        try:
            zone = ZoneInfo(user["timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            zone = None
        if zone is not None:
            first = local.replace(tzinfo=zone, fold=0)
            # A skipped time comes back as a different wall-clock time after a round trip through UTC.
            if first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) != local:
                raise HTTPException(400, ERR_CLOCK_GAP)
            out = []
            for fold in (0, 1):
                off = local.replace(tzinfo=zone, fold=fold).utcoffset()
                if off is not None and int(off.total_seconds() // 60) not in out:
                    out.append(int(off.total_seconds() // 60))
            if out:
                return out
    latest = conn.execute(
        "SELECT tz FROM (SELECT start_ms, tz_offset_min AS tz FROM samples WHERE user_id = ? "
        "UNION ALL SELECT start_ms, end_tz_min FROM sleep_stages WHERE user_id = ?) "
        "ORDER BY start_ms DESC LIMIT 1",
        (user_id, user_id),
    ).fetchone()
    if latest:
        return [int(latest["tz"])]
    if phone_offset is not None:
        return [phone_offset]
    raise HTTPException(400, ERR_NO_TIME_ZONE)


def local_utc_ms(local: datetime, offset_min: int) -> int:
    return (local - timedelta(minutes=offset_min) - datetime(1970, 1, 1)) // timedelta(milliseconds=1)


def _real_times(conn, user_id: str, s: NixSession, phone_offset: int | None) -> tuple[int, int, int, int]:
    """
    Start and end in UTC with their offsets. In the repeated hour, the copy whose length fits the file's
    duration wins, and between equal fits the one overlapping a workout (else summer time, the first).
    """
    choices = []
    for start_tz in utc_offsets(conn, user_id, s.start_local, phone_offset):
        for end_tz in utc_offsets(conn, user_id, s.end_local, phone_offset):
            start_ms, end_ms = local_utc_ms(s.start_local, start_tz), local_utc_ms(s.end_local, end_tz)
            if end_ms >= start_ms:
                choices.append((start_ms, end_ms, start_tz, end_tz))
    if not choices:
        raise HTTPException(400, C3.ERR_END_BEFORE_START)

    def misfit(c: tuple[int, int, int, int]) -> float:
        return 0 if s.file_duration_min is None else abs((c[1] - c[0]) / 60000 - s.file_duration_min)

    best = min(misfit(c) for c in choices)
    ties = [c for c in choices if misfit(c) == best]

    def overlap(c: tuple[int, int, int, int]) -> int:
        matched, _ = _match(conn, user_id, c[0], c[1])
        return 0 if matched is None else min(matched["end_ms"], c[1]) - max(matched["start_ms"], c[0])

    return max(ties, key=overlap) if len(ties) > 1 else ties[0]


def _from_nix(conn, user_id: str, s: NixSession, phone_offset: int | None) -> tuple[dict, list[tuple]]:
    start_ms, end_ms, start_tz, end_tz = _real_times(conn, user_id, s, phone_offset)
    require_time(start_ms, start_tz, "The Nix workout start")
    require_time(end_ms, end_tz, "The Nix workout end")
    if end_ms - start_ms > MAX_SESSION_HOURS * HOUR_MS:
        raise HTTPException(400, f"A workout can't be longer than {MAX_SESSION_HOURS} hours.")
    if end_ms == start_ms:
        raise HTTPException(400, ERR_NO_LENGTH)
    span_min = (end_ms - start_ms) / 60000
    # The file's Duration is used only when it agrees with the real times. A far-off one is a broken file.
    file_min = s.file_duration_min
    used_min = span_min
    if file_min is not None and abs(file_min - span_min) <= C3.DURATION_CHECK_TOLERANCE_MIN:
        used_min = file_min
    warnings = [w for w in s.warnings if not w.startswith(_LOCAL_TIME_WARNINGS)]
    if abs(len(s.minutes) - used_min) > C3.MINUTES_CHECK_TOLERANCE:
        warnings.insert(0, C3.WARN_MINUTES_MISMATCH.format(rows=len(s.minutes), minutes=used_min))
    if s.file_duration_min is not None and abs(s.file_duration_min - span_min) > C3.DURATION_CHECK_TOLERANCE_MIN:
        warnings.insert(0, C3.WARN_DURATION_MISMATCH.format(duration=s.file_duration_min, span=span_min))
    session = {
        "id": f"nix-{start_ms}-{end_ms}",
        "workout_id": None,
        "source": "nix",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "start_tz_min": start_tz,
        "end_tz_min": end_tz,
        "duration_min": round(used_min, 1),
        "fluid_loss_ml": _round("fluid_loss_ml", s.fluid_loss_ml),
        "sweat_rate_l_h": _round("sweat_rate_l_h", s.sweat_rate_l_h),
        "sodium_mg": _round("sodium_mg", s.sodium_mg),
        "sodium_rate_mg_h": _round("sodium_rate_mg_h", s.sodium_rate_mg_h),
        "electrolytes_mg": _round("electrolytes_mg", s.electrolytes_mg),
        "electrolyte_rate_mg_h": _round("electrolyte_rate_mg_h", s.electrolyte_rate_mg_h),
        "sweat_composition_mg_l": _round("sweat_composition_mg_l", s.sweat_composition_mg_l),
        "nix_index": _round("nix_index", s.nix_index),
        "workout_type": s.workout_type,
        "sweat_detected": s.sweat_detected,
        "unit_system": s.unit_system,
        "warnings": warnings,
        "imported_at_ms": None,
    }
    minutes = [(m.minute, *(_round(c, getattr(m, c)) for c in MINUTE_COLUMNS)) for m in s.minutes]
    return session, minutes


# ---------------------------------------------------------------- workouts, and what's already saved


def _workout(conn, user_id: str, workout_id: str):
    row = conn.execute("SELECT * FROM workouts WHERE user_id = ? AND id = ?", (user_id, workout_id)).fetchone()
    if row is None:
        raise HTTPException(404, f"No workout '{workout_id}'.")
    return row


def _match(conn, user_id: str, start_ms: int, end_ms: int):
    """The workout overlapping the session most, and other workouts nearby, closest first."""
    slack = NEARBY_DAYS * 24 * HOUR_MS
    rows = conn.execute(
        "SELECT * FROM workouts WHERE user_id = ? AND end_ms >= ? AND start_ms <= ? ORDER BY start_ms",
        (user_id, start_ms - slack, end_ms + slack),
    ).fetchall()
    overlap = {r["id"]: min(r["end_ms"], end_ms) - max(r["start_ms"], start_ms) for r in rows}
    hits = [r for r in rows if overlap[r["id"]] > 0]
    matched = max(hits, key=lambda r: overlap[r["id"]]) if hits else None  # ties keep the earliest
    others = [r for r in rows if matched is None or r["id"] != matched["id"]]
    nearby = sorted(others, key=lambda r: abs(r["start_ms"] - start_ms))[:NEARBY_MAX]
    return matched, nearby


def _conflicts(conn, user_id: str, session_id: str, workout_id: str | None) -> list[dict]:
    """Saved sessions this one would replace: the same file, or the workout's current sweat data."""
    rows = conn.execute(
        "SELECT * FROM sweat_sessions WHERE user_id = ? AND (id = ? OR workout_id = ?)",
        (user_id, session_id, workout_id),
    ).fetchall()
    return [dict(r) for r in rows]


REFUSED = ("keeps_more_precise", "keeps_sweat_data")


def _existing(new: dict, conflicts: list[dict]) -> str:
    """
    What saving does to what's saved. Real sweat data always beats a breathing-only Nix file, whatever the
    precision. Otherwise the more precise numbers win (Metric Nix, then Customary Nix, then typed in).
    """
    if not conflicts:
        return "none"
    new_sweat = bool(new["sweat_detected"])
    if not new_sweat and any(c["sweat_detected"] for c in conflicts):
        return "keeps_sweat_data"
    if new_sweat and not any(c["sweat_detected"] for c in conflicts):
        return "replaces"
    if new_sweat:
        # Breathing-only copies lose to sweat data anyway, so only sweat data takes part in the precision race.
        conflicts = [c for c in conflicts if c["sweat_detected"]]
    best = max(C3.UNIT_PRECISION[c["unit_system"]] for c in conflicts)
    if best > C3.UNIT_PRECISION[new["unit_system"]]:
        return "keeps_more_precise"
    if best < C3.UNIT_PRECISION[new["unit_system"]]:
        return "replaces_less_precise"
    old = conflicts[0]
    if len(conflicts) == 1 and old["id"] == new["id"] and old["workout_id"] == new["workout_id"]:
        if all(old[k] == new[k] for k in NUMBERS):
            return "same"
    return "replaces"


def _refuse(existing: str) -> None:
    if existing == "keeps_more_precise":
        raise HTTPException(409, ERR_MORE_PRECISE)
    if existing == "keeps_sweat_data":
        raise HTTPException(409, ERR_KEEPS_SWEAT)


def _store(conn, user_id: str, new: dict, minutes: list[tuple]) -> dict:
    """Saves the session and returns what's saved now (the earlier row untouched when it's the same file)."""
    # Take the write lock before looking at what's saved. Otherwise two saves at once (a double tap) both
    # see nothing saved, and the second one breaks the one-per-workout rule.
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
    conflicts = _conflicts(conn, user_id, new["id"], new["workout_id"])
    existing = _existing(new, conflicts)
    _refuse(existing)
    if existing == "same":
        return conflicts[0]
    for old in conflicts:
        conn.execute("DELETE FROM sweat_sessions WHERE user_id = ? AND id = ?", (user_id, old["id"]))
        conn.execute("DELETE FROM sweat_minutes WHERE user_id = ? AND session_id = ?", (user_id, old["id"]))
    row = {**new, "warnings": json.dumps(new["warnings"]), "sweat_detected": int(new["sweat_detected"])}
    cols = ["user_id", *row]
    conn.execute(
        f"INSERT INTO sweat_sessions ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
        (user_id, *row.values()),
    )
    # A file with the same minute twice keeps the later row instead of failing.
    conn.executemany(
        "INSERT OR REPLACE INTO sweat_minutes VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(user_id, new["id"], *m) for m in minutes],
    )
    return new


# ---------------------------------------------------------------- replies


def _weight(conn, user_id: str) -> float | None:
    row = conn.execute("SELECT weight_kg FROM users WHERE user_id = ?", (user_id,)).fetchone()
    return row["weight_kg"] if row else None


def _out(s: dict, weight_kg: float | None) -> dict:
    detected = bool(s["sweat_detected"])
    warnings = json.loads(s["warnings"]) if isinstance(s["warnings"], str) else s["warnings"]
    pct = round(s["fluid_loss_ml"] / (weight_kg * 1000) * 100, 3) if detected and weight_kg else None
    return {
        **{k: s[k] for k in ("id", "workout_id", "source", "start_ms", "end_ms", "start_tz_min", "end_tz_min")},
        "start_local": local_time(s["start_ms"], s["start_tz_min"]).isoformat(timespec="minutes"),
        "end_local": local_time(s["end_ms"], s["end_tz_min"]).isoformat(timespec="minutes"),
        "duration_min": s["duration_min"],
        **{k: s[k] for k in NUMBERS},
        "workout_type": s["workout_type"],
        "sweat_detected": detected,
        "unit_system": s["unit_system"],
        "warnings": warnings,
        "imported_at_ms": s["imported_at_ms"],
        "fluid_loss_pct_body_weight": pct,
        "rehydrate_ml": round(s["fluid_loss_ml"] * REHYDRATE_FACTOR) if detected else None,
    }


def _check_offset(phone_offset: int | None) -> None:
    if phone_offset is not None and not db.valid_offset(phone_offset):
        raise HTTPException(400, ERR_BAD_OFFSET)


# ---------------------------------------------------------------- what the routes call


def preview_nix(
    user_id: str, data: bytes, phone_offset: int | None, workout_id: str | None = None, new_workout: bool = False
) -> dict:
    """
    What saving this file would do. Nothing is stored, the app sends the file again to save it.
    Without a target it's worked out for the workout the file matches. With workout_id (or new_workout)
    it's for that one, so the app can check again whenever the person picks a different workout.
    """
    _check_offset(phone_offset)
    with db.connect() as conn:
        require_user(conn, user_id)
        nix = _parse(data)
        new, _minutes = _from_nix(conn, user_id, nix, phone_offset)
        matched, nearby = _match(conn, user_id, new["start_ms"], new["end_ms"])
        if workout_id is not None:
            _workout(conn, user_id, workout_id)
            target: str | None = workout_id
        elif new_workout:
            target = f"nix-{new['start_ms']}"
        else:
            target = matched["id"] if matched else None
        new["workout_id"] = target
        weight = _weight(conn, user_id)
        conflicts = _conflicts(conn, user_id, new["id"], target)
        # The same file saved on another workout: saving here takes it off that one.
        elsewhere = next((c for c in conflicts if c["id"] == new["id"] and c["workout_id"] != target), None)
        moves_from = _workout(conn, user_id, elsewhere["workout_id"]) if elsewhere else None
        existing = _existing(new, conflicts)
    suggestion = nix.file_weight_kg if weight is None else None
    return {
        "session": _out(new, weight),
        "matched_workout": workout_out(matched) if matched else None,
        "nearby_workouts": [workout_out(r) for r in nearby],
        "existing": existing,
        "moves_from_workout": workout_out(moves_from) if moves_from else None,
        "weight_suggestion_kg": suggestion,
    }


def save_nix(user_id: str, data: bytes, phone_offset: int | None, workout_id: str | None, new_workout: bool) -> dict:
    """Saves the file to the workout picked, else a new workout if asked for, else the one it overlaps."""
    _check_offset(phone_offset)
    make_workout = False
    with db.connect() as conn:
        require_user(conn, user_id)
        new, minutes = _from_nix(conn, user_id, _parse(data), phone_offset)
        if workout_id is not None:
            _workout(conn, user_id, workout_id)
        elif not new_workout:
            matched, _nearby = _match(conn, user_id, new["start_ms"], new["end_ms"])
            if matched is None:
                raise HTTPException(400, ERR_PICK_WORKOUT)
            workout_id = matched["id"]
        else:
            # The id comes from the start time, so saving the same file as new again can't make a second
            # workout. A workout that already has this id is used as it is, never changed.
            workout_id = f"nix-{new['start_ms']}"
            make_workout = (
                conn.execute("SELECT 1 FROM workouts WHERE user_id = ? AND id = ?", (user_id, workout_id)).fetchone()
                is None
            )
            # Refuse before making the workout, so a 409 doesn't leave an empty one behind.
            new["workout_id"] = workout_id
            _refuse(_existing(new, _conflicts(conn, user_id, new["id"], workout_id)))
    if make_workout:
        save_workout(
            user_id,
            WorkoutIn(
                id=workout_id,
                start_ms=new["start_ms"],
                end_ms=new["end_ms"],
                start_tz_min=new["start_tz_min"],
                end_tz_min=new["end_tz_min"],
                source="manual",
                type=(new["workout_type"] or "Workout")[:40],
            ),
        )
    new["workout_id"] = workout_id
    new["imported_at_ms"] = int(time.time() * 1000)
    with db.connect() as conn:
        return _out(_store(conn, user_id, new, minutes), _weight(conn, user_id))


def save_manual(user_id: str, workout_id: str, fluid_loss_ml: float, sodium_mg, sweat_rate_l_h) -> dict:
    """Numbers typed in from any sweat sensor. They count as sweat data, at the lowest precision."""
    with db.connect() as conn:
        require_user(conn, user_id)
        w = _workout(conn, user_id, workout_id)
        new = {
            "id": f"manual-{workout_id}",
            "workout_id": workout_id,
            "source": "manual",
            "start_ms": w["start_ms"],
            "end_ms": w["end_ms"],
            "start_tz_min": w["start_tz_min"],
            "end_tz_min": w["end_tz_min"],
            "duration_min": round((w["end_ms"] - w["start_ms"]) / 60000, 1),
            **dict.fromkeys(NUMBERS),
            "fluid_loss_ml": _round("fluid_loss_ml", float(fluid_loss_ml)),
            "sodium_mg": _round("sodium_mg", None if sodium_mg is None else float(sodium_mg)),
            "sweat_rate_l_h": _round("sweat_rate_l_h", None if sweat_rate_l_h is None else float(sweat_rate_l_h)),
            "workout_type": w["type"],
            "sweat_detected": True,
            "unit_system": "manual",
            "warnings": [],
            "imported_at_ms": int(time.time() * 1000),
        }
        return _out(_store(conn, user_id, new, []), _weight(conn, user_id))


_SESSIONS_SQL = (
    "SELECT s.*, w.type AS w_type, w.start_ms AS w_start_ms, w.end_ms AS w_end_ms, "
    "w.start_tz_min AS w_start_tz, w.end_tz_min AS w_end_tz FROM sweat_sessions s LEFT JOIN workouts w "
    "ON w.user_id = s.user_id AND w.id = s.workout_id WHERE s.user_id = ?"
)


def _session_row(r) -> dict:
    """A saved session. Typed-in numbers have no times of their own, so they follow their workout if it moves."""
    d = dict(r)
    if d["source"] == "manual" and d["w_start_ms"] is not None:
        d.update(
            start_ms=d["w_start_ms"],
            end_ms=d["w_end_ms"],
            start_tz_min=d["w_start_tz"],
            end_tz_min=d["w_end_tz"],
            duration_min=round((d["w_end_ms"] - d["w_start_ms"]) / 60000, 1),
        )
    return d


def for_workout(user_id: str, workout_id: str) -> dict:
    with db.connect() as conn:
        require_user(conn, user_id)
        _workout(conn, user_id, workout_id)
        row = conn.execute(_SESSIONS_SQL + " AND s.workout_id = ?", (user_id, workout_id)).fetchone()
        if row is None:
            raise HTTPException(404, ERR_NO_SWEAT_DATA)
        return _out(_session_row(row), _weight(conn, user_id))


def _now(conn, user_id: str) -> datetime:
    """The person's own clock, like the workouts list, so a demo person's fixed clock counts too."""
    try:
        return processing.local_now(conn, user_id, processing.utc_now())
    except ValueError:
        # A demo user's fixed clock that can't be read. The real date is close enough.
        return processing.utc_now().replace(tzinfo=None)


def list_sessions(user_id: str, days: int) -> list[dict]:
    with db.connect() as conn:
        require_user(conn, user_id)
        since = _now(conn, user_id) - timedelta(days=days)
        sessions = _sessions(conn, user_id)
        weight = _weight(conn, user_id)
    return [_out(s, weight) for s in sessions if s["start_at"] >= since]


# ---------------------------------------------------------------- Today, Trends and the readiness model


def _sessions(conn, user_id: str) -> list[dict]:
    """Every session with its local start and end times and its workout's type."""
    out = []
    for r in conn.execute(_SESSIONS_SQL, (user_id,)).fetchall():
        d = _session_row(r)
        d["start_at"] = local_time(d["start_ms"], d["start_tz_min"])
        d["end_at"] = local_time(d["end_ms"], d["end_tz_min"])
        out.append(d)
    return sorted(out, key=lambda d: d["start_ms"])


def _morning(night: date, update_time: tuple[int, int]) -> datetime:
    """When the night's row is made: the next day at the person's update time."""
    return datetime.combine(night + timedelta(days=1), clock_time(*update_time))


def _window(sessions: list[dict], night: date, days: int, update_time: tuple[int, int]) -> list[dict]:
    """
    Sessions that ended since the update time `days` mornings before, up to this night's morning. Mornings
    don't overlap, so a workout before the update time counts for one night only (the one it leads into).
    """
    end = _morning(night, update_time)
    start = end - timedelta(days=days)
    return [s for s in sessions if start <= s["end_at"] < end]


def _night_of(end_at: datetime, update_time: tuple[int, int]) -> date:
    """The night whose morning a session ending at this local time counts for."""
    d = end_at.date()
    return d if (end_at.hour, end_at.minute) >= update_time else d - timedelta(days=1)


def _type_text(s: dict) -> str:
    """'Run' reads as 'run' in a sentence, but 'HIIT' keeps its capitals."""
    t = s["w_type"] or s["workout_type"] or "workout"
    return t if t.isupper() else t.lower()


def _amount(ml: float, units: str | None) -> str:
    if units == "imperial":
        return f"{ml / C3.OZ_TO_ML:.0f} oz"
    # Rounded half up, so 250 ml (the threshold) reads 0.3 L rather than 0.2 L.
    return f"{math.floor(ml / 100 + 0.5) / 10:.1f} L"


def hydration_line(user_id: str, night_date: date) -> str | None:
    """
    Today's Hydration line for the morning after this night, or None. Placeholder wording until the team
    decides the advice. Only sessions where Nix picked up sweat (or typed-in numbers) count.
    """
    with db.connect() as conn:
        user = conn.execute("SELECT units, update_time FROM users WHERE user_id = ?", (user_id,)).fetchone()
        if user is None:
            return None
        sessions = _sessions(conn, user_id)
    update = processing.parse_update_time(user["update_time"])
    sweaty = [s for s in _window(sessions, night_date, 1, update) if s["sweat_detected"]]
    total = sum(s["fluid_loss_ml"] for s in sweaty)
    if not sweaty or total < HYDRATION_MIN_ML:
        return None
    what = "workouts" if len(sweaty) > 1 else _type_text(sweaty[0])
    # A workout that started the morning the line is shown, before the update time, isn't "yesterday".
    when = "This morning's" if all(s["start_at"].date() > night_date for s in sweaty) else "Yesterday's"
    return (
        f"{when} {what} cost about {_amount(total, user['units'])} of sweat. "
        "Drink a little more than usual this morning."
    )


def daily(user_id: str, nights: int) -> dict:
    """Sweat per day for the Trends chart, by the day the workout started, ending yesterday."""
    with db.connect() as conn:
        user = require_user(conn, user_id)
        today = _now(conn, user_id).date()
        sessions = _sessions(conn, user_id)
    first = today - timedelta(days=nights)
    days: list[dict[str, Any]] = []
    for i in range(nights):
        d = first + timedelta(days=i)
        that_day = [s for s in sessions if s["start_at"].date() == d]
        sweaty = [s for s in that_day if s["sweat_detected"]]
        sodium = [s["sodium_mg"] for s in sweaty if s["sodium_mg"] is not None]
        days.append(
            {
                "date": d.isoformat(),
                "fluid_loss_ml": round(sum(s["fluid_loss_ml"] for s in sweaty), 1) if sweaty else None,
                "sodium_mg": round(sum(sodium), 1) if sodium else None,
                "sessions": len(that_day),
                "has_sweat_data": bool(sweaty),
            }
        )
    with_data = [d for d in days if d["has_sweat_data"]]
    if with_data:
        top = max(with_data, key=lambda d: d["fluid_loss_ml"])
        when = date.fromisoformat(top["date"]).strftime("%a %d %b").replace(" 0", " ")
        summary = (
            f"Highest on {when} ({_amount(top['fluid_loss_ml'], user['units'])}). "
            "Long or hot sessions push it up, so drink more the next morning."
        )
    else:
        summary = f"No sweat data in the last {nights} days."
    return {"nights": nights, "days": days, "summary": summary, "placeholder": True}


DAILY_COLUMNS = [
    "person_id",
    "night_date",
    "fluid_loss_pct_bw_1d",
    "sodium_mg_1d",
    "fluid_loss_pct_bw_2d",
    "sodium_mg_2d",
    "has_sweat_data",
]


def daily_sweat_table(conn, user_id: str) -> pd.DataFrame:
    """
    One row per night that has sweat sessions in reach, for the readiness model to join on person and night.
    Windows: sessions that ended since the update time 1 or 2 mornings before, up to this night's morning.
    Only sessions where sweat was detected count, and missing stays NaN, never 0.
    Uses today's weight from Settings, since weight has no history yet.
    """
    user = conn.execute("SELECT weight_kg, update_time FROM users WHERE user_id = ?", (user_id,)).fetchone()
    weight = user["weight_kg"] if user else None
    update = processing.parse_update_time(user["update_time"] if user else None)
    sessions = _sessions(conn, user_id)
    nights: set[date] = set()
    for s in sessions:
        n = _night_of(s["end_at"], update)
        nights.update({n, n + timedelta(days=1)})

    def totals(rows: list[dict]) -> tuple[float, float]:
        sweaty = [r for r in rows if r["sweat_detected"]]
        fluid = sum(r["fluid_loss_ml"] for r in sweaty)
        pct = fluid / (weight * 1000) * 100 if sweaty and weight else math.nan
        sodium = [r["sodium_mg"] for r in sweaty if r["sodium_mg"] is not None]
        return pct, (sum(sodium) if sodium else math.nan)

    rows = []
    for night in sorted(nights):
        pct1, na1 = totals(_window(sessions, night, 1, update))
        two = _window(sessions, night, 2, update)
        pct2, na2 = totals(two)
        rows.append(
            {
                "person_id": user_id,
                "night_date": night.isoformat(),
                "fluid_loss_pct_bw_1d": pct1,
                "sodium_mg_1d": na1,
                "fluid_loss_pct_bw_2d": pct2,
                "sodium_mg_2d": na2,
                "has_sweat_data": any(r["sweat_detected"] for r in two),
            }
        )
    return pd.DataFrame(rows, columns=DAILY_COLUMNS)
