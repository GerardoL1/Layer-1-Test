"""
    cd preprocessing
    python -m pytest -q

Two kinds of test:
  * small hand-built exports where the right answer is known exactly
  * the three sample files must still produce the saved outputs in expected/
    (if you change the preprocessing on purpose, refresh them with
     `python run_pipeline.py --save-expected` and commit the new CSVs)
"""
import io
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
import config as C  # noqa: E402
import pipeline as P  # noqa: E402

WATCH = "Test’s Apple Watch"
TZ = "-0500"


# ---------------------------------------------------------------- helpers to build tiny exports

def rec(rtype, start, end=None, value=None, source=WATCH, unit=None):
    end = end or start
    v = f' value="{value}"' if value is not None else ""
    u = f' unit="{unit}"' if unit else ""
    return (f'<Record type="{rtype}" sourceName="{source}"{u} '
            f'startDate="{start} {TZ}" endDate="{end} {TZ}"{v}/>')


def hr(t, bpm, source=WATCH):
    return rec("HKQuantityTypeIdentifierHeartRate", t, value=bpm, source=source, unit="count/min")


def hrv(t, ms):
    return rec("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", t, value=ms, unit="ms")


def sleep(start, end, stage, source=WATCH):
    return rec(C.SLEEP_TYPE, start, end, value=f"HKCategoryValueSleepAnalysis{stage}", source=source)


def export(*records) -> io.BytesIO:
    xml = "<?xml version='1.0'?>\n<HealthData>" + "".join(records) + "</HealthData>"
    buf = io.BytesIO(xml.encode())
    buf.name = "export.xml"
    return buf


def night(date_evening, date_morning, extra=()):
    """A simple night: 23:00-03:00 core, 03:00-03:10 awake, 03:10-06:00 deep."""
    return [
        sleep(f"{date_evening} 23:00:00", f"{date_morning} 03:00:00", "AsleepCore"),
        sleep(f"{date_morning} 03:00:00", f"{date_morning} 03:10:00", "Awake"),
        sleep(f"{date_morning} 03:10:00", f"{date_morning} 06:00:00", "AsleepDeep"),
        *extra,
    ]


# ---------------------------------------------------------------- 1-2. load and clean

def test_load_keeps_only_layer1_types():
    src = export(hr("2026-09-01 10:00:00", 70),
                 rec("HKQuantityTypeIdentifierStepCount", "2026-09-01 10:00:00", value=100, unit="count"))
    records, counts = P.load_export(src, days=None)
    assert list(records["metric"]) == ["heart_rate"]
    assert set(counts["type"]) == {"HKQuantityTypeIdentifierHeartRate", "HKQuantityTypeIdentifierStepCount"}


def test_local_and_utc_times():
    records, _ = P.load_export(export(hr("2026-09-01 23:30:00", 70)), days=None)
    assert records["start_local"][0] == pd.Timestamp("2026-09-01 23:30:00")
    assert records["start_utc"][0] == pd.Timestamp("2026-09-02 04:30:00", tz="UTC")


def test_clean_rules():
    src = export(hr("2026-09-01 10:00:00", 70), hr("2026-09-01 10:00:00", 70),        # duplicate
                 hr("2026-09-01 10:05:00", 250), hr("2026-09-01 10:06:00", 12),       # impossible
                 hr("2026-09-01 10:07:00", 120, source="Polar Beat"),                 # other app
                 sleep("2026-09-01 22:00:00", "2026-09-02 07:00:00", "InBed", source="Test’s iPhone"))
    records, _ = P.load_export(src, days=None)
    cleaned, log, removed = P.clean(records)
    assert list(cleaned["heart_rate"]["value"]) == [70]
    assert len(cleaned["in_bed"]) == 1                       # iPhone In Bed is kept
    assert set(log["reason"]) == {"Exact duplicate", "Value outside plausible range",
                                  "Not recorded by the Apple Watch"}
    assert len(removed) == 4


