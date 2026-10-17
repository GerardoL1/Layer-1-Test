"""
Reads Apple Health's "Export All Health Data" file (export.zip or export.xml)
and loads Layer 1 data into the platform database.

The file can be several GB, so it is streamed record by record instead of
loaded into memory.
"""

import sqlite3
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from app.core import db, limits


class ExportTooLarge(ValueError):
    """The zip would unpack to more than limits.MAX_UNZIPPED_BYTES."""


def check_unzipped_size(path: str | Path) -> None:
    """Refuse a zip whose entries add up to more than the limit, before reading any of it."""
    path = Path(path)
    if path.suffix.lower() != ".zip":
        return
    with zipfile.ZipFile(path) as zf:
        total = sum(info.file_size for info in zf.infolist())
    if total > limits.MAX_UNZIPPED_BYTES:
        raise ExportTooLarge(
            f"This export unzips to {limits.size_text(total)}, over the "
            f"{limits.size_text(limits.MAX_UNZIPPED_BYTES)} limit. Import a shorter export, "
            "or unzip it and upload export.xml."
        )


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
# How often (in records of any type) the import reports how far through the file it is.
TICK_EVERY = 20000
# What the progress line says it's reading, by HealthKit type.
READING = {
    "HKQuantityTypeIdentifierHeartRate": "heart rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting heart rate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "HRV",
    SLEEP_TYPE: "sleep",
}


def parse_date(date_str: str) -> tuple[int, int]:
    """
    Apple export (and Health Auto Export) dates look like '2026-09-30 23:14:05 -0700'.
    Returns UTC milliseconds and the UTC offset in minutes.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z")
    offset = dt.utcoffset()
    if offset is None:
        raise ValueError(f"date has no UTC offset: {date_str}")
    minutes = int(offset.total_seconds() // 60)
    if not db.valid_offset(minutes):
        raise ValueError(f"impossible UTC offset: {date_str}")
    return int(dt.timestamp() * 1000), minutes


def xml_size(path: str | Path) -> int:
    """Size of export.xml in bytes (unzipped), so progress can be shown as a share of it."""
    path = Path(path)
    if path.suffix.lower() != ".zip":
        return path.stat().st_size
    with zipfile.ZipFile(path) as zf:
        name = next((n for n in zf.namelist() if n.endswith("/export.xml") or n == "export.xml"), None)
        return zf.getinfo(name).file_size if name else 0


@contextmanager
def open_export_xml(path: str | Path):
    """Accepts either export.zip or an already-unzipped export.xml."""
    path = Path(path)
    check_unzipped_size(path)
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


def iter_records(fileobj, on_tick: Callable[[int, str], None] | None = None) -> Iterator[dict]:
    """
    Yields the records Layer 1 uses. on_tick(bytes_read, reading) is called every TICK_EVERY
    records, including ones we skip, so progress keeps moving through long stretches of steps etc.
    """
    seen = 0
    for _, elem in ET.iterparse(fileobj, events=("end",)):
        if elem.tag == "Record":
            rtype = elem.get("type")
            seen += 1
            if on_tick and seen % TICK_EVERY == 0:
                on_tick(fileobj.tell(), READING.get(rtype, "other"))
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
    on_position: Callable[[float, str], None] | None = None,
) -> dict:
    """
    Load heart rate, resting HR, HRV and sleep stages from an Apple Health export.
    progress(counts) is called after each saved batch. on_position(share_read, reading) reports
    how far through export.xml the reader is (0 to 1) and what kind of record it's on.
    """
    cutoff_ms = None
    if since_days:
        cutoff_ms = int((datetime.now().timestamp() - since_days * 86400) * 1000)

    counts = {"heart_rate": 0, "resting_heart_rate": 0, "hrv_sdnn": 0, "sleep_stages": 0, "skipped": 0, "new": 0}
    samples: list[tuple] = []
    stages: list[tuple] = []

    def flush():
        # A busy server can keep the database locked for a while. Try a batch a few times before
        # giving up, so a big import doesn't fail just because other people were syncing.
        for attempt in range(4):
            try:
                counts["new"] += db.add_readings(conn, user_id, samples, stages)
                conn.commit()
                break
            except sqlite3.OperationalError as e:
                conn.rollback()
                if "locked" not in str(e) or attempt == 3:
                    raise
                time.sleep(2**attempt)
        samples.clear()
        stages.clear()
        if progress:
            progress(dict(counts))

    total = xml_size(path) if on_position else 0
    tick = (lambda pos, reading: on_position(min(pos / total, 1.0), reading)) if on_position and total else None

    with open_export_xml(path) as f:
        for r in iter_records(f, tick):
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
                stages.append(
                    (
                        db.sleep_id(user_id, stage, start_ms, end_ms, source),
                        stage,
                        start_ms,
                        end_ms,
                        start_tz,
                        end_tz,
                        source,
                    )
                )
                counts["sleep_stages"] += 1
            else:
                metric = QUANTITY_TYPES[r["type"]]
                try:
                    value = float(r["value"])
                except (KeyError, ValueError):
                    counts["skipped"] += 1
                    continue
                samples.append(
                    (
                        db.sample_id(user_id, metric, start_ms, end_ms, value, source),
                        metric,
                        value,
                        start_ms,
                        end_ms,
                        start_tz,
                        source,
                    )
                )
                counts[metric] += 1

            if len(samples) + len(stages) >= BATCH:
                flush()
    flush()
    if on_position:
        on_position(1.0, "done")
    return counts
