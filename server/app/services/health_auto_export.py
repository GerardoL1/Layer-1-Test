"""
Reads the JSON the Health Auto Export iPhone app posts (REST API automation, JSON format).
Its dates carry the UTC offset, e.g. '2026-09-30 23:14:05 -0700'.
"""

from dataclasses import dataclass, field

from app.core import db
from app.services.apple_export import parse_date

HAE_METRICS = {
    "heart_rate": "heart_rate",
    "resting_heart_rate": "resting_heart_rate",
    "heart_rate_variability": "hrv_sdnn",
}
HAE_SLEEP_STAGES = {
    "in bed": "in_bed",
    "inbed": "in_bed",
    "awake": "awake",
    "core": "core",
    "deep": "deep",
    "rem": "rem",
    "asleep": "asleep_unspecified",
}


@dataclass
class Parsed:
    samples: list[tuple] = field(default_factory=list)
    stages: list[tuple] = field(default_factory=list)
    ignored: set[str] = field(default_factory=set)  # metric names we don't use, like steps
    bad: int = 0  # rows whose dates couldn't be read


def parse_payload(payload: dict, user_id: str) -> Parsed:
    out = Parsed()
    metrics = (payload.get("data") or {}).get("metrics") or []

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
                    out.bad += 1
                    continue
                source = row.get("source")
                out.samples.append(
                    (db.sample_id(user_id, metric, t, t, value, source), metric, float(value), t, t, tz, source)
                )

        elif name == "sleep_analysis":
            # Unaggregated sleep phases have a start, end and a stage name.
            for row in rows:
                stage = HAE_SLEEP_STAGES.get(str(row.get("value", "")).strip().lower())
                if not stage or "startDate" not in row or "endDate" not in row:
                    continue
                try:
                    (s, s_tz), (e, e_tz) = parse_date(row["startDate"]), parse_date(row["endDate"])
                except ValueError:
                    out.bad += 1
                    continue
                source = row.get("source")
                out.stages.append((db.sleep_id(user_id, stage, s, e, source), stage, s, e, s_tz, e_tz, source))
        else:
            out.ignored.add(name)

    return out
