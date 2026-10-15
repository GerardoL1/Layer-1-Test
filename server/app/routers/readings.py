"""
Three of the four ways readings arrive (the fourth, the export file, is in imports.py):
  1. Our iPhone app                  POST /upload
  2. Health Auto Export iPhone app   POST /api/hae       (no Mac needed, paid app feature)
  3. Apple Shortcuts automation      POST /api/shortcut  (no Mac needed, free)
"""

import logging

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse

from app.core import db
from app.schemas.readings import Upload
from app.services import health_auto_export, shortcuts
from app.services.readings import save_readings

log = logging.getLogger("recovery.ingest")

router = APIRouter(tags=["readings"])


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


@router.post("/upload")
def upload(payload: Upload, background: BackgroundTasks):
    samples: list[tuple] = []
    stages: list[tuple] = []
    for q in payload.samples:
        if q.metric not in db.METRICS:
            raise HTTPException(400, f"Unknown metric '{q.metric}'. Use one of: {', '.join(db.METRICS)}")
        tz = require_offset(q.tz_offset_min, f"{q.metric} sample {q.uuid}")
        samples.append((q.uuid, q.metric, q.value, q.start_ms, q.end_ms, tz, q.source))
    for st in payload.sleep:
        if st.stage not in db.STAGES:
            raise HTTPException(400, f"Unknown sleep stage '{st.stage}'. Use one of: {', '.join(db.STAGES)}")
        start_tz = require_offset(st.start_tz_min, f"sleep stage {st.uuid}")
        end_tz = require_offset(st.end_tz_min, f"sleep stage {st.uuid}")
        stages.append((st.uuid, st.stage, st.start_ms, st.end_ms, start_tz, end_tz, st.source))

    added = save_readings(background, payload.user_id, samples, stages)
    received = len(samples) + len(stages)
    log.info("upload %s: received %d, new %d", payload.user_id, received, added)
    return {"received": received, "new": added}


# ---------------------------------------------------------------- 2. Health Auto Export


@router.post("/api/hae")
async def health_auto_export_receiver(request: Request, background: BackgroundTasks, user_id: str = "tester1"):
    """
    Receiver for the Health Auto Export app (REST API automation, JSON format).
    Set the URL in the app to:  http://<computer-ip>:8000/api/hae?user_id=<tester name>
    Its dates carry the UTC offset, e.g. '2026-09-30 23:14:05 -0700'.
    """
    parsed = health_auto_export.parse_payload(await request.json(), user_id)
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
    return {
        "samples": len(parsed.samples),
        "sleep_stages": len(parsed.stages),
        "new": added,
        "unreadable": parsed.bad,
        "ignored_metrics": sorted(parsed.ignored),
    }


# ---------------------------------------------------------------- 3. Apple Shortcuts


@router.post("/api/shortcut", response_class=PlainTextResponse)
def apple_shortcut(background: BackgroundTasks, user: str = Form(...), metric: str = Form(...), rows: str = Form("")):
    """
    Receiver for the Apple Shortcuts automation. Form fields:
      user    tester name
      metric  heart_rate | resting_heart_rate | hrv_sdnn | sleep
      rows    one line per Health sample:  start | end | value | source
    Replies in plain text so the shortcut can show the result.
    """
    metric = metric.strip()
    if metric not in shortcuts.SHORTCUT_METRICS:
        raise HTTPException(400, f"Unknown metric '{metric}'. Use one of: {', '.join(shortcuts.SHORTCUT_METRICS)}")
    user = user.strip()
    samples, stages, bad = shortcuts.parse_rows(user, metric, rows)
    added = save_readings(background, user, samples, stages)

    received = len(samples) + len(stages)
    log.info("shortcut %s %s: %d rows, %d new, %d unreadable", user, metric, received, added, len(bad))
    if bad:
        log.warning("shortcut %s: first unreadable line: %s", user, bad[0][:200])
    msg = f"{metric}: received {received}, new {added}"
    if bad:
        msg += f", {len(bad)} lines could not be read (first one: {bad[0][:80]})"
    return msg
