"""
Makes fake Apple Health exports (export.zip) that look like the real thing,
so the team can test the dashboard and Layer 1 math without a real watch.

    python mock/make_mock_export.py                 # all three testers, last 30 days
    python mock/make_mock_export.py --days 60 --profile alex

Each profile tells a different story:
  steady  (sam)    good sleep, stable HRV and resting HR
  overreach (alex) normal for 3 weeks, then a hard training block with short,
                   broken sleep: HRV drops, resting HR rises
  messy   (jordan) real-world gaps: missed nights, days with no HRV,
                   iPhone "In Bed" records, a watch that sometimes isn't worn,
                   plus noise to clean: duplicate records, sensor glitches,
                   heart rate / sleep written by other apps, and afternoon naps
"""
import argparse
import math
import random
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Los_Angeles")
WATCH = "{name}’s Apple Watch"  # Apple uses a curly apostrophe
PHONE = "{name}’s iPhone"


@dataclass
class Profile:
    name: str
    rhr: float            # baseline resting heart rate (bpm)
    hrv: float            # baseline overnight SDNN (ms)
    sleep_hours: float    # typical time asleep
    bedtime: float        # typical sleep onset, hours after midnight-of-evening (23.0 = 11pm)
    workouts_per_week: int
    seed: int


PROFILES = {
    "steady": Profile("Sam", rhr=56, hrv=58, sleep_hours=7.6, bedtime=22.9, workouts_per_week=4, seed=11),
    "overreach": Profile("Alex", rhr=60, hrv=47, sleep_hours=7.2, bedtime=23.2, workouts_per_week=5, seed=22),
    "messy": Profile("Jordan", rhr=63, hrv=39, sleep_hours=6.8, bedtime=23.7, workouts_per_week=3, seed=33),
}


def fmt(dt: datetime) -> str:
    return dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S %z")


def record(rtype, source, start, end, value, unit=None) -> str:
    unit_attr = f' unit="{unit}"' if unit else ""
    return (f'<Record type="{rtype}" sourceName="{source}" sourceVersion="12.0"{unit_attr} '
            f'creationDate="{fmt(end)}" startDate="{fmt(start)}" endDate="{fmt(end)}" value="{value}"/>')


def day_state(profile_key: str, day_index: int, total_days: int, rng: random.Random) -> dict:
    """How 'recovered' this person is on a given day; drives HRV, RHR and sleep."""
    days_left = total_days - day_index
    state = {"hrv_shift": 0.0, "rhr_shift": 0.0, "sleep_shift": 0.0, "wake_ups": 2,
             "extra_workout": False, "skip_night": False, "no_hrv": False}

    if profile_key == "overreach" and days_left <= 9:
        # Hard block: gets steadily worse over the last 9 days.
        severity = (10 - days_left) / 9
        state.update(hrv_shift=-0.35 * severity, rhr_shift=7 * severity,
                     sleep_shift=-1.3 * severity, wake_ups=2 + round(4 * severity),
                     extra_workout=True)
    if profile_key == "messy":
        state["skip_night"] = rng.random() < 0.15
        state["no_hrv"] = rng.random() < 0.25
        state["wake_ups"] = rng.choice([2, 3, 4, 5])
    return state


def sleep_night(p: Profile, night: date, st: dict, rng: random.Random, records: list):
    """Builds one night of sleep stages in ~90-minute cycles. Returns (onset, wake)."""
    onset = datetime.combine(night, time(0), TZ) + timedelta(hours=p.bedtime + rng.gauss(0, 0.5))
    target = max(4.0, p.sleep_hours + st["sleep_shift"] + rng.gauss(0, 0.45)) * 60  # minutes asleep
    src = WATCH.format(name=p.name)

    t, asleep, cycle = onset, 0.0, 0
    wake_slots = set(rng.sample(range(1, 7), k=min(st["wake_ups"], 6)))
    while asleep < target:
        cycle += 1
        # Early cycles are deep-heavy; later cycles are REM-heavy (as in real sleep).
        deep = max(0, rng.gauss(32 - 7 * cycle, 6))
        rem = max(5, rng.gauss(8 + 5 * cycle, 4))
        core = max(20, rng.gauss(50, 10))
        for stage, mins in (("AsleepCore", core * 0.6), ("AsleepDeep", deep), ("AsleepCore", core * 0.4), ("AsleepREM", rem)):
            if mins < 1 or asleep >= target:
                continue
            mins = min(mins, target - asleep)
            end = t + timedelta(minutes=mins)
            records.append(record("HKCategoryTypeIdentifierSleepAnalysis", src, t, end,
                                  f"HKCategoryValueSleepAnalysis{stage}"))
            t, asleep = end, asleep + mins
        if cycle in wake_slots:
            awake = max(1, rng.gauss(6, 4))
            end = t + timedelta(minutes=awake)
            records.append(record("HKCategoryTypeIdentifierSleepAnalysis", src, t, end,
                                  "HKCategoryValueSleepAnalysisAwake"))
            t = end
    return onset, t


