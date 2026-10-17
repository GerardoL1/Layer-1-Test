"""
Step 1. Load: read the records Layer 1 needs from export.zip / export.xml.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

from layer1 import config as C

DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"


def _open_xml(source) -> IO[bytes]:
    """Accepts a path or file-like object pointing at export.zip or export.xml."""
    name = getattr(source, "name", str(source))
    if str(name).lower().endswith(".zip"):
        zf = zipfile.ZipFile(source)
        # The same rule as the server. A zip made on a Mac can also hold __MACOSX/.../._export.xml, which isn't XML.
        names = [n for n in zf.namelist() if not n.startswith("__MACOSX/")]
        inner = next((n for n in names if n == "export.xml" or n.endswith("/export.xml")), None)
        if inner is None:
            raise ValueError(
                "No export.xml inside this zip. Use the zip made by the Health app "
                "(Health > profile picture > Export All Health Data)."
            )
        return zf.open(inner)
    if isinstance(source, (str, Path)):
        return open(source, "rb")
    return source


def load_export(source, days: int | None = C.DEFAULT_DAYS) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Step 1. Stream the export and keep heart rate, resting HR, HRV and sleep records.

    Returns
      records      one row per kept record, with UTC and local timestamps
      type_counts  how many records of every type were in the file (kept or not)
    """
    rows: list[tuple] = []
    counts: dict[str, int] = {}
    with _open_xml(source) as f:
        for _, elem in ET.iterparse(f, events=("end",)):
            if elem.tag == "Record":
                rtype = elem.get("type", "")
                counts[rtype] = counts.get(rtype, 0) + 1
                if rtype in C.QUANTITY_TYPES:
                    rows.append(
                        (
                            "quantity",
                            C.QUANTITY_TYPES[rtype],
                            elem.get("value"),
                            elem.get("unit"),
                            elem.get("sourceName", ""),
                            elem.get("startDate"),
                            elem.get("endDate"),
                        )
                    )
                elif rtype == C.SLEEP_TYPE:
                    rows.append(
                        (
                            "sleep",
                            "sleep_analysis",
                            elem.get("value"),
                            None,
                            elem.get("sourceName", ""),
                            elem.get("startDate"),
                            elem.get("endDate"),
                        )
                    )
            if elem.tag in ("Record", "Workout", "Correlation", "ActivitySummary", "ClinicalRecord"):
                elem.clear()

    type_counts = (
        pd.DataFrame(sorted(counts.items(), key=lambda kv: -kv[1]), columns=["type", "records"])
        if counts
        else pd.DataFrame(columns=["type", "records"])
    )
    type_counts["kept"] = type_counts["type"].isin(list(C.QUANTITY_TYPES) + [C.SLEEP_TYPE])

    records = pd.DataFrame(rows, columns=["kind", "metric", "raw_value", "unit", "source", "start_str", "end_str"])
    if records.empty:
        raise ValueError("No heart rate, HRV or sleep records found in this export.")

    # Apple writes local time with its UTC offset, e.g. "2026-09-30 23:14:05 -0700".
    # UTC is used for ordering and durations; the local wall-clock time decides which night it belongs to.
    for side in ("start", "end"):
        txt = records[f"{side}_str"].astype(str)
        records[f"{side}_utc"] = pd.to_datetime(txt, format=DATE_FORMAT, utc=True, errors="coerce")
        records[f"{side}_local"] = pd.to_datetime(txt.str.slice(0, 19), format="%Y-%m-%d %H:%M:%S", errors="coerce")
    records = records.dropna(subset=["start_utc", "end_utc"]).copy()

    records["value"] = np.where(
        records["kind"] == "quantity", pd.to_numeric(records["raw_value"], errors="coerce"), np.nan
    )
    records["stage"] = records["raw_value"].map(C.SLEEP_VALUES).where(records["kind"] == "sleep")

    # Records dated more than a day ahead come from a wrong clock (say 2099). Kept, one of them would
    # create years of empty nights, so they're dropped and counted for the notes.
    future = records["start_utc"] > pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)
    future_dropped = int(future.sum())
    records = records[~future]
    if records.empty:
        raise ValueError("Every heart rate, HRV and sleep record in this file is dated in the future.")

    if days:
        newest = records.sort_values("end_utc").iloc[-1]
        # Start the window at local noon, where one night's label ends and the next begins
        # (nights are labelled onset minus 12 h), so the first night is never cut in half.
        start = newest["end_local"] - pd.Timedelta(days=days)
        noon = start.normalize() + pd.Timedelta(hours=C.NIGHT_SHIFT_HOURS)
        cutoff = noon if noon <= start else noon - pd.Timedelta(days=1)
        # Someone who sleeps through the day can be asleep at noon. Move the cut back to where that
        # sleep started, so the oldest night is kept whole instead of leaving a piece that looks like a nap.
        sleep = records[records["kind"] == "sleep"]
        gap = pd.Timedelta(minutes=C.SESSION_GAP_MIN)
        while True:
            crossing = sleep[(sleep["start_local"] < cutoff) & (sleep["end_local"] > cutoff - gap)]
            if crossing.empty:
                break
            cutoff = crossing["start_local"].min()
        records = records[records["start_local"] >= cutoff]

    records = records.drop(columns=["start_str", "end_str"]).sort_values("start_utc").reset_index(drop=True)
    records.attrs["future_dropped"] = future_dropped
    return records, type_counts
