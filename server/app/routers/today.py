"""
Today: last night's readiness, metric rows and sleep. Brings results up to date first,
which only does work when new data arrived or a new night became ready.
"""

from datetime import date, timedelta

from fastapi import APIRouter

from app.core import db
from app.core.json_values import clean, r1
from app.core.urls import USER
from app.readiness import explain
from app.readiness.scoring import LOW_BELOW, READINESS_METHOD, READY_FROM, readiness
from app.readiness.usual import metric_rows
from app.schemas.today import Today
from app.services import processing
from app.services.update_schedule import can_update_now, next_update
from app.services.users import last_run, night_rows, require_user
from layer1 import config as C

router = APIRouter(prefix=USER, tags=["today"])


def sleep_block(row) -> dict:
    return {
        "onset": clean(row.get("sleep_onset")),
        "wake": clean(row.get("final_wake")),
        "total_min": r1(row.get("tst_min")),
        "deep_min": r1(row.get("deep_min")),
        "core_min": r1(row.get("core_min")),
        "rem_min": r1(row.get("rem_min")),
        "unspecified_min": r1(row.get("unspecified_min")),
        "awake_min": r1(row.get("waso_min")),
        "in_bed_min": r1(row.get("tib_min")),
        "efficiency_pct": r1(row.get("sleep_efficiency_pct")),
    }


@router.get("/today", response_model=Today, response_model_exclude_unset=True)
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

    last_night = now.date() - timedelta(days=1)  # the night that started yesterday evening
    base = {
        "user_id": user_id,
        "now_local": now.isoformat(timespec="minutes"),
        "update_time": f"{update_time[0]:02d}:{update_time[1]:02d}",
        "next_update": next_update(now, update_time).isoformat(timespec="minutes"),
        "updated_at": run["sync_local"] if run else None,
        "can_update_now": update_now_ok,
        "readiness_method": READINESS_METHOD,
        "cutoffs": {"low_below": LOW_BELOW, "ready_from": READY_FROM, "placeholder": True},
    }
    if nights.empty:
        return {
            **base,
            "night_date": None,
            "is_last_night": False,
            "message": "No nights processed yet.",
            "readiness": None,
            "metrics": [],
            "sleep": None,
            "quality_notes": None,
        }

    row = nights.iloc[-1].to_dict()
    shown = row["night_date"]
    message = None
    if shown < last_night:
        message = f"Last night updates at {base['update_time']}" + (", or tap Update now." if update_now_ok else ".")
    ready = readiness(row)
    metrics = metric_rows(row)
    verdict, reason = explain.today_text(
        ready["status"], metrics, clean(row.get("tst_min_base_n")), C.BASELINE_MIN_NIGHTS, clean(row.get("tst_min"))
    )
    return {
        **base,
        "night_date": shown.isoformat(),
        "is_last_night": shown == last_night,
        "message": message,
        "readiness": ready,
        "metrics": metrics,
        "sleep": sleep_block(row),
        "quality_notes": row.get("quality_notes") or None,
        "verdict": verdict,
        "reason": reason,
        "text_placeholder": True,
    }
