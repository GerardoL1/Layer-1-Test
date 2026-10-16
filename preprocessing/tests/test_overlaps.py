"""
Overlapping sleep records (two watches, or "asleep" written on top of stages) must not
be counted twice.

    python -m pytest -q tests/test_overlaps.py
"""

from pathlib import Path

import pandas as pd
import pytest

from agent_testing.scenario_builder import build, load_spec
from layer1 import pipeline as P
from layer1.samples import SAMPLES

HERE = Path(__file__).resolve().parent.parent

WATCH = "Sam’s Apple Watch"
HK = {
    "core": "AsleepCore",
    "deep": "AsleepDeep",
    "rem": "AsleepREM",
    "asleep_unspecified": "AsleepUnspecified",
    "awake": "Awake",
    "in_bed": "InBed",
}


def records(pieces, offset="-0500"):
    """Pipeline-style records from (stage, start, end[, source]) with local times like '2026-09-01 23:00'."""
    rows = []
    for p in pieces:
        stage, start, end = p[:3]
        source = p[3] if len(p) > 3 else WATCH
        s = f"{start}:00 {offset}" if len(start) == 16 else f"{start} {offset}"
        e = f"{end}:00 {offset}" if len(end) == 16 else f"{end} {offset}"
        rows.append(("sleep", "sleep_analysis", f"HKCategoryValueSleepAnalysis{HK[stage]}", None, source, s, e))
    df = pd.DataFrame(rows, columns=["kind", "metric", "raw_value", "unit", "source", "start_str", "end_str"])
    for side in ("start", "end"):
        df[f"{side}_utc"] = pd.to_datetime(df[f"{side}_str"], format=P.DATE_FORMAT, utc=True)
        df[f"{side}_local"] = pd.to_datetime(df[f"{side}_str"].str.slice(0, 19))
    df["value"] = float("nan")
    df["stage"] = df["raw_value"].map(lambda v: next(k for k, h in HK.items() if v.endswith(h)))
    return df.drop(columns=["start_str", "end_str"])


def night(pieces):
    cleaned, _, _ = P.clean(records(pieces))
    sessions, stages = P.find_sleep_windows(cleaned["sleep_stages"])
    return P.nightly_metrics(sessions, stages, cleaned).iloc[0]


BASE = [
    ("core", "2026-09-01 23:00", "2026-09-02 02:00"),
    ("deep", "2026-09-02 02:00", "2026-09-02 03:00"),
    ("awake", "2026-09-02 03:00", "2026-09-02 03:10"),
    ("rem", "2026-09-02 03:10", "2026-09-02 06:00"),
]


def test_unspecified_on_top_of_core_does_not_change_tst():
    plain = night(BASE)
    doubled = night(BASE + [("asleep_unspecified", "2026-09-01 23:30", "2026-09-02 01:30")])
    assert plain["tst_min"] == pytest.approx(410)
    assert doubled["tst_min"] == pytest.approx(plain["tst_min"])
    assert doubled["core_min"] == pytest.approx(180) and doubled["unspecified_min"] == pytest.approx(0)
    assert doubled["sleep_efficiency_pct"] <= 100


def test_second_watch_recording_the_same_night():
    twice = night(BASE + [(s, a, b, "Sam’s second Apple Watch") for s, a, b in BASE])
    assert twice["tst_min"] == pytest.approx(410)
    assert twice["awakenings"] == 1 and twice["waso_min"] == pytest.approx(10)


def test_overlapping_specific_stages_go_to_the_one_that_started_first():
    n = night([("core", "2026-09-01 23:00", "2026-09-02 01:00"), ("deep", "2026-09-02 00:30", "2026-09-02 02:00")])
    assert n["core_min"] == pytest.approx(120)  # core started first, keeps 23:00-01:00
    assert n["deep_min"] == pytest.approx(60)  # deep keeps only 01:00-02:00
    assert n["tst_min"] == pytest.approx(180)


def test_asleep_beats_awake_under_it():
    n = night([("core", "2026-09-01 23:00", "2026-09-02 05:00"), ("awake", "2026-09-02 02:00", "2026-09-02 02:10")])
    assert n["tst_min"] == pytest.approx(360)
    assert n["awakenings"] == 0 and n["waso_min"] == pytest.approx(0)


def test_split_pieces_keep_their_local_times():
    st = P.resolve_overlaps(
        P.clean(
            records(
                [
                    ("asleep_unspecified", "2026-09-01 23:00", "2026-09-02 01:00"),
                    ("core", "2026-09-02 00:00", "2026-09-02 00:30"),
                ]
            )
        )[0]["sleep_stages"]
    )
    got = [(r.stage, str(r.start_local), str(r.end_local)) for r in st.sort_values("start_utc").itertuples()]
    assert got == [
        ("asleep_unspecified", "2026-09-01 23:00:00", "2026-09-02 00:00:00"),
        ("core", "2026-09-02 00:00:00", "2026-09-02 00:30:00"),
        ("asleep_unspecified", "2026-09-02 00:30:00", "2026-09-02 01:00:00"),
    ]


def test_split_pieces_keep_true_local_times_across_a_clock_change():
    # London falls back at 01:00 UTC on 25 Oct 2026. A second watch's deep piece (01:30 BST to
    # 01:20 GMT) sits inside an unspecified piece that runs from 23:00 BST to 07:00 GMT.
    df = records(
        [
            ("asleep_unspecified", "2026-10-24 23:00", "2026-10-25 07:00"),
            ("deep", "2026-10-25 01:30", "2026-10-25 01:20", "Sam’s Apple Watch 2"),
        ],
        offset="+0100",
    )
    df["end_utc"] = df["end_local"].dt.tz_localize("UTC")  # both pieces end after the change (+0000)
    st = P.resolve_overlaps(P.clean(df)[0]["sleep_stages"])
    got = [(r.stage, str(r.start_local), str(r.end_local)) for r in st.sort_values("start_utc").itertuples()]
    assert got == [
        ("asleep_unspecified", "2026-10-24 23:00:00", "2026-10-25 01:30:00"),
        ("deep", "2026-10-25 01:30:00", "2026-10-25 01:20:00"),
        ("asleep_unspecified", "2026-10-25 01:20:00", "2026-10-25 07:00:00"),
    ]


def test_no_overlap_is_left_untouched():
    st = P.clean(records(BASE))[0]["sleep_stages"]
    assert P.resolve_overlaps(st) is st


def _check_bounds(nights, where):
    has = nights.dropna(subset=["tst_min"])
    over_window = has[has["tst_min"] > has["sleep_window_min"] + 1e-9]
    over_100 = has[has["sleep_efficiency_pct"] > 100 + 1e-9]
    assert over_window.empty, f"{where}: tst over the sleep window on {list(over_window['night_date'])}"
    assert over_100.empty, f"{where}: efficiency over 100% on {list(over_100['night_date'])}"


@pytest.mark.parametrize("person", list(SAMPLES))
def test_sample_nights_stay_within_bounds(person):
    _check_bounds(P.run_pipeline(HERE / "sample_data" / SAMPLES[person], person, days=None).nights, person)


SCENARIOS = sorted((HERE / "agent_testing" / "scenarios").glob("*.json"))


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario_nights_stay_within_bounds(path, tmp_path):
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(build(load_spec(path)).export_zip())
    _check_bounds(P.run_pipeline(zip_path, path.stem, days=None).nights, path.stem)