def test_zip_without_export_xml_is_a_clear_error(tmp_path):
    z = tmp_path / "wrong.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("notes.txt", "hello")
    with pytest.raises(ValueError, match="No export.xml"):
        P.load_export(z)


# ---------------------------------------------------------------- 3. sleep window

def test_night_label_and_trimmed_window():
    stages = [sleep("2026-09-01 22:50:00", "2026-09-01 23:00:00", "Awake"),   # awake before onset
              *night("2026-09-01", "2026-09-02"),
              sleep("2026-09-02 06:00:00", "2026-09-02 06:20:00", "Awake")]   # awake after final wake
    r = P.run_pipeline(export(*stages), days=None)
    row = r.nights.iloc[0]
    assert str(row["night_date"]) == "2026-09-01"
    assert row["sleep_onset"] == pd.Timestamp("2026-09-01 23:00:00")
    assert row["final_wake"] == pd.Timestamp("2026-09-02 06:00:00")
    assert row["tst_min"] == pytest.approx(240 + 170)
    assert row["waso_min"] == pytest.approx(10)
    assert row["awakenings"] == 1


def test_sleep_starting_after_midnight_belongs_to_previous_evening():
    r = P.run_pipeline(export(sleep("2026-09-02 01:30:00", "2026-09-02 07:00:00", "AsleepCore")), days=None)
    assert str(r.nights.iloc[0]["night_date"]) == "2026-09-01"


def test_nap_is_ignored():
    stages = [sleep("2026-09-01 14:00:00", "2026-09-01 14:30:00", "AsleepCore"),  # nap, same night label
              *night("2026-09-01", "2026-09-02")]
    r = P.run_pipeline(export(*stages), days=None)
    assert r.sessions["is_main"].sum() == 1 and len(r.sessions) == 2
    assert r.nights.iloc[0]["tst_min"] == pytest.approx(410)
    assert r.nights.iloc[0]["naps"] == 1


def test_touching_awake_pieces_count_as_one_awakening():
    stages = [sleep("2026-09-01 23:00:00", "2026-09-02 02:00:00", "AsleepCore"),
              sleep("2026-09-02 02:00:00", "2026-09-02 02:03:00", "Awake"),
              sleep("2026-09-02 02:03:00", "2026-09-02 02:06:00", "Awake"),
              sleep("2026-09-02 02:06:00", "2026-09-02 06:00:00", "AsleepREM")]
    row = P.run_pipeline(export(*stages), days=None).nights.iloc[0]
    assert row["awakenings"] == 1 and row["waso_min"] == pytest.approx(6)


# ---------------------------------------------------------------- 4. nightly metrics

def test_time_in_bed_uses_iphone_when_present():
    stages = [*night("2026-09-01", "2026-09-02"),
              sleep("2026-09-01 22:30:00", "2026-09-02 06:30:00", "InBed", source="Test’s iPhone")]
    row = P.run_pipeline(export(*stages), days=None).nights.iloc[0]
    assert row["tib_source"] == "iphone_in_bed"
    assert row["tib_min"] == pytest.approx(480)
    assert row["sleep_latency_min"] == pytest.approx(30)
    assert row["sleep_efficiency_pct"] == pytest.approx(410 / 480 * 100)


def test_time_in_bed_falls_back_to_sleep_window():
    row = P.run_pipeline(export(*night("2026-09-01", "2026-09-02")), days=None).nights.iloc[0]
    assert row["tib_source"] == "sleep_window" and row["tib_min"] == pytest.approx(420)
    assert row["fragmentation_per_hr"] == pytest.approx(1 / (410 / 60))


