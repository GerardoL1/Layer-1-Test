"""
Read and settings endpoints for the app (Today, Trends, Profile, Setup).

Every read first brings the user's results up to date, which only does work
when new data arrived or a new night became ready.

Two things here are PLACEHOLDERS until the team decides them:
  - the readiness score (equal-weight average of the z-scores) and its 40 / 70 cut-offs
  - the "usual range" (baseline mean plus or minus 1 SD) and the Worse / Usual / Better label
Both are marked "placeholder": true in every response.
"""
import json
import math
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

import db
import processing
from processing import C, I, P

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------- placeholders (not decided yet)

# +1 means a higher value is better, -1 means higher is worse.
READINESS_SIGNS = {"z_hrv": 1, "z_rhr": -1, "z_tst": 1, "z_eff": 1, "z_frag": -1}
READINESS_CENTER, READINESS_POINTS_PER_SD = 50, 10
LOW_BELOW, READY_FROM = 40, 70
USUAL_RANGE_SD = 1.0

READINESS_METHOD = ("Placeholder: 50 + 10 x the average of the available z-scores "
                    "(HRV, sleep time and efficiency count up, resting HR and fragmentation count down), "
                    "clipped to 0-100. Weights and cut-offs are not decided yet.")

# The metric rows shown on Today and Profile, in order.
METRICS = [
    # key, column, label, unit, z column, higher is better?
    ("hrv", "hrv_night_ms", "Heart rate variability", "ms", "z_hrv", True),
    ("rhr", "rhr_night_bpm", "Resting heart rate", "bpm", "z_rhr", False),
    ("sleep", "tst_min", "Total sleep", "min", "z_tst", True),
    ("efficiency", "sleep_efficiency_pct", "Sleep efficiency", "%", "z_eff", True),
    ("fragmentation", "fragmentation_per_hr", "Awakenings per hour", "/h", "z_frag", False),
]
# Baselines are kept on these columns. HRV's is on the log scale.
BASE_COLUMN = {"hrv_night_ms": "hrv_ln"}


# ---------------------------------------------------------------- helpers

def clean(v):
    """JSON can't hold NaN, so missing numbers become null."""
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):   # numpy numbers
        return clean(v.item())
    return v


def r1(v):
    v = clean(v)
    return round(v, 1) if isinstance(v, float) else v


def readiness(row) -> dict:
    zs = [sign * row[z] for z, sign in READINESS_SIGNS.items() if pd.notna(row.get(z))]
    if not zs:
        score, status = None, ("building_baseline" if row.get("usable_sleep") else "no_data")
    else:
        score = int(round(min(100, max(0, READINESS_CENTER + READINESS_POINTS_PER_SD * sum(zs) / len(zs)))))
        status = "low" if score < LOW_BELOW else "moderate" if score < READY_FROM else "ready"
    return {"score": score, "status": status, "z_count": len(zs), "placeholder": True}


def usual_range(row, col) -> tuple:
    base = BASE_COLUMN.get(col, col)
    mu, sd = row.get(f"{base}_base_mean"), row.get(f"{base}_base_sd")
    if pd.isna(mu) or pd.isna(sd):
        return None, None
    lo, hi = mu - USUAL_RANGE_SD * sd, mu + USUAL_RANGE_SD * sd
    if base != col:   # back from the log scale
        lo, hi = math.exp(lo), math.exp(hi)
    return r1(lo), r1(hi)


def direction(z, higher_is_better) -> str | None:
    if pd.isna(z):
        return None
    good = z if higher_is_better else -z
    return "better" if good > USUAL_RANGE_SD else "worse" if good < -USUAL_RANGE_SD else "usual"


def metric_rows(row) -> list:
    out = []
    for key, col, label, unit, zcol, up in METRICS:
        lo, hi = usual_range(row, col)
        out.append({"key": key, "label": label, "unit": unit, "value": r1(row.get(col)),
                    "z": r1(row.get(zcol)), "usual_low": lo, "usual_high": hi,
                    "direction": direction(row.get(zcol), up), "placeholder": True})
    return out


def sleep_block(row) -> dict:
    return {"onset": clean(row.get("sleep_onset")), "wake": clean(row.get("final_wake")),
            "total_min": r1(row.get("tst_min")), "deep_min": r1(row.get("deep_min")),
            "core_min": r1(row.get("core_min")), "rem_min": r1(row.get("rem_min")),
            "unspecified_min": r1(row.get("unspecified_min")), "awake_min": r1(row.get("waso_min")),
            "in_bed_min": r1(row.get("tib_min")), "efficiency_pct": r1(row.get("sleep_efficiency_pct"))}


def night_rows(user_id: str) -> pd.DataFrame:
    with db.connect() as conn:
        return processing.load_nights(conn, user_id)


def require_user(conn, user_id: str):
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if user is None:
        raise HTTPException(404, f"No data for '{user_id}' yet. Sync from the iPhone or import a Health export.")
    return user


