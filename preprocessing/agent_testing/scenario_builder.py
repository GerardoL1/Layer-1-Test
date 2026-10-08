"""
Turn a scenario description (JSON) into a fake Apple Health export AND the exact truth
the preprocessing should find in it.

A scenario is a made-up person with a story ("overtrains in week 4", "night-shift
worker", "forgets the watch"). Because this builder writes every record itself, it knows
exactly how much the person slept, how many times they woke up, which HRV readings fell
inside each night, and so on. The checks then compare the pipeline's output with that
truth instead of trusting the pipeline to grade itself.

Scenario format (see scenarios/*.json for examples):

{
  "name": "short_name",
  "description": "What this person is like and what should happen",
  "nights": 35,                       # number of nights to generate (night 1 = first evening)
  "end_date": "2026-10-01",           # date of the last morning
  "utc_offset": "-0500",
  "seed": 1,
  "baseline": {"rhr": 58, "hrv": 50, "sleep_hours": 7.3, "bedtime": "23:15", "wake_ups": 2},
  "events": [ ... see EVENT TYPES below ... ],
  "expect": [ ... see checks.py ... ]
}

Nights are numbered 1..N. Night n starts on the evening of date (end_date - N + n - 1)
and ends on the following morning.

EVENT TYPES ("nights" can be a list like [3, 4] or "all" or {"from": 20, "to": 35})
  {"type": "overreach", "nights": ..., "hrv_change_pct": -30, "rhr_change_bpm": 6,
       "sleep_change_hours": -1, "extra_wake_ups": 2, "ramp": true}
  {"type": "no_sleep_data", "nights": [...]}           watch not worn overnight
  {"type": "no_hrv", "nights": [...]}                  no HRV reading that night
  {"type": "short_sleep", "nights": [...], "hours": 2.5}
  {"type": "bedtime", "nights": [...], "time": "02:30"}  times before 12:00 = next morning
  {"type": "no_stages", "nights": [...]}               older watch: only "asleep", no core/deep/REM
  {"type": "nap", "nights": [...], "time": "14:00", "minutes": 30}   nap on the afternoon of that night's date
  {"type": "in_bed", "nights": ...}                    iPhone "In Bed" records
  {"type": "few_hr", "nights": [...], "every_minutes": 40}  loose strap: sparse HR during sleep
  {"type": "late_hrv_hours", "hours": 26}              (daily-update simulation) HRV arrives late
  {"type": "utc_offset", "from_night": 18, "offset": "-0800"}  travel / time-zone change
  {"type": "duplicates", "rate": 0.02}                 re-sent records
  {"type": "glitches", "count": 6}                     impossible HR values (12, 250 bpm)
  {"type": "other_app_hr", "nights": [...]}            HR written by another app
  {"type": "other_app_sleep", "nights": [...]}         a third-party sleep app's "asleep" record
"""
from __future__ import annotations

import io
import json
import math
import random
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

WATCH = "Tester’s Apple Watch"
PHONE = "Tester’s iPhone"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
HR = "HKQuantityTypeIdentifierHeartRate"
HRV = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
RHR = "HKQuantityTypeIdentifierRestingHeartRate"


def _nights(spec, total: int) -> list[int]:
    if spec in (None, "all"):
        return list(range(1, total + 1))
    if isinstance(spec, dict):
        return list(range(int(spec.get("from", 1)), int(spec.get("to", total)) + 1))
    return [int(n) for n in spec]


def _hhmm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)


def _offset_td(off: str) -> timedelta:
    sign = -1 if off[0] == "-" else 1
    return sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))


@dataclass
class Record:
    rtype: str
    source: str
    start: datetime          # local wall-clock time
    end: datetime
    offset: str
    value: str
    unit: str | None = None

    def xml(self) -> str:
        f = lambda d: d.strftime("%Y-%m-%d %H:%M:%S ") + self.offset
        u = f' unit="{self.unit}"' if self.unit else ""
        return (f'<Record type="{self.rtype}" sourceName="{self.source}"{u} creationDate="{f(self.end)}" '
                f'startDate="{f(self.start)}" endDate="{f(self.end)}" value="{self.value}"/>')

    @property
    def utc_end(self) -> datetime:
        return self.end - _offset_td(self.offset)


