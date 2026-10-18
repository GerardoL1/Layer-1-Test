"""
Three of the four ways readings arrive (the fourth, the export file, is in imports.py).
All under /api/v1/users/{user_id}/readings:
  1. Our iPhone app                  POST .../readings
  2. Health Auto Export iPhone app   POST .../readings/health-auto-export  (no Mac needed, paid app feature)
  3. Apple Shortcuts automation      POST .../readings/shortcuts           (no Mac needed, free)
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core import db
from app.core.urls import USER
from app.routers.large_form import LargeFormRoute
from app.schemas.readings import HealthAutoExportResult, ReadingsBatch, ReadingsResult
from app.services import health_auto_export, shortcuts
from app.services.readings import save_readings
from layer1.units import factor

log = logging.getLogger("recovery.ingest")

router = APIRouter(prefix=USER + "/readings", tags=["readings"])


# ---------------------------------------------------------------- 1. our iPhone app


def require_offset(minutes, what: str) -> int:
    # Without the offset we can't tell which night a reading belongs to, so refuse it.
    if minutes is None:
        raise HTTPException(
            400,
            f"{what} is missing its UTC offset (tz_offset_min). "
            "Update the app so it sends the time zone with every reading.",
        )
    if not db.valid_offset(minutes):
        raise HTTPException(400, f"{what} has an impossible UTC offset: {minutes} minutes.")
    return minutes


@router.post("", response_model=ReadingsResult)
def add_readings(user_id: str, payload: ReadingsBatch, background: BackgroundTasks):
    if payload.user_id is not None and payload.user_id != user_id:
        raise HTTPException(400, f"The body is for '{payload.user_id}' but the URL is for '{user_id}'.")
    samples: list[tuple] = []
    stages: list[tuple] = []
    for q in payload.samples:
        if q.metric not in db.METRICS:
            raise HTTPException(400, f"Unknown metric '{q.metric}'. Use one of: {', '.join(db.METRICS)}")
        tz = require_offset(q.tz_offset_min, f"{q.metric} sample {q.uuid}")
        scale = factor(q.metric, q.unit)
        if scale is None:
            raise HTTPException(400, f"{q.metric} sample {q.uuid} is in '{q.unit}', a unit we can't convert.")
        samples.append((q.uuid, q.metric, q.value * scale, q.start_ms, q.end_ms, tz, q.source))
    for st in payload.sleep:
        if st.stage not in db.STAGES:
            raise HTTPException(400, f"Unknown sleep stage '{st.stage}'. Use one of: {', '.join(db.STAGES)}")
        start_tz = require_offset(st.start_tz_min, f"sleep stage {st.uuid}")
        end_tz = require_offset(st.end_tz_min, f"sleep stage {st.uuid}")
        stages.append((st.uuid, st.stage, st.start_ms, st.end_ms, start_tz, end_tz, st.source))

    added = save_readings(background, user_id, samples, stages)
    received = len(samples) + len(stages)
    log.info("upload %s: received %d, new %d", user_id, received, added)
    return {"received": received, "new": added}


# ---------------------------------------------------------------- 2. Health Auto Export


@router.post("/health-auto-export", response_model=HealthAutoExportResult)
async def add_health_auto_export(user_id: str, request: Request, background: BackgroundTasks):
    """
    Receiver for the Health Auto Export app (REST API automation, JSON format).
    Set the URL in the app to:
      http://<computer-ip>:8000/api/v1/users/<tester name>/readings/health-auto-export
    Its dates carry the UTC offset, e.g. '2026-09-30 23:14:05 -0700'.
    """
    try:
        parsed = health_auto_export.parse_payload(await request.json(), user_id)
    except health_auto_export.BadPayload as e:
        raise HTTPException(400, str(e)) from None
    except (ValueError, RecursionError):  # not JSON at all, an empty body, or nested too deep to read
        raise HTTPException(400, "The body isn't JSON. Set Health Auto Export's format to JSON.") from None
    added = save_readings(background, user_id, parsed.samples, parsed.stages)
    log.info(
        "health-auto-export %s: %d samples, %d sleep stages, %d new, %d unreadable dates, ignored: %s",
        user_id,
        len(parsed.samples),
        len(parsed.stages),
        added,
        parsed.bad,
        ", ".join(sorted(parsed.ignored)) or "none",
    )
    notes = []
    if parsed.aggregated_sleep:
        notes.append(
            f"{parsed.aggregated_sleep} nights of sleep arrived as nightly summaries, which have no sleep "
            "stages, so they weren't saved. In Health Auto Export, turn off 'Aggregate sleep data' and send again."
        )
        log.warning("health-auto-export %s: %d aggregated sleep rows refused", user_id, parsed.aggregated_sleep)
    if parsed.unknown_units:
        notes.append(
            f"Not saved, in a unit we can't convert: {', '.join(sorted(parsed.unknown_units))}. "
            "Set Health Auto Export to send heart rate in count/min and HRV in ms."
        )
    return {
        "samples": len(parsed.samples),
        "sleep_stages": len(parsed.stages),
        "new": added,
        "unreadable": parsed.bad,
        "ignored_metrics": sorted(parsed.ignored),
        "notes": notes,
    }


# ---------------------------------------------------------------- 3. Apple Shortcuts


def add_shortcut_rows(user_id: str, background: BackgroundTasks, metric: str = Form(...), rows: str = Form("")):
    """
    Receiver for the Apple Shortcuts automation. Form fields:
      metric  heart_rate | resting_heart_rate | hrv_sdnn | sleep
      rows    one line per Health sample:  start | end | value | source
    Replies in plain text so the shortcut can show the result.
    """
    metric = metric.strip()
    if metric not in shortcuts.SHORTCUT_METRICS:
        raise HTTPException(400, f"Unknown metric '{metric}'. Use one of: {', '.join(shortcuts.SHORTCUT_METRICS)}")
    samples, stages, bad = shortcuts.parse_rows(user_id, metric, rows)
    if metric == "sleep" and bad:
        # Saving the lines that did read would leave part of a night (in another language, often
        # only REM matches), which looks like a short night. Better to save none and say why.
        log.warning("shortcut %s: sleep refused, first unreadable line: %s", user_id, bad[0][:200])
        raise HTTPException(
            400,
            f"Nothing was saved: {len(bad)} sleep lines could not be read (first one: {bad[0][:80]}). "
            "Set the shortcut to send the sleep value as a number: 0 in bed, 1 asleep, 2 awake, "
            "3 core, 4 deep, 5 REM.",
        )
    added = save_readings(background, user_id, samples, stages)

    received = len(samples) + len(stages)
    log.info("shortcut %s %s: %d rows, %d new, %d unreadable", user_id, metric, received, added, len(bad))
    if bad:
        log.warning("shortcut %s: first unreadable line: %s", user_id, bad[0][:200])
    msg = f"{metric}: received {received}, new {added}"
    if bad:
        msg += f", {len(bad)} lines could not be read (first one: {bad[0][:80]})"
    return msg


router.add_api_route(
    "/shortcuts",
    add_shortcut_rows,
    methods=["POST"],
    response_class=PlainTextResponse,
    route_class_override=LargeFormRoute,
)
