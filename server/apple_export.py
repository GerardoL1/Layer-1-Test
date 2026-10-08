"""
Reads Apple Health's "Export All Health Data" file (export.zip or export.xml)
and loads Layer 1 data into the platform database.

The file can be several GB, so it is streamed record by record instead of
loaded into memory.
"""
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

import db

# HealthKit type -> our metric name
QUANTITY_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
}
SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"

# HealthKit sleep values -> short stage names
SLEEP_STAGES = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_unspecified",  # older iOS versions
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
}

BATCH = 5000


def parse_date(date_str: str) -> tuple[int, int]:
    """
    Apple export (and Health Auto Export) dates look like '2026-09-30 23:14:05 -0700'.
    Returns UTC milliseconds and the UTC offset in minutes.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")
    return int(dt.timestamp() * 1000), int(dt.utcoffset().total_seconds() // 60)


@contextmanager
def open_export_xml(path: str | Path):
    """Accepts either export.zip or an already-unzipped export.xml."""
    path = Path(path)
    if path.suffix.lower() != ".zip":
        with open(path, "rb") as f:
            yield f
        return
    # Close the zip itself too, or Windows won't let us delete the uploaded file afterwards.
    with zipfile.ZipFile(path) as zf:
        name = next((n for n in zf.namelist() if n.endswith("/export.xml") or n == "export.xml"), None)
        if name is None:
            raise ValueError("No export.xml found inside the zip. Is this the Apple Health export?")
        with zf.open(name) as f:
            yield f


def iter_records(fileobj) -> Iterator[dict]:
    for _, elem in ET.iterparse(fileobj, events=("end",)):
        if elem.tag == "Record":
            rtype = elem.get("type")
            if rtype in QUANTITY_TYPES or rtype == SLEEP_TYPE:
                yield dict(elem.attrib)
        # Free memory as we go. Record elements can contain nested metadata.
        if elem.tag in ("Record", "Workout", "ActivitySummary", "Correlation"):
            elem.clear()


def import_export(
    path: str | Path,
    conn: sqlite3.Connection,
    user_id: str,
    since_days: int | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """Load heart rate, resting HR, HRV and sleep stages from an Apple Health export."""
    cutoff_ms = None
    if since_days:
        cutoff_ms = int((datetime.now().timestamp() - since_days * 86400) * 1000)

    counts = {"heart_rate": 0, "resting_heart_rate": 0, "hrv_sdnn": 0, "sleep_stages": 0,
              "skipped": 0, "new": 0}
    samples, stages = [], []

    def flush():
        counts["new"] += db.add_readings(conn, user_id, samples, stages)
        conn.commit()
        samples.clear()
        stages.clear()
        if progress:
            progress(dict(counts))

    with open_export_xml(path) as f:
        for r in iter_records(f):
            try:
                start_ms, start_tz = parse_date(r["startDate"])
                end_ms, end_tz = parse_date(r["endDate"])
            except (KeyError, ValueError):
                counts["skipped"] += 1
                continue
            if cutoff_ms and start_ms < cutoff_ms:
                continue
            source = r.get("sourceName")

            if r["type"] == SLEEP_TYPE:
                stage = SLEEP_STAGES.get(r.get("value", ""))
                if stage is None:
                    counts["skipped"] += 1
                    continue
                stages.append((db.sleep_id(user_id, stage, start_ms, end_ms, source),
                               stage, start_ms, end_ms, start_tz, end_tz, source))
                counts["sleep_stages"] += 1
            else:
                metric = QUANTITY_TYPES[r["type"]]
                try:
                    value = float(r["value"])
                except (KeyError, ValueError):
                    counts["skipped"] += 1
                    continue
                samples.append((db.sample_id(user_id, metric, start_ms, end_ms, value, source),
                                metric, value, start_ms, end_ms, start_tz, source))
                counts[metric] += 1

            if len(samples) + len(stages) >= BATCH:
                flush()
    flush()
    return counts