@dataclass
class Scenario:
    spec: dict
    records: list = field(default_factory=list)
    truth: dict = field(default_factory=dict)

    def export_zip(self) -> bytes:
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<HealthData locale="en_US">\n'
               + "\n".join(r.xml() for r in self.records) + "\n</HealthData>\n")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("apple_health_export/export.xml", xml)
        return buf.getvalue()

    def save(self, folder: Path) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.spec['name']}.zip"
        path.write_bytes(self.export_zip())
        (folder / f"{self.spec['name']}_truth.json").write_text(json.dumps(self.truth, indent=1, default=str))
        return path


def build(spec: dict) -> Scenario:
    rng = random.Random(spec.get("seed", 1))
    N = int(spec.get("nights", 30))
    end_date = date.fromisoformat(spec.get("end_date", "2026-10-01"))
    first_evening = end_date - timedelta(days=N)
    base = {"rhr": 58, "hrv": 50, "sleep_hours": 7.3, "bedtime": "23:15", "wake_ups": 2, **spec.get("baseline", {})}
    events = spec.get("events", [])
    by_type = {}
    for e in events:
        by_type.setdefault(e["type"], []).append(e)

    def nights_with(kind):
        out = {}
        for e in by_type.get(kind, []):
            for n in _nights(e.get("nights"), N):
                out[n] = e
        return out

    skip, no_hrv, short = nights_with("no_sleep_data"), nights_with("no_hrv"), nights_with("short_sleep")
    bed_ev, no_stage, naps = nights_with("bedtime"), nights_with("no_stages"), nights_with("nap")
    in_bed, few_hr = nights_with("in_bed"), nights_with("few_hr")
    other_hr, other_sleep = nights_with("other_app_hr"), nights_with("other_app_sleep")
    offsets = sorted(((e["from_night"], e["offset"]) for e in by_type.get("utc_offset", [])))

    def offset_for(n: int) -> str:
        off = spec.get("utc_offset", "-0500")
        for start, o in offsets:
            if n >= start:
                off = o
        return off

    def overreach(n: int) -> dict:
        shift = {"hrv": 0.0, "rhr": 0.0, "sleep": 0.0, "wake": 0}
        for e in by_type.get("overreach", []):
            ns = _nights(e.get("nights"), N)
            if n in ns:
                k = (ns.index(n) + 1) / len(ns) if e.get("ramp", True) else 1.0
                shift["hrv"] += e.get("hrv_change_pct", 0) / 100 * k
                shift["rhr"] += e.get("rhr_change_bpm", 0) * k
                shift["sleep"] += e.get("sleep_change_hours", 0) * k
                shift["wake"] += round(e.get("extra_wake_ups", 0) * k)
        return shift

    sc = Scenario(spec)
    recs = sc.records
    truth_nights, sleep_windows = [], []   # sleep_windows: (start_local, end_local, offset, night_rhr_level, hr_every)

    for n in range(1, N + 1):
        evening = first_evening + timedelta(days=n - 1)
        off = offset_for(n)
        row = {"night": n, "night_date": evening.isoformat(), "has_sleep": n not in skip, "offset": off}
        sh = overreach(n)

        if n in naps:
            e = naps[n]; hh, mm = _hhmm(e.get("time", "14:00"))
            ns = datetime.combine(evening, datetime.min.time()).replace(hour=hh, minute=mm)
            recs.append(Record(SLEEP, WATCH, ns, ns + timedelta(minutes=e.get("minutes", 30)), off,
                               "HKCategoryValueSleepAnalysisAsleepCore"))
            row["naps"] = 1
        else:
            row["naps"] = 0

        if n in skip:
            truth_nights.append(row)
            continue

        # Sleep onset (local time). Times before noon mean the next morning.
        hh, mm = _hhmm(bed_ev[n]["time"]) if n in bed_ev else _hhmm(base["bedtime"])
        day = evening + timedelta(days=1) if hh < 12 else evening
        onset = datetime.combine(day, datetime.min.time()).replace(hour=hh, minute=mm) \
            + timedelta(minutes=rng.randint(-20, 20), seconds=rng.randint(0, 59))
        target = (short[n]["hours"] if n in short else base["sleep_hours"] + sh["sleep"] + rng.gauss(0, 0.3)) * 60
        target = max(target, 30)
        wake_ups = max(0, base["wake_ups"] + sh["wake"] + rng.choice([-1, 0, 0, 1]))

        # Build asleep blocks of roughly 90-minute cycles, with awake bouts between some blocks.
        blocks, remaining = [], target
        while remaining > 1:
            cyc = min(remaining, rng.uniform(80, 100)); blocks.append(cyc); remaining -= cyc
        wake_slots = set(rng.sample(range(1, len(blocks)), k=min(wake_ups, max(len(blocks) - 1, 0)))) if len(blocks) > 1 else set()

        t = onset
        # A few minutes awake BEFORE onset (must not count)
        recs.append(Record(SLEEP, WATCH, t - timedelta(minutes=6), t, off, "HKCategoryValueSleepAnalysisAwake"))
        stage_min = {"core": 0.0, "deep": 0.0, "rem": 0.0, "asleep_unspecified": 0.0}
        waso, awakenings = 0.0, 0
        for i, cyc in enumerate(blocks):
            if i in wake_slots:
                aw = timedelta(minutes=rng.randint(2, 12), seconds=rng.randint(0, 59))
                recs.append(Record(SLEEP, WATCH, t, t + aw, off, "HKCategoryValueSleepAnalysisAwake"))
                waso += aw.total_seconds() / 60; awakenings += 1; t += aw
            if n in no_stage:
                pieces = [("AsleepUnspecified", "asleep_unspecified", cyc)]
            else:
                deep = max(0.0, min(cyc * 0.35, rng.gauss(30 - 6 * i, 5)))
                rem = max(5.0, min(cyc * 0.4, rng.gauss(10 + 6 * i, 4)))
                core = max(cyc - deep - rem, 5.0)
                pieces = [("AsleepCore", "core", core * 0.6), ("AsleepDeep", "deep", deep),
                          ("AsleepCore", "core", core * 0.4), ("AsleepREM", "rem", rem)]
            for val, key, mins in pieces:
                if mins < 0.6:
                    continue
                d = timedelta(seconds=round(mins * 60))
                recs.append(Record(SLEEP, WATCH, t, t + d, off, f"HKCategoryValueSleepAnalysis{val}"))
                stage_min[key] += d.total_seconds() / 60; t += d
        wake = t
        # A few minutes awake AFTER final awakening (must not count)
        recs.append(Record(SLEEP, WATCH, wake, wake + timedelta(minutes=9), off, "HKCategoryValueSleepAnalysisAwake"))

        tst = sum(stage_min.values())
        row.update({"onset": onset.isoformat(), "final_wake": wake.isoformat(), "tst_min": tst,
                    "core_min": stage_min["core"], "deep_min": stage_min["deep"], "rem_min": stage_min["rem"],
                    "unspecified_min": stage_min["asleep_unspecified"], "waso_min": waso, "awakenings": awakenings,
                    "window_min": (wake - onset).total_seconds() / 60})

        if n in in_bed:
            ib_s, ib_e = onset - timedelta(minutes=25), wake + timedelta(minutes=12)
            recs.append(Record(SLEEP, PHONE, ib_s, ib_e, off, "HKCategoryValueSleepAnalysisInBed"))
            row.update({"tib_source": "iphone_in_bed", "tib_min": (ib_e - ib_s).total_seconds() / 60})
        else:
            row.update({"tib_source": "sleep_window", "tib_min": (wake - onset).total_seconds() / 60})

        # HRV readings strictly inside the window
        readings = []
        if n not in no_hrv:
            for _ in range(rng.choice([1, 2, 3, 3, 4])):
                when = onset + (wake - onset) * rng.uniform(0.08, 0.92)
                when = when.replace(microsecond=0)
                v = round(base["hrv"] * (1 + sh["hrv"]) * math.exp(rng.gauss(0, 0.15)), 2)
                recs.append(Record(HRV, WATCH, when, when, off, f"{v}", "ms"))
                readings.append(v)
        row.update({"hrv_readings": readings,
                    "hrv_night_ms": (sum(readings) / len(readings)) if readings else None})

        if n in other_sleep:
            recs.append(Record(SLEEP, "AutoSleep", onset - timedelta(minutes=40), wake + timedelta(minutes=30), off,
                               "HKCategoryValueSleepAnalysisAsleepUnspecified"))

        night_rhr = base["rhr"] - 4 + sh["rhr"]
        every = few_hr[n].get("every_minutes", 40) if n in few_hr else None
        sleep_windows.append((onset, wake, off, night_rhr, every, n))
        truth_nights.append(row)

    # Heart rate for every day: every ~5 min awake, sparse when a few_hr night says so.
    def in_sleep(t: datetime):
        for s, e, off, lvl, every, n in sleep_windows:
            if s <= t <= e:
                return lvl, every
        return None

    day0 = first_evening
    for d in range(N + 1):
        day = day0 + timedelta(days=d)
        off = offset_for(max(1, min(N, d + 1)))
        t = datetime.combine(day, datetime.min.time())
        stop = t + timedelta(days=1)
        rest = base["rhr"] + overreach(max(1, min(N, d)))["rhr"] if d else base["rhr"]
        while t < stop:
            s = in_sleep(t)
            if s:
                lvl, every = s
                bpm = lvl + rng.gauss(0, 2)
                step = timedelta(minutes=every) if every else timedelta(minutes=rng.choice([4, 5, 6]))
            else:
                bpm = rest + 14 + 8 * math.sin((t.hour - 9) / 24 * 2 * math.pi) + rng.gauss(0, 6)
                step = timedelta(minutes=rng.choice([4, 5, 6]))
            recs.append(Record(HR, WATCH, t, t, off, str(int(round(max(40, bpm)))), "count/min"))
            t += step + timedelta(seconds=rng.randint(0, 30))
        if d:  # Apple's daily resting HR for this day
            recs.append(Record(RHR, WATCH, datetime.combine(day, datetime.min.time()),
                               datetime.combine(day, datetime.min.time()) + timedelta(hours=23, minutes=59, seconds=59),
                               off, str(int(round(rest))), "count/min"))
        if (d + 1) in other_hr:
            for k in range(6):
                tt = datetime.combine(day, datetime.min.time()).replace(hour=18) + timedelta(minutes=k)
                recs.append(Record(HR, "Polar Beat", tt, tt, off, str(rng.randint(115, 150)), "count/min"))

    # Noise that cleaning must remove (truth is unaffected).
    hr_recs = [r for r in recs if r.rtype == HR and r.source == WATCH]
    for e in by_type.get("duplicates", []):
        for r in rng.sample(hr_recs, k=int(len(hr_recs) * e.get("rate", 0.02))):
            recs.append(Record(r.rtype, r.source, r.start, r.end, r.offset, r.value, r.unit))
    for e in by_type.get("glitches", []):
        for _ in range(int(e.get("count", 5))):
            r = rng.choice(hr_recs)
            recs.append(Record(HR, WATCH, r.start + timedelta(seconds=7), r.start + timedelta(seconds=7), r.offset,
                               str(rng.choice([12, 18, 238, 251])), "count/min"))

    sc.truth = {
        "name": spec["name"],
        "nights": truth_nights,
        "late_hrv_hours": next((e.get("hours", 26) for e in by_type.get("late_hrv_hours", [])), None),
        "noise": {k: len(v) for k, v in by_type.items() if k in ("duplicates", "glitches", "other_app_hr", "other_app_sleep")},
    }
    return sc


def load_spec(path: str | Path) -> dict:
    spec = json.loads(Path(path).read_text())
    if "name" not in spec:
        spec["name"] = Path(path).stem
    return spec