def heart_rate_day(p, day_start, day_end, sleep_windows, workouts, st, rng, records):
    """Heart rate every few minutes, lower at night, near-continuous during workouts."""
    src = WATCH.format(name=p.name)
    rhr = p.rhr + st["rhr_shift"]
    t = day_start
    while t < day_end:
        hour = t.hour + t.minute / 60
        in_sleep = any(s <= t < e for s, e in sleep_windows)
        workout = next(((s, e) for s, e in workouts if s <= t < e), None)
        if workout:
            s, e = workout
            frac = (t - s) / (e - s)
            bpm = rhr + 60 + 45 * math.sin(math.pi * frac) + rng.gauss(0, 6)
            step = timedelta(seconds=rng.choice([5, 6, 7]))
        elif in_sleep:
            bpm = rhr - 4 + rng.gauss(0, 2.5)
            step = timedelta(minutes=rng.choice([5, 8, 10]))
        else:
            daytime = 14 + 8 * math.sin((hour - 9) / 24 * 2 * math.pi)
            bpm = rhr + daytime + rng.gauss(0, 7)
            step = timedelta(minutes=rng.choice([3, 4, 5, 6]))
        records.append(record("HKQuantityTypeIdentifierHeartRate", src, t, t, round(max(40, bpm)), "count/min"))
        t += step


def add_noise(p: Profile, day_start: datetime, records: list, rng: random.Random):
    """Things real exports contain that preprocessing has to remove."""
    hr_lines = [r for r in records[-400:] if "HKQuantityTypeIdentifierHeartRate\"" in r]
    # Exact duplicates (sync glitches, re-imports).
    for line in rng.sample(hr_lines, k=min(len(hr_lines), rng.randint(2, 6))):
        records.append(line)
    # Sensor glitches: impossible heart rates from a loose strap.
    if rng.random() < 0.4:
        when = day_start + timedelta(hours=rng.uniform(8, 20))
        records.append(record("HKQuantityTypeIdentifierHeartRate", WATCH.format(name=p.name), when, when,
                              rng.choice([12, 18, 238, 251]), "count/min"))
    # Heart rate from another app (a chest strap app), which we exclude to keep one sensor.
    if rng.random() < 0.3:
        when = day_start + timedelta(hours=rng.uniform(17, 19))
        for k in range(5):
            t = when + timedelta(minutes=k)
            records.append(record("HKQuantityTypeIdentifierHeartRate", "Polar Beat", t, t,
                                  rng.randint(110, 150), "count/min"))
    # An afternoon nap picked up by the watch (preprocessing should ignore it).
    if rng.random() < 0.15:
        start = day_start + timedelta(hours=rng.uniform(13.5, 15.5))
        end = start + timedelta(minutes=rng.randint(20, 45))
        records.append(record("HKCategoryTypeIdentifierSleepAnalysis", WATCH.format(name=p.name), start, end,
                              "HKCategoryValueSleepAnalysisAsleepCore"))
    # A third-party sleep app writing its own "asleep" estimate over the same night.
    if rng.random() < 0.25:
        start = day_start - timedelta(hours=rng.uniform(0.5, 1.5))
        records.append(record("HKCategoryTypeIdentifierSleepAnalysis", "AutoSleep", start,
                              start + timedelta(hours=rng.uniform(6, 8)),
                              "HKCategoryValueSleepAnalysisAsleepUnspecified"))