def last_run(conn, user_id: str):
    return conn.execute("SELECT * FROM runs WHERE user_id = ? ORDER BY run DESC LIMIT 1", (user_id,)).fetchone()


def next_update(now: datetime, update_time: tuple) -> datetime:
    at = datetime.combine(now.date(), time(*update_time))
    return at if at > now else at + timedelta(days=1)


def can_update_now(conn, user_id: str, now: datetime, update_time: tuple, ready_through) -> bool:
    """True when "Update now" would process a night that isn't processed yet."""
    since = int((now - timedelta(days=3)).timestamp() * 1000)   # rough, local vs UTC doesn't matter here
    recent = db.load_records(conn, user_id, since_ms=since, sleep_only=True)
    if recent.empty:
        return False
    stages = P.clean(recent)[0]["sleep_stages"]   # same cleaning as processing (watch only, no In Bed)
    if stages.empty:
        return False
    newest = I.latest_ready_night(now, stages, update_time, update_now=True)
    return ready_through is None or newest > ready_through


# ---------------------------------------------------------------- Today

@router.get("/today")
def today(user_id: str):
    processing.ensure_processed(user_id)
    with db.connect() as conn:
        user = require_user(conn, user_id)
        now = processing.local_now(conn, user_id, processing.utc_now())
        update_time = processing.parse_update_time(user["update_time"])
        run = last_run(conn, user_id)
        ready_through = date.fromisoformat(run["ready_through"]) if run and run["ready_through"] else None
        update_now_ok = can_update_now(conn, user_id, now, update_time, ready_through)
    nights = night_rows(user_id)

    last_night = now.date() - timedelta(days=1)   # the night that started yesterday evening
    base = {"user_id": user_id, "now_local": now.isoformat(timespec="minutes"),
            "update_time": f"{update_time[0]:02d}:{update_time[1]:02d}",
            "next_update": next_update(now, update_time).isoformat(timespec="minutes"),
            "updated_at": run["sync_local"] if run else None, "can_update_now": update_now_ok,
            "readiness_method": READINESS_METHOD,
            "cutoffs": {"low_below": LOW_BELOW, "ready_from": READY_FROM, "placeholder": True}}
    if nights.empty:
        return {**base, "night_date": None, "is_last_night": False, "message": "No nights processed yet.",
                "readiness": None, "metrics": [], "sleep": None, "quality_notes": None}

    row = nights.iloc[-1].to_dict()
    shown = row["night_date"]
    message = None
    if shown < last_night:
        message = (f"Last night updates at {base['update_time']}"
                   + (", or tap Update now." if update_now_ok else "."))
    return {**base, "night_date": shown.isoformat(), "is_last_night": shown == last_night, "message": message,
            "readiness": readiness(row), "metrics": metric_rows(row), "sleep": sleep_block(row),
            "quality_notes": row.get("quality_notes") or None}


# ---------------------------------------------------------------- Trends

TREND_RANGES = (14, 28, 90)

@router.get("/trends")
def trends(user_id: str, nights: int = 14):
    if nights not in TREND_RANGES:
        raise HTTPException(422, f"nights must be one of {', '.join(map(str, TREND_RANGES))}")
    processing.ensure_processed(user_id)
    with db.connect() as conn:
        require_user(conn, user_id)
    table = night_rows(user_id)
    if table.empty:
        return {"user_id": user_id, "nights": nights, "rows": []}
    last = table["night_date"].iloc[-1]
    table = table[table["night_date"] > last - timedelta(days=nights)]
    rows = []
    for row in table.to_dict(orient="records"):
        entry = {"night_date": row["night_date"].isoformat(), "readiness": readiness(row),
                 "usable_sleep": bool(row["usable_sleep"]), "quality_notes": row.get("quality_notes") or None,
                 "deep_min": r1(row.get("deep_min")), "core_min": r1(row.get("core_min")),
                 "rem_min": r1(row.get("rem_min")), "unspecified_min": r1(row.get("unspecified_min"))}
        for key, col, _label, _unit, zcol, _up in METRICS:
            lo, hi = usual_range(row, col)
            entry[key] = {"value": r1(row.get(col)), "z": r1(row.get(zcol)), "usual_low": lo, "usual_high": hi}
        rows.append(entry)
    return {"user_id": user_id, "nights": nights, "cutoffs": {"low_below": LOW_BELOW, "ready_from": READY_FROM},
            "placeholder": True, "rows": rows}


# ---------------------------------------------------------------- Profile

