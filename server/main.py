"""
Recovery platform server (API only).

Four ways data can arrive (all land in the same database):
  1. Our iPhone app                  POST /upload
  2. Health Auto Export iPhone app   POST /api/hae       (no Mac needed, paid app feature)
  3. Apple Shortcuts automation      POST /api/shortcut  (no Mac needed, free)
  4. Apple Health export file        POST /api/import  or  python import_export.py

Every reading is stored with its UTC offset so nights can be worked out in local time.

Run:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

import db
from apple_export import import_export, parse_date

app = FastAPI(title="Recovery platform")

# Wide open for testing only.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db.init_db()


@app.get("/health")
def health():
    """Open this from the phone's browser to check it can reach the server."""
    return {"ok": True}


# ---------------------------------------------------------------- 1. our iPhone app

class Sample(BaseModel):
    uuid: str
    metric: str
    value: float
    start_ms: int
    end_ms: int
    tz_offset_min: int | None = None  # minutes ahead of UTC when the reading was taken
    source: str | None = None
    unit: str | None = None           # ignored, each metric has one fixed unit


class SleepStage(BaseModel):
    uuid: str
    stage: str                        # in_bed, awake, core, deep, rem, asleep_unspecified
    start_ms: int
    end_ms: int
    start_tz_min: int | None = None
    end_tz_min: int | None = None
    source: str | None = None


class Upload(BaseModel):
    user_id: str
    samples: list[Sample] = []
    sleep: list[SleepStage] = []


def require_offset(minutes, what: str) -> int:
    # Without the offset we can't tell which night a reading belongs to, so refuse it.
    if minutes is None:
        raise HTTPException(400, f"{what} is missing its UTC offset (tz_offset_min). "
                                 "Update the app so it sends the time zone with every reading.")
    if not db.valid_offset(minutes):
        raise HTTPException(400, f"{what} has an impossible UTC offset: {minutes} minutes.")
    return minutes


@app.post("/upload")
def upload(payload: Upload):
    samples, stages = [], []
    for s in payload.samples:
        if s.metric not in db.METRICS:
            raise HTTPException(400, f"Unknown metric '{s.metric}'. Use one of: {', '.join(db.METRICS)}")
        tz = require_offset(s.tz_offset_min, f"{s.metric} sample {s.uuid}")
        samples.append((s.uuid, s.metric, s.value, s.start_ms, s.end_ms, tz, s.source))
    for s in payload.sleep:
        if s.stage not in db.STAGES:
            raise HTTPException(400, f"Unknown sleep stage '{s.stage}'. Use one of: {', '.join(db.STAGES)}")
        start_tz = require_offset(s.start_tz_min, f"sleep stage {s.uuid}")
        end_tz = require_offset(s.end_tz_min, f"sleep stage {s.uuid}")
        stages.append((s.uuid, s.stage, s.start_ms, s.end_ms, start_tz, end_tz, s.source))

    with db.connect() as conn:
        added = db.add_readings(conn, payload.user_id, samples, stages)
    received = len(samples) + len(stages)
    print(f"[upload] {payload.user_id}: received {received}, new {added}")
    return {"received": received, "new": added}


# ---------------------------------------------------------------- 2. Health Auto Export

HAE_METRICS = {
    "heart_rate": "heart_rate",
    "resting_heart_rate": "resting_heart_rate",
    "heart_rate_variability": "hrv_sdnn",
}
HAE_SLEEP_STAGES = {
    "in bed": "in_bed", "inbed": "in_bed", "awake": "awake", "core": "core",
    "deep": "deep", "rem": "rem", "asleep": "asleep_unspecified",
}


@app.post("/api/hae")
async def health_auto_export(request: Request, user_id: str = "tester1"):
    """
    Receiver for the Health Auto Export app (REST API automation, JSON format).
    Set the URL in the app to:  http://<computer-ip>:8000/api/hae?user_id=<tester name>
    Its dates carry the UTC offset, e.g. '2026-09-30 23:14:05 -0700'.
    """
    payload = await request.json()
    metrics = (payload.get("data") or {}).get("metrics") or []
    samples, stages, ignored, bad = [], [], set(), 0

    for m in metrics:
        name = m.get("name", "")
        rows = m.get("data") or []

        if name in HAE_METRICS:
            metric = HAE_METRICS[name]
            for row in rows:
                # Heart rate comes as Min/Avg/Max per interval, other metrics as qty.
                value = row.get("qty", row.get("Avg"))
                if value is None or "date" not in row:
                    continue
                try:
                    t, tz = parse_date(row["date"])
                except ValueError:
                    bad += 1
                    continue
                source = row.get("source")
                samples.append((db.sample_id(user_id, metric, t, t, value, source),
                                metric, float(value), t, t, tz, source))

        elif name == "sleep_analysis":
            # Unaggregated sleep phases have a start, end and a stage name.
            for row in rows:
                stage = HAE_SLEEP_STAGES.get(str(row.get("value", "")).strip().lower())
                if not stage or "startDate" not in row or "endDate" not in row:
                    continue
                try:
                    (s, s_tz), (e, e_tz) = parse_date(row["startDate"]), parse_date(row["endDate"])
                except ValueError:
                    bad += 1
                    continue
                source = row.get("source")
                stages.append((db.sleep_id(user_id, stage, s, e, source), stage, s, e, s_tz, e_tz, source))
        else:
            ignored.add(name)

    with db.connect() as conn:
        added = db.add_readings(conn, user_id, samples, stages)

    print(f"[hae] {user_id}: {len(samples)} samples, {len(stages)} sleep stages, {added} new"
          f"{', ' + str(bad) + ' unreadable dates' if bad else ''}"
          f"{' ignored: ' + ', '.join(sorted(ignored)) if ignored else ''}")
    return {"samples": len(samples), "sleep_stages": len(stages), "new": added,
            "unreadable": bad, "ignored_metrics": sorted(ignored)}


