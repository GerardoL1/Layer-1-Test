"""
Reads Apple Health's "Export All Health Data" file (export.zip or export.xml)
and loads Layer 1 data into the platform database.

The file can be several GB, so it is streamed record by record instead of
loaded into memory.
"""
import hashlib
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

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


def to_ms(date_str: str) -> int:
    """Apple export dates look like '2026-09-30 23:14:05 -0700'. Returns UTC milliseconds."""
    return int(datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z").timestamp() * 1000)


def stable_id(*parts) -> str:
    """The export has no HealthKit UUIDs, so build a repeatable ID to avoid duplicates on re-import."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()


def open_export_xml(path: str | Path):
    """Accepts either export.zip or an already-unzipped export.xml."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        name = next((n for n in zf.namelist() if n.endswith("/export.xml") or n == "export.xml"), None)
        if name is None:
            raise ValueError("No export.xml found inside the zip. Is this the Apple Health export?")
        return zf.open(name)
    return open(path, "rb")


def iter_records(fileobj) -> Iterator[dict]:
    for _, elem in ET.iterparse(fileobj, events=("end",)):
        if elem.tag == "Record":
            rtype = elem.get("type")
            if rtype in QUANTITY_TYPES or rtype == SLEEP_TYPE:
                yield dict(elem.attrib)
        # Free memory as we go; Record elements can contain nested metadata.
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

    counts = {"heart_rate": 0, "resting_heart_rate": 0, "hrv_sdnn": 0, "sleep_stages": 0, "skipped": 0}
    samples, stages = [], []

    def flush():
        conn.executemany("INSERT OR IGNORE INTO samples VALUES (?,?,?,?,?,?,?,?)", samples)
        conn.executemany("INSERT OR IGNORE INTO sleep_stages VALUES (?,?,?,?,?,?)", stages)
        conn.commit()
        samples.clear()
        stages.clear()
        if progress:
            progress(dict(counts))

    with open_export_xml(path) as f:
        for r in iter_records(f):
            try:
                start_ms, end_ms = to_ms(r["startDate"]), to_ms(r["endDate"])
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
                sid = stable_id(user_id, "sleep", stage, start_ms, end_ms, source)
                stages.append((sid, user_id, stage, start_ms, end_ms, source))
                counts["sleep_stages"] += 1
            else:
                metric = QUANTITY_TYPES[r["type"]]
                try:
                    value = float(r["value"])
                except (KeyError, ValueError):
                    counts["skipped"] += 1
                    continue
                sid = stable_id(user_id, metric, start_ms, round(value, 3), source)
                samples.append((sid, user_id, metric, value, r.get("unit", ""), start_ms, end_ms, source))
                counts[metric] += 1

            if len(samples) + len(stages) >= BATCH:
                flush()
    flush()
    return counts
