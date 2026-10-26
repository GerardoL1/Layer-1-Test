"""
Sweat sessions (Layer 3). A Nix export is read by layer3.nix, its local times get the person's UTC
offset, it's matched to a workout and saved, one sweat session per workout, the more precise data
winning. Also the Hydration line for Today, the daily sweat for the Trends chart, and the per-day
table the readiness model can join. See docs/layer3_spec.md.
"""

import json
import math
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from fastapi import HTTPException

from app.core import db
from app.routers.workouts import _out as workout_out
from app.routers.workouts import save_workout
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

ERR_PICK_WORKOUT = "This file doesn't match any workout. Pick one, or save it as a new workout."
ERR_NO_TIME_ZONE = "We don't know your time zone yet. Set it in Profile, then import the file again."
ERR_MORE_PRECISE = "This workout already has more precise sweat data, so it was kept."
ERR_NO_SWEAT_DATA = "This workout has no sweat data yet."
ERR_BAD_OFFSET = "The phone sent an impossible UTC offset."

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


def _offset(conn, user_id: str, local: datetime, phone_offset: int | None) -> int:
    """Nix times have no time zone. Settings time zone for that date, else the newest reading's, else the phone's."""
    user = conn.execute("SELECT timezone FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user and user["timezone"]:
        try:
            off = local.replace(tzinfo=ZoneInfo(user["timezone"])).utcoffset()
            if off is not None:
                return int(off.total_seconds() // 60)
        except (ZoneInfoNotFoundError, ValueError):
            pass
    latest = conn.execute(
        "SELECT tz FROM (SELECT start_ms, tz_offset_min AS tz FROM samples WHERE user_id = ? "
        "UNION ALL SELECT start_ms, end_tz_min FROM sleep_stages WHERE user_id = ?) "
        "ORDER BY start_ms DESC LIMIT 1",
        (user_id, user_id),
    ).fetchone()
    if latest:
        return int(latest["tz"])
    if phone_offset is not None:
        return phone_offset
    raise HTTPException(400, ERR_NO_TIME_ZONE)


def _utc_ms(local: datetime, offset_min: int) -> int:
    return (local - timedelta(minutes=offset_min) - datetime(1970, 1, 1)) // timedelta(milliseconds=1)


def _from_nix(conn, user_id: str, s: NixSession, phone_offset: int | None) -> tuple[dict, list[tuple]]:
    start_tz = _offset(conn, user_id, s.start_local, phone_offset)
    end_tz = _offset(conn, user_id, s.end_local, phone_offset)
    start_ms, end_ms = _utc_ms(s.start_local, start_tz), _utc_ms(s.end_local, end_tz)
    require_time(start_ms, start_tz, "The Nix workout start")
    require_time(end_ms, end_tz, "The Nix workout end")
    if end_ms - start_ms > MAX_SESSION_HOURS * HOUR_MS:
        raise HTTPException(400, f"A workout can't be longer than {MAX_SESSION_HOURS} hours.")
    session = {
        "id": f"nix-{start_ms}-{end_ms}",
        "workout_id": None,
        "source": "nix",
        "start_ms": start_ms,
        "end_ms": end_ms,
        "start_tz_min": start_tz,
        "end_tz_min": end_tz,
        "duration_min": round(s.duration_min, 1),
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
        "warnings": list(s.warnings),
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


def _precision(unit_system: str) -> int:
    return C3.UNIT_PRECISION[unit_system]


def _existing(new: dict, conflicts: list[dict]) -> str:
    if not conflicts:
        return "none"
    best = max(_precision(c["unit_system"]) for c in conflicts)
    if best > _precision(new["unit_system"]):
        return "keeps_more_precise"
    if best < _precision(new["unit_system"]):
        return "replaces_less_precise"
    old = conflicts[0]
    if len(conflicts) == 1 and old["id"] == new["id"] and old["workout_id"] == new["workout_id"]:
        if all(old[k] == new[k] for k in NUMBERS):
            return "same"
    return "replaces"


def _store(conn, user_id: str, new: dict, minutes: list[tuple]) -> None:
    conflicts = _conflicts(conn, user_id, new["id"], new["workout_id"])
    if _existing(new, conflicts) == "keeps_more_precise":
        raise HTTPException(409, ERR_MORE_PRECISE)
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
    }


def _check_offset(phone_offset: int | None) -> None:
    if phone_offset is not None and not db.valid_offset(phone_offset):
        raise HTTPException(400, ERR_BAD_OFFSET)


# ---------------------------------------------------------------- what the routes call


def preview_nix(user_id: str, data: bytes, phone_offset: int | None) -> dict:
    """What saving this file would do. Nothing is stored, the app sends the file again to save it."""
    _check_offset(phone_offset)
    with db.connect() as conn:
        require_user(conn, user_id)
        nix = _parse(data)
        new, _minutes = _from_nix(conn, user_id, nix, phone_offset)
        matched, nearby = _match(conn, user_id, new["start_ms"], new["end_ms"])
        new["workout_id"] = matched["id"] if matched else None
        weight = _weight(conn, user_id)
        existing = _existing(new, _conflicts(conn, user_id, new["id"], new["workout_id"]))
    suggestion = nix.file_weight_kg if weight is None else None
    return {
        "session": _out(new, weight),
        "matched_workout": workout_out(matched) if matched else None,
        "nearby_workouts": [workout_out(r) for r in nearby],
        "existing": existing,
        "weight_suggestion_kg": suggestion,
    }


def save_nix(user_id: str, data: bytes, phone_offset: int | None, workout_id: str | None, new_workout: bool) -> dict:
    """Saves the file to the workout picked, else a new workout if asked for, else the one it overlaps."""
    _check_offset(phone_offset)
    nix = _parse(data)
    with db.connect() as conn:
        require_user(conn, user_id)
        new, minutes = _from_nix(conn, user_id, nix, phone_offset)
        if workout_id is not None:
            _workout(conn, user_id, workout_id)
        elif not new_workout:
            matched, _nearby = _match(conn, user_id, new["start_ms"], new["end_ms"])
            if matched is None:
                raise HTTPException(400, ERR_PICK_WORKOUT)
            workout_id = matched["id"]
    if workout_id is None:
        # The id comes from the start time, so saving the same file as new again can't make a second workout.
        workout_id = f"nix-{new['start_ms']}"
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
        _store(conn, user_id, new, minutes)
        return _out(new, _weight(conn, user_id))


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
        _store(conn, user_id, new, [])
        return _out(new, _weight(conn, user_id))


def for_workout(user_id: str, workout_id: str) -> dict:
    with db.connect() as conn:
        require_user(conn, user_id)
        _workout(conn, user_id, workout_id)
        row = conn.execute(
            "SELECT * FROM sweat_sessions WHERE user_id = ? AND workout_id = ?", (user_id, workout_id)
        ).fetchone()
        if row is None:
            raise HTTPException(404, ERR_NO_SWEAT_DATA)
        return _out(dict(row), _weight(conn, user_id))


def list_sessions(user_id: str, days: int) -> list[dict]:
    since = int(time.time() * 1000) - days * 24 * HOUR_MS
    with db.connect() as conn:
        require_user(conn, user_id)
        rows = conn.execute(
            "SELECT * FROM sweat_sessions WHERE user_id = ? AND start_ms >= ? ORDER BY start_ms", (user_id, since)
        ).fetchall()
        weight = _weight(conn, user_id)
    return [_out(dict(r), weight) for r in rows]


# ---------------------------------------------------------------- Today, Trends and the readiness model


def _sessions(conn, user_id: str) -> list[dict]:
    """Every session with its local end time and its workout's type."""
    rows = conn.execute(
        "SELECT s.*, w.type AS w_type FROM sweat_sessions s LEFT JOIN workouts w "
        "ON w.user_id = s.user_id AND w.id = s.workout_id WHERE s.user_id = ? ORDER BY s.start_ms",
        (user_id,),
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["start_at"] = local_time(r["start_ms"], r["start_tz_min"])
        d["end_at"] = local_time(r["end_ms"], r["end_tz_min"])
        out.append(d)
    return out


def _window(sessions: list[dict], night: date, days: int, update_time: tuple[int, int]) -> list[dict]:
    """Sessions that ended in the last `days` days up to the night, or the next morning before the update time."""
    start = datetime.combine(night - timedelta(days=days - 1), datetime.min.time())
    end = datetime.combine(night + timedelta(days=1), datetime.min.time()).replace(
        hour=update_time[0], minute=update_time[1]
    )
    return [s for s in sessions if start <= s["end_at"] < end]


def _amount(ml: float, units: str | None) -> str:
    if units == "imperial":
        return f"{ml / C3.OZ_TO_ML:.0f} oz"
    return f"{ml / 1000:.1f} L"


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
    what = "workouts" if len(sweaty) > 1 else (sweaty[0]["w_type"] or sweaty[0]["workout_type"] or "workout").lower()
    return (
        f"Yesterday's {what} cost about {_amount(total, user['units'])} of sweat. "
        "Drink a little more than usual this morning."
    )


def daily(user_id: str, nights: int) -> dict:
    """Sweat per day for the Trends chart, by the day the workout started, ending yesterday."""
    with db.connect() as conn:
        user = require_user(conn, user_id)
        today = processing.local_now(conn, user_id, processing.utc_now()).date()
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
    Windows: the last 1 or 2 days up to the night, plus the next morning before the update time.
    Only sessions where sweat was detected count, and missing stays NaN, never 0.
    Uses today's weight from Settings, since weight has no history yet.
    """
    user = conn.execute("SELECT weight_kg, update_time FROM users WHERE user_id = ?", (user_id,)).fetchone()
    weight = user["weight_kg"] if user else None
    update = processing.parse_update_time(user["update_time"] if user else None)
    sessions = _sessions(conn, user_id)
    nights: set[date] = set()
    for s in sessions:
        d = s["end_at"].date()
        nights.update({d, d + timedelta(days=1)})
        if (s["end_at"].hour, s["end_at"].minute) < update:
            nights.add(d - timedelta(days=1))

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
