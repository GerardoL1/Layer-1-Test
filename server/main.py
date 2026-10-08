"""
Test server for the recovery platform.

Four ways data can arrive (all land in the same database):
  1. Our iPhone test app             POST /upload        (needs a Mac to build)
  2. Health Auto Export iPhone app   POST /api/hae       (no Mac needed, paid app feature)
  3. Apple Shortcuts automation      POST /api/shortcut  (no Mac needed, free)
  4. Apple Health export file        upload at /  or  python import_export.py  (no Mac needed)

Run:
    pip install -r requirements.txt
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
import json
import shutil
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from apple_export import import_export, stable_id

DB_PATH = "platform.db"
RAW_DIR = Path("hae_raw")  # copies of Health Auto Export payloads, for debugging

app = FastAPI(title="Recovery platform (test)")

# Wide open for testing only.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS samples (
                uuid     TEXT PRIMARY KEY,   -- HealthKit ID, or a stable hash for imports
                user_id  TEXT NOT NULL,
                metric   TEXT NOT NULL,      -- heart_rate, resting_heart_rate, hrv_sdnn
                value    REAL NOT NULL,
                unit     TEXT NOT NULL,
                start_ms INTEGER NOT NULL,   -- UTC milliseconds
                end_ms   INTEGER NOT NULL,
                source   TEXT
            );
            CREATE TABLE IF NOT EXISTS sleep_stages (
                id       TEXT PRIMARY KEY,
                user_id  TEXT NOT NULL,
                stage    TEXT NOT NULL,      -- in_bed, awake, core, deep, rem, asleep_unspecified
                start_ms INTEGER NOT NULL,
                end_ms   INTEGER NOT NULL,
                source   TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_samples_lookup ON samples(user_id, metric, start_ms);
            CREATE INDEX IF NOT EXISTS idx_sleep_lookup ON sleep_stages(user_id, start_ms);
            """
        )


init_db()


# ---------------------------------------------------------------- 1. our iPhone app

class Sample(BaseModel):
    uuid: str
    metric: str
    value: float
    unit: str
    start_ms: int
    end_ms: int
    source: str | None = None


class Upload(BaseModel):
    user_id: str
    samples: list[Sample]


@app.get("/health")
def health():
    """Open this from the phone's browser to check it can reach the server."""
    return {"ok": True}


@app.post("/upload")
def upload(payload: Upload):
    with db() as conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?)",
            [(s.uuid, payload.user_id, s.metric, s.value, s.unit, s.start_ms, s.end_ms, s.source)
             for s in payload.samples],
        )
        added = conn.total_changes - before
    print(f"[upload] {payload.user_id}: received {len(payload.samples)}, new {added}")
    return {"received": len(payload.samples), "new": added}


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


def hae_ms(date_str: str) -> int:
    # Health Auto Export dates look like '2026-09-30 23:14:05 -0700'
    return int(datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z").timestamp() * 1000)


@app.post("/api/hae")
async def health_auto_export(request: Request, user_id: str = "tester1"):
    """
    Receiver for the Health Auto Export app (REST API automation, JSON format).
    Set the URL in the app to:  http://<computer-ip>:8000/api/hae?user_id=<tester name>
    """
    payload = await request.json()

    RAW_DIR.mkdir(exist_ok=True)
    raw_file = RAW_DIR / f"{user_id}_{datetime.now():%Y%m%d_%H%M%S}.json"
    raw_file.write_text(json.dumps(payload))

    metrics = (payload.get("data") or {}).get("metrics") or []
    samples, stages, ignored = [], [], set()

    for m in metrics:
        name, units = m.get("name", ""), m.get("units", "")
        rows = m.get("data") or []

        if name in HAE_METRICS:
            metric = HAE_METRICS[name]
            for row in rows:
                # Heart rate comes as Min/Avg/Max per interval; other metrics as qty.
                value = row.get("qty", row.get("Avg"))
                if value is None or "date" not in row:
                    continue
                t = hae_ms(row["date"])
                source = row.get("source")
                samples.append((stable_id(user_id, metric, t, round(float(value), 3), source),
                                user_id, metric, float(value), units, t, t, source))

        elif name == "sleep_analysis":
            # Unaggregated sleep phases have a start, end and a stage name.
            for row in rows:
                stage = HAE_SLEEP_STAGES.get(str(row.get("value", "")).strip().lower())
                if not stage or "startDate" not in row or "endDate" not in row:
                    continue
                s, e = hae_ms(row["startDate"]), hae_ms(row["endDate"])
                source = row.get("source")
                stages.append((stable_id(user_id, "sleep", stage, s, e, source), user_id, stage, s, e, source))
        else:
            ignored.add(name)

    with db() as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?)", samples)
        conn.executemany("INSERT OR IGNORE INTO sleep_stages VALUES (?,?,?,?,?,?)", stages)
        added = conn.total_changes - before

    print(f"[hae] {user_id}: {len(samples)} samples, {len(stages)} sleep stages, {added} new "
          f"(raw copy: {raw_file}){' ignored: ' + ', '.join(sorted(ignored)) if ignored else ''}")
    return {"samples": len(samples), "sleep_stages": len(stages), "new": added,
            "ignored_metrics": sorted(ignored)}