# ---------------------------------------------------------------- 3. Apple Shortcuts

SHORTCUT_METRICS = ("heart_rate", "resting_heart_rate", "hrv_sdnn", "sleep")
# HealthKit's numeric sleep values, in case Shortcuts sends numbers instead of names
SLEEP_NUMBERS = {"0": "in_bed", "1": "asleep_unspecified", "2": "awake", "3": "core", "4": "deep", "5": "rem"}


def shortcut_date(text: str) -> tuple[int, int]:
    """
    Shortcuts' ISO 8601 dates, e.g. 2026-10-01T14:02:11-07:00 (with or without the colon, or Z).
    Returns UTC milliseconds and the UTC offset in minutes.
    """
    text = text.strip().replace("Z", "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":  # -0700 -> -07:00
        text = text[:-2] + ":" + text[-2:]
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("date has no time zone, set the date format to ISO 8601 with time")
    return int(dt.timestamp() * 1000), int(dt.utcoffset().total_seconds() // 60)


def sleep_stage(value: str) -> str | None:
    v = value.strip().lower()
    if v in SLEEP_NUMBERS:
        return SLEEP_NUMBERS[v]
    for word, stage in (("in bed", "in_bed"), ("inbed", "in_bed"), ("awake", "awake"), ("core", "core"),
                        ("deep", "deep"), ("rem", "rem"), ("asleep", "asleep_unspecified")):
        if word in v:
            return stage
    return None


@app.post("/api/shortcut", response_class=PlainTextResponse)
def apple_shortcut(user: str = Form(...), metric: str = Form(...), rows: str = Form("")):
    """
    Receiver for the Apple Shortcuts automation. Form fields:
      user    tester name
      metric  heart_rate | resting_heart_rate | hrv_sdnn | sleep
      rows    one line per Health sample:  start | end | value | source
    Replies in plain text so the shortcut can show the result.
    """
    metric = metric.strip()
    if metric not in SHORTCUT_METRICS:
        raise HTTPException(400, f"Unknown metric '{metric}'. Use one of: {', '.join(SHORTCUT_METRICS)}")
    user = user.strip()
    samples, stages, bad = [], [], []

    for line in rows.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|", 3)]
        if len(parts) < 3:
            bad.append(line)
            continue
        start_txt, end_txt, value_txt = parts[:3]
        source = parts[3] if len(parts) > 3 and parts[3] else None
        try:
            (s, s_tz), (e, e_tz) = shortcut_date(start_txt), shortcut_date(end_txt)
        except ValueError:
            bad.append(line)
            continue

        if metric == "sleep":
            stage = sleep_stage(value_txt)
            if stage is None:
                bad.append(line)
                continue
            stages.append((db.sleep_id(user, stage, s, e, source), stage, s, e, s_tz, e_tz, source))
        else:
            try:
                # Strip units if the whole sample was inserted, and accept "48,5" decimals.
                value = float(value_txt.split()[0].replace(",", "."))
            except (ValueError, IndexError):
                bad.append(line)
                continue
            samples.append((db.sample_id(user, metric, s, e, value, source), metric, value, s, e, s_tz, source))

    with db.connect() as conn:
        added = db.add_readings(conn, user, samples, stages)

    received = len(samples) + len(stages)
    print(f"[shortcut] {user} {metric}: {received} rows, {added} new, {len(bad)} unreadable")
    if bad:
        print("  first unreadable line:", bad[0][:200])
    msg = f"{metric}: received {received}, new {added}"
    if bad:
        msg += f", {len(bad)} lines could not be read (first one: {bad[0][:80]})"
    return msg


# ---------------------------------------------------------------- 4. Apple Health export file

IMPORT_STATUS: dict = {"state": "idle"}


def run_import(path: str, user_id: str, since_days: int | None):
    IMPORT_STATUS.update(state="running", user_id=user_id, counts={}, error=None)
    try:
        conn = db.connect()
        counts = import_export(path, conn, user_id, since_days,
                               progress=lambda c: IMPORT_STATUS.update(counts=c))
        conn.close()
        IMPORT_STATUS.update(state="done", counts=counts)
    except Exception as e:  # report any parsing problem to whoever is polling the status
        IMPORT_STATUS.update(state="error", error=str(e))
    finally:
        Path(path).unlink(missing_ok=True)


@app.post("/api/import")
async def import_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form("tester1"),
    since_days: int = Form(90),
):
    if IMPORT_STATUS.get("state") in ("queued", "running"):
        raise HTTPException(409, "An import is already running. Wait for it to finish.")
    if not file.filename.lower().endswith((".zip", ".xml")):
        raise HTTPException(400, "Upload the export.zip (or export.xml) from the Health app.")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix)
    with tmp:
        shutil.copyfileobj(file.file, tmp)
    IMPORT_STATUS.update(state="queued", user_id=user_id, counts={}, error=None)
    background.add_task(run_import, tmp.name, user_id, since_days or None)
    return {"started": True}


@app.get("/api/import/status")
def import_status():
    return IMPORT_STATUS