def build(profile_key: str, days: int, end_day: date) -> tuple[str, dict]:
    p = PROFILES[profile_key]
    rng = random.Random(p.seed)
    records: list[str] = []
    stats = {"nights": 0, "hrv": 0, "workouts": 0}
    first_day = end_day - timedelta(days=days - 1)
    hr_days, all_sleep = [], []  # heart rate is generated after all sleep, so late-evening
                                 # readings know that tonight's sleep has already started

    for i in range(days):
        day = first_day + timedelta(days=i)
        st = day_state(profile_key, i + 1, days, rng)
        day_start = datetime.combine(day, time(0), TZ)
        day_end = day_start + timedelta(days=1)

        # Last night's sleep (the night that ends this morning).
        sleep_windows = []
        if not st["skip_night"]:
            onset, wake = sleep_night(p, day - timedelta(days=1), st, rng, records)
            sleep_windows.append((onset, wake))
            stats["nights"] += 1
            if profile_key == "messy":
                # iPhone Sleep Schedule writes "In Bed" from bedtime to alarm.
                records.append(record("HKCategoryTypeIdentifierSleepAnalysis", PHONE.format(name=p.name),
                                      onset - timedelta(minutes=20), wake + timedelta(minutes=10),
                                      "HKCategoryValueSleepAnalysisInBed"))

            # HRV: a few readings during the night.
            if not st["no_hrv"]:
                for _ in range(rng.choice([1, 2, 3, 3, 4])):
                    when = onset + (wake - onset) * rng.uniform(0.1, 0.9)
                    value = p.hrv * (1 + st["hrv_shift"]) * math.exp(rng.gauss(0, 0.18))
                    records.append(record("HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
                                          WATCH.format(name=p.name), when, when, round(value, 2), "ms"))
                    stats["hrv"] += 1

            # Resting heart rate: one value per day.
            rhr = p.rhr + st["rhr_shift"] + rng.gauss(0, 1.2)
            records.append(record("HKQuantityTypeIdentifierRestingHeartRate", WATCH.format(name=p.name),
                                  day_start, day_end - timedelta(seconds=1), round(rhr), "count/min"))

        # Workouts in the late afternoon.
        workouts = []
        if rng.random() < p.workouts_per_week / 7 or st["extra_workout"]:
            start = day_start + timedelta(hours=17 + rng.uniform(0, 2))
            workouts.append((start, start + timedelta(minutes=rng.choice([45, 60, 75]))))
            stats["workouts"] += 1

        # Daytime watch wear: the messy tester sometimes doesn't wear it in the afternoon.
        wear_end = day_end if not (profile_key == "messy" and rng.random() < 0.2) else day_start + timedelta(hours=13)
        hr_days.append((day_start, wear_end, workouts, st))
        all_sleep.extend(sleep_windows)

        # Some data the importer should ignore (real exports are full of this).
        records.append(record("HKQuantityTypeIdentifierStepCount", PHONE.format(name=p.name),
                              day_start + timedelta(hours=12), day_start + timedelta(hours=13),
                              rng.randint(800, 3000), "count"))

    for day_start, wear_end, workouts, st in hr_days:
        heart_rate_day(p, day_start, wear_end, all_sleep, workouts, st, rng, records)
        if profile_key == "messy":
            add_noise(p, day_start, records, rng)

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<!DOCTYPE HealthData [\n<!ELEMENT HealthData (ExportDate,Me,(Record|Correlation|Workout|ActivitySummary)*)>\n]>\n'
           f'<HealthData locale="en_US">\n<ExportDate value="{fmt(datetime.now(TZ))}"/>\n'
           '<Me HKCharacteristicTypeIdentifierDateOfBirth="" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexNotSet"/>\n'
           + "\n".join(records) + "\n</HealthData>\n")
    stats["records"] = len(records)
    return xml, stats


def main():
    parser = argparse.ArgumentParser(description="Make mock Apple Health exports.")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--profile", choices=list(PROFILES), help="only build one profile")
    parser.add_argument("--end", help="last day of data, YYYY-MM-DD (default: today)")
    parser.add_argument("--out", default="mock_exports", help="output folder")
    args = parser.parse_args()

    end_day = date.fromisoformat(args.end) if args.end else datetime.now(TZ).date()
    out = Path(args.out)
    out.mkdir(exist_ok=True)

    for key in [args.profile] if args.profile else PROFILES:
        xml, stats = build(key, args.days, end_day)
        name = PROFILES[key].name.lower()
        path = out / f"mock_export_{name}_{key}.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("apple_health_export/export.xml", xml)
        print(f"{path}  ({stats['records']} records, {stats['nights']} nights, "
              f"{stats['hrv']} HRV readings, {stats['workouts']} workouts)")


if __name__ == "__main__":
    main()