def test_overnight_rhr_is_lowest_30_minute_average():
    readings = []
    # Every 5 minutes from 23:00 to 05:55 at 60 bpm, except 02:00-02:30 at 50 bpm.
    t = pd.Timestamp("2026-09-01 23:00:00")
    while t < pd.Timestamp("2026-09-02 06:00:00"):
        bpm = 50 if pd.Timestamp("2026-09-02 02:00:00") <= t < pd.Timestamp("2026-09-02 02:30:00") else 60
        readings.append(hr(t.strftime("%Y-%m-%d %H:%M:%S"), bpm))
        t += pd.Timedelta(minutes=5)
    row = P.run_pipeline(export(*night("2026-09-01", "2026-09-02"), *readings), days=None).nights.iloc[0]
    assert row["rhr_night_bpm"] == pytest.approx(50, abs=1.5)
    assert row["hr_night_count"] == 84          # 23:00 to 05:55, every 5 minutes


def test_hrv_only_counts_readings_inside_window():
    extra = [hrv("2026-09-01 20:00:00", 99), hrv("2026-09-02 01:00:00", 40), hrv("2026-09-02 04:00:00", 60)]
    row = P.run_pipeline(export(*night("2026-09-01", "2026-09-02"), *extra), days=None).nights.iloc[0]
    assert row["hrv_count"] == 2 and row["hrv_night_ms"] == pytest.approx(50)
    assert row["hrv_ln"] == pytest.approx(np.log(50))


# ---------------------------------------------------------------- 5-6. quality and baselines

def test_missing_night_gets_a_flagged_row():
    stages = night("2026-09-01", "2026-09-02") + night("2026-09-03", "2026-09-04")
    nights = P.run_pipeline(export(*stages), days=None).nights
    gap = nights[nights["night_date"].astype(str) == "2026-09-02"].iloc[0]
    assert gap["flag_no_sleep_data"] and not gap["usable_sleep"]


def test_baseline_needs_minimum_nights_and_excludes_tonight():
    days = pd.date_range("2026-09-01", periods=C.BASELINE_MIN_NIGHTS + 2, freq="D")
    recs = []
    for i, d in enumerate(days):
        e, m = d.strftime("%Y-%m-%d"), (d + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        recs += night(e, m)
        recs.append(hrv(f"{m} 02:00:00", 100 if i == len(days) - 1 else 50 + (i % 2) * 2))
    nights = P.run_pipeline(export(*recs), days=None).nights
    assert nights["z_hrv"].iloc[: C.BASELINE_MIN_NIGHTS].isna().all()      # still building baseline
    assert nights["hrv_ln_base_n"].iloc[-1] == len(days) - 1                 # tonight not included
    assert nights["z_hrv"].iloc[-1] > 5                                       # big jump stands out


def test_file_with_no_sleep_still_runs():
    r = P.run_pipeline(export(hr("2026-09-01 10:00:00", 70), hr("2026-09-03 10:00:00", 72)), days=None)
    assert r.notes and r.nights["flag_no_sleep_data"].all()


# ---------------------------------------------------------------- 7. output format and saved results

def test_ml_table_columns_and_empty_label():
    ml = P.run_pipeline(export(*night("2026-09-01", "2026-09-02")), "t", days=None).ml_table
    assert list(ml.columns) == list(P.ML_COLUMNS)
    assert ml["readiness_label"].isna().all() and (ml["person_id"] == "t").all()


@pytest.mark.parametrize("person", ["sam", "alex", "jordan"])
def test_sample_files_match_expected(person):
    from run_pipeline import SAMPLES
    got = P.run_pipeline(HERE / "sample_data" / SAMPLES[person], person, days=None).ml_table
    buf = io.StringIO()
    got.to_csv(buf, index=False)
    got = pd.read_csv(io.StringIO(buf.getvalue()))
    want = pd.read_csv(HERE / "expected" / f"{person}_features.csv")
    pd.testing.assert_frame_equal(got, want, check_exact=False, rtol=1e-6)


def test_alex_story_comes_through():
    from run_pipeline import SAMPLES
    ml = P.run_pipeline(HERE / "sample_data" / SAMPLES["alex"], "alex", days=None).ml_table
    last = ml.tail(5)
    assert last["z_hrv"].mean() < -1 and last["z_rhr"].mean() > 1 and last["z_tst"].mean() < -1
