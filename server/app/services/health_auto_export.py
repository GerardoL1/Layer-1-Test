"""
Reads the JSON the Health Auto Export iPhone app posts (REST API automation, JSON format).
Its dates carry the UTC offset, e.g. '2026-09-30 23:14:05 -0700'.
"""

import math
import re
from dataclasses import dataclass, field

from app.core import db
from app.services.apple_export import parse_date

HAE_METRICS = {
    "heart_rate": "heart_rate",
    "resting_heart_rate": "resting_heart_rate",
    "heart_rate_variability": "hrv_sdnn",
}
# Sleep value names, with spaces, punctuation and case removed first ("Core Sleep" -> "coresleep").
HAE_SLEEP_STAGES = {
    "inbed": "in_bed",
    "awake": "awake",
    "core": "core",
    "coresleep": "core",
    "asleepcore": "core",
    "deep": "deep",
    "deepsleep": "deep",
    "asleepdeep": "deep",
    "rem": "rem",
    "remsleep": "rem",
    "asleeprem": "rem",
    "asleep": "asleep_unspecified",
    "unspecified": "asleep_unspecified",
    "asleepunspecified": "asleep_unspecified",
}


def _stage(value) -> str | None:
    return HAE_SLEEP_STAGES.get(re.sub(r"[^a-z]", "", str(value).lower()))


@dataclass
class Parsed:
    samples: list[tuple] = field(default_factory=list)
    stages: list[tuple] = field(default_factory=list)
    ignored: set[str] = field(default_factory=set)  # metric names we don't use, like steps
    bad: int = 0  # rows that couldn't be read: bad dates, impossible offsets, values that aren't numbers
    aggregated_sleep: int = 0  # nightly sleep summaries, which have no stages to work with


class BadPayload(ValueError):
    """The body isn't shaped like Health Auto Export's JSON at all."""


def parse_payload(payload, user_id: str) -> Parsed:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(payload, dict) or not isinstance(data or {}, dict):
        raise BadPayload("Expected Health Auto Export's JSON: an object with data.metrics.")
    metrics = (data or {}).get("metrics") or []
    if not isinstance(metrics, list):
        raise BadPayload("data.metrics should be a list.")
    out = Parsed()

    for m in metrics:
        if not isinstance(m, dict):
            out.bad += 1
            continue
        name = m.get("name", "")
        rows = m.get("data") or []
        if not isinstance(name, str) or not isinstance(rows, list):
            out.bad += 1
            continue
        rows = _objects(rows, out)

        if name in HAE_METRICS:
            metric = HAE_METRICS[name]
            for row in rows:
                # Heart rate comes as Min/Avg/Max per interval, other metrics as qty.
                value = row.get("qty", row.get("Avg"))
                if value is None or "date" not in row:
                    continue
                source = row.get("source")
                try:
                    t, tz = parse_date(row["date"])
                    value = float(value)
                except (TypeError, ValueError, OverflowError):  # OverflowError: a number too big for a float
                    out.bad += 1
                    continue
                if not math.isfinite(value) or (source is not None and not isinstance(source, str)):
                    out.bad += 1
                    continue
                out.samples.append(
                    (db.sample_id(user_id, metric, t, t, value, source), metric, value, t, t, tz, source)
                )

        elif name == "sleep_analysis":
            # Unaggregated sleep phases have a start, end and a stage name.
            for row in rows:
                if "startDate" not in row and ("sleepStart" in row or "inBedStart" in row):
                    out.aggregated_sleep += 1
                    out.bad += 1
                    continue
                if "startDate" not in row or "endDate" not in row:
                    continue
                stage = _stage(row.get("value", ""))
                source = row.get("source")
                if stage is None or (source is not None and not isinstance(source, str)):
                    out.bad += 1  # a sleep value we don't know, so the night would be missing a piece
                    continue
                try:
                    (s, s_tz), (e, e_tz) = parse_date(row["startDate"]), parse_date(row["endDate"])
                except (TypeError, ValueError):
                    out.bad += 1
                    continue
                out.stages.append((db.sleep_id(user_id, stage, s, e, source), stage, s, e, s_tz, e_tz, source))
        else:
            out.ignored.add(str(name))

    return out


def _objects(rows: list, out: Parsed) -> list[dict]:
    """The rows that are JSON objects. Anything else is counted as unreadable."""
    kept = []
    for row in rows:
        if isinstance(row, dict):
            kept.append(row)
        else:
            out.bad += 1
    return kept
