"""
Layer 1 preprocessing: Apple Health export -> one ML-ready row per person per night.

Each step is a plain function in its own file that takes the previous step's output, so
the steps can be inspected one at a time (the test platform does this) or chained with
run_pipeline(). All tunable numbers come from config.py. Every step is also available
from here under its old name, so `from layer1 import pipeline as P; P.clean(...)` works.

    1. load_export        read the records we need from export.zip / export.xml
    2. clean              watch-only, de-duplicate, drop impossible values
    3. find_sleep_windows group sleep pieces into sessions, pick each night's main sleep
    4. nightly_metrics    TST, efficiency, fragmentation, overnight HRV and resting HR
    5. flag_quality       mark short, empty and incomplete nights
    6. add_baselines      rolling personal baselines and z-scores (previous nights only)
    7. build_ml_table     final feature table + column dictionary
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from layer1 import config as C
from layer1.baselines import add_baselines
from layer1.clean import clean
from layer1.load import DATE_FORMAT, load_export
from layer1.metrics import NIGHT_COLUMNS, count_awakenings, nightly_metrics, overnight_rhr
from layer1.ml_table import ML_COLUMNS, build_ml_table, column_dictionary
from layer1.quality import flag_quality
from layer1.sleep import find_sleep_windows, resolve_overlaps

__all__ = [
    "DATE_FORMAT",
    "ML_COLUMNS",
    "NIGHT_COLUMNS",
    "PipelineResult",
    "add_baselines",
    "build_ml_table",
    "clean",
    "column_dictionary",
    "count_awakenings",
    "find_sleep_windows",
    "flag_quality",
    "load_export",
    "nightly_metrics",
    "overnight_rhr",
    "resolve_overlaps",
    "run_pipeline",
]


@dataclass
class PipelineResult:
    person_id: str
    type_counts: pd.DataFrame
    records: pd.DataFrame
    cleaned: dict
    removal_log: pd.DataFrame
    removed_rows: pd.DataFrame
    sessions: pd.DataFrame
    stages: pd.DataFrame
    nights: pd.DataFrame  # metrics + flags + baselines (everything)
    ml_table: pd.DataFrame
    notes: list = field(default_factory=list)


def run_pipeline(source, person_id: str = "tester1", days: int | None = C.DEFAULT_DAYS) -> PipelineResult:
    records, type_counts = load_export(source, days)
    cleaned, removal_log, removed_rows = clean(records)
    sessions, stages = find_sleep_windows(cleaned["sleep_stages"])
    metrics = nightly_metrics(sessions, stages, cleaned)
    notes = []
    if metrics.empty:
        notes.append("No sleep sessions found. Is sleep tracking on (iPhone Watch app > Sleep)?")
        first = cleaned["heart_rate"]["start_local"].min()
        last = cleaned["heart_rate"]["start_local"].max()
        nights = flag_quality(
            metrics, first.date() if pd.notna(first) else None, last.date() if pd.notna(last) else None
        )
    else:
        nights = flag_quality(metrics)
    nights = add_baselines(nights) if not nights.empty else nights
    ml = build_ml_table(nights, person_id) if not nights.empty else pd.DataFrame(columns=list(ML_COLUMNS))
    return PipelineResult(
        person_id, type_counts, records, cleaned, removal_log, removed_rows, sessions, stages, nights, ml, notes
    )