# ---------------------------------------------------------------- 3. Apple Shortcuts

SHORTCUT_METRICS = {"heart_rate": "count/min", "resting_heart_rate": "count/min", "hrv_sdnn": "ms", "sleep": None}
# HealthKit's numeric sleep values, in case Shortcuts sends numbers instead of names
SLEEP_NUMBERS = {"0": "in_bed", "1": "asleep_unspecified", "2": "awake", "3": "core", "4": "deep", "5": "rem"}


def shortcut_date(text: str) -> int:
    """Shortcuts' ISO 8601 dates, e.g. 2026-10-01T14:02:11-07:00 (with or without the colon, or Z)."""
    text = text.strip().replace("Z", "+00:00")
    if len(text) >= 5 and text[-5] in "+-" and text[-3] != ":":  # -0700 -> -07:00
        text = text[:-2] + ":" + text[-2:]
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        raise ValueError("date has no time zone; set the date format to ISO 8601 with time")
    return int(dt.timestamp() * 1000)


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
            s, e = shortcut_date(start_txt), shortcut_date(end_txt)
        except ValueError:
            bad.append(line)
            continue

        if metric == "sleep":
            stage = sleep_stage(value_txt)
            if stage is None:
                bad.append(line)
                continue
            stages.append((stable_id(user, "sleep", stage, s, e, source), user, stage, s, e, source))
        else:
            try:
                # Strip units if the whole sample was inserted, and accept "48,5" decimals.
                value = float(value_txt.split()[0].replace(",", "."))
            except (ValueError, IndexError):
                bad.append(line)
                continue
            samples.append((stable_id(user, metric, s, round(value, 3), source),
                            user, metric, value, SHORTCUT_METRICS[metric], s, e, source))

    with db() as conn:
        before = conn.total_changes
        conn.executemany("INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?)", samples)
        conn.executemany("INSERT OR IGNORE INTO sleep_stages VALUES (?,?,?,?,?,?)", stages)
        added = conn.total_changes - before

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
        conn = sqlite3.connect(DB_PATH)
        counts = import_export(path, conn, user_id, since_days,
                               progress=lambda c: IMPORT_STATUS.update(counts=c))
        conn.close()
        IMPORT_STATUS.update(state="done", counts=counts)
    except Exception as e:  # report any parsing problem on the page
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
    if IMPORT_STATUS.get("state") == "running":
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


# ---------------------------------------------------------------- read endpoints for the dashboard

@app.get("/api/samples")
def get_samples(metric: str = "heart_rate", hours: int = 24, user_id: str | None = None):
    since = int((datetime.now(timezone.utc) - timedelta(hours=hours)).timestamp() * 1000)
    query = "SELECT * FROM samples WHERE metric = ? AND start_ms >= ?"
    args: list = [metric, since]
    if user_id:
        query += " AND user_id = ?"
        args.append(user_id)
    with db() as conn:
        rows = conn.execute(query + " ORDER BY start_ms", args).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/sleep")
def get_sleep(days: int = 7, user_id: str | None = None):
    since = int((datetime.now(timezone.utc) - timedelta(days=days + 1)).timestamp() * 1000)
    query = "SELECT user_id, stage, start_ms, end_ms, source FROM sleep_stages WHERE start_ms >= ?"
    args: list = [since]
    if user_id:
        query += " AND user_id = ?"
        args.append(user_id)
    with db() as conn:
        rows = conn.execute(query + " ORDER BY start_ms", args).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/summary")
def summary():
    with db() as conn:
        rows = conn.execute(
            """SELECT user_id, metric, COUNT(*) AS n, ROUND(AVG(value), 1) AS avg,
                      MIN(start_ms) AS first_ms, MAX(start_ms) AS last_ms
               FROM samples GROUP BY user_id, metric
               UNION ALL
               SELECT user_id, 'sleep_stages', COUNT(*), NULL, MIN(start_ms), MAX(start_ms)
               FROM sleep_stages GROUP BY user_id
               ORDER BY 1, 2"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return (Path(__file__).parent / "dashboard.html").read_text()