@router.get("/profile")
def profile(user_id: str):
    processing.ensure_processed(user_id)
    with db.connect() as conn:
        require_user(conn, user_id)
        sources = [r[0] for r in conn.execute(
            "SELECT DISTINCT source FROM samples WHERE user_id = ? AND source IS NOT NULL "
            "UNION SELECT DISTINCT source FROM sleep_stages WHERE user_id = ? AND source IS NOT NULL",
            (user_id, user_id))]
    table = night_rows(user_id)
    usual = []
    if not table.empty:
        latest = table.iloc[-1].to_dict()
        for key, col, label, unit, _z, _up in METRICS:
            lo, hi = usual_range(latest, col)
            base = BASE_COLUMN.get(col, col)
            usual.append({"key": key, "label": label, "unit": unit, "usual_low": lo, "usual_high": hi,
                          "baseline_nights": clean(latest.get(f"{base}_base_n")), "placeholder": True})
    return {
        "user_id": user_id,
        "settings": get_settings(user_id),
        "nights_total": int(len(table)),
        "nights_usable": int(table["usable_sleep"].sum()) if len(table) else 0,
        "first_night": table["night_date"].iloc[0].isoformat() if len(table) else None,
        "last_night": table["night_date"].iloc[-1].isoformat() if len(table) else None,
        "baseline_window_nights": C.BASELINE_WINDOW_NIGHTS,
        "baseline_min_nights": C.BASELINE_MIN_NIGHTS,
        "usual_ranges": usual,
        "sources": sorted(sources),
    }


# ---------------------------------------------------------------- Settings

class Settings(BaseModel):
    timezone: str | None = None
    update_time: str | None = None
    age: int | None = None
    training: str | None = None
    training_days: list[int] | None = None
    units: Literal["metric", "imperial"] | None = None

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v):
        if v is not None:
            try:
                ZoneInfo(v)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError(f"unknown time zone '{v}', use a name like America/Chicago")
        return v

    @field_validator("update_time")
    @classmethod
    def clock_time(cls, v):
        if v is not None:
            try:
                h, m = (int(x) for x in v.split(":"))
                assert 0 <= h < 24 and 0 <= m < 60
            except (ValueError, AssertionError):
                raise ValueError("use HH:MM, for example 08:00")
            v = f"{h:02d}:{m:02d}"
        return v

    @field_validator("age")
    @classmethod
    def sensible_age(cls, v):
        if v is not None and not 13 <= v <= 100:
            raise ValueError("age must be between 13 and 100")
        return v

    @field_validator("training")
    @classmethod
    def short_text(cls, v):
        if v is not None and len(v) > 100:
            raise ValueError("keep training under 100 characters")
        return v

    @field_validator("training_days")
    @classmethod
    def weekdays(cls, v):
        if v is not None:
            if any(d not in range(7) for d in v):
                raise ValueError("training days are weekday numbers, 0 = Monday to 6 = Sunday")
            v = sorted(set(v))
        return v


@router.get("/settings")
def get_settings(user_id: str):
    with db.connect() as conn:
        user = require_user(conn, user_id)
    return {"timezone": user["timezone"], "update_time": user["update_time"], "age": user["age"],
            "training": user["training"],
            "training_days": json.loads(user["training_days"]) if user["training_days"] else [],
            "units": user["units"] or "metric"}


@router.put("/settings")
def put_settings(user_id: str, settings: Settings):
    """Changes only the fields that were sent. A new user is created by their first settings or data."""
    changes = settings.model_dump(exclude_unset=True)
    if "training_days" in changes and changes["training_days"] is not None:
        changes["training_days"] = json.dumps(changes["training_days"])
    if changes.get("update_time", "") is None:
        changes["update_time"] = "%02d:%02d" % C.DEFAULT_UPDATE_TIME
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        for col, value in changes.items():   # column names come from the Settings model, not the request
            conn.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (value, user_id))
    return get_settings(user_id)


# ---------------------------------------------------------------- Update now

@router.post("/update-now")
def update_now(user_id: str):
    with db.connect() as conn:
        require_user(conn, user_id)
    report = processing.process_user(user_id, update_now=True)
    if report is None or not report.new_nights:
        return {"processed": False, "new_nights": [],
                "message": "Nothing new to process. Last night's sleep hasn't ended or hasn't synced yet."}
    return {"processed": True, "new_nights": [d.isoformat() for d in report.new_nights],
            "message": "Updated."}


# ---------------------------------------------------------------- Demo mode (temporary, remove later)

DEMO_PEOPLE = {"sam": "mock_export_sam_steady.zip", "alex": "mock_export_alex_overreach.zip",
               "jordan": "mock_export_jordan_messy.zip"}
# The mock people last sleep on the night of 30 Sep 2026 (they wake on 1 Oct), so the demo
# clock sits just after that night's update time.
DEMO_CLOCK = "2026-10-01T08:30:00"


@router.post("/demo/{person}")
def load_demo(person: Literal["sam", "alex", "jordan"]):
    """Load a mock person as demo-<name> with a fixed clock. Reloading starts them fresh."""
    from apple_export import import_export
    from pathlib import Path

    user_id = f"demo-{person}"
    path = Path(processing.__file__).resolve().parent.parent / "preprocessing" / "sample_data" / DEMO_PEOPLE[person]
    with db.connect() as conn:
        for table in ("samples", "sleep_stages", "nights", "runs", "users"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user_id, DEMO_CLOCK))
        import_export(path, conn, user_id)
    processing.process_user(user_id, force=True)
    return {"user_id": user_id, "clock_local": DEMO_CLOCK}
