"""
Reads what the Apple Shortcuts automation posts: one line per Health sample,
start | end | value | source, with ISO 8601 dates.
"""

import math
from datetime import datetime

from app.core import db
from app.services.time_checks import utc_ms
from layer1.units import factor

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
    offset = dt.utcoffset()
    if offset is None:
        raise ValueError("date has no time zone, set the date format to ISO 8601 with time")
    return utc_ms(dt, offset, text)


def sleep_stage(value: str) -> str | None:
    v = value.strip().lower()
    if v in SLEEP_NUMBERS:
        return SLEEP_NUMBERS[v]
    for word, stage in (
        ("in bed", "in_bed"),
        ("inbed", "in_bed"),
        ("awake", "awake"),
        ("core", "core"),
        ("deep", "deep"),
        ("rem", "rem"),
        ("asleep", "asleep_unspecified"),
    ):
        if word in v:
            return stage
    return None


def parse_rows(user: str, metric: str, rows: str) -> tuple[list[tuple], list[tuple], list[str]]:
    """Returns the samples, the sleep stages and the lines that couldn't be read."""
    samples: list[tuple] = []
    stages: list[tuple] = []
    bad: list[str] = []

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
                # The whole sample may have been inserted, like "48,5 ms". Its unit is converted
                # (a unit we don't know makes the line unreadable), and "48,5" decimals are accepted.
                number, *unit = value_txt.split(None, 1)  # any space, including the no-break kind
                value = float(number.replace(",", "."))
                scale = factor(metric, unit[0] if unit else None)
            except ValueError:
                scale = None
            if scale is None:
                bad.append(line)
                continue
            value *= scale
            if not math.isfinite(value):  # "inf" and "nan" read as numbers, but aren't readings
                bad.append(line)
                continue
            samples.append((db.sample_id(user, metric, s, e, value, source), metric, value, s, e, s_tz, source))

    return samples, stages, bad
