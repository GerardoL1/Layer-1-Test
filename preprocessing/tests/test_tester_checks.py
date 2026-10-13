"""
The Layer 1 tester must fail, not warn, when a scenario's expectation can't be checked,
so a broken scenario can't hide inside an "ALL PASSED" report.

    python -m pytest -q tests/test_tester_checks.py
"""
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "agent_testing"))
from checks import expectation_checks  # noqa: E402

TRUTH = {"nights": [{"night_date": "2026-09-01"}, {"night_date": "2026-09-02"}]}
NIGHTS = pd.DataFrame({"night_date": ["2026-09-01", "2026-09-02"], "tst_min": [400.0, 420.0]})


def test_unknown_expectation_type_fails():
    [r] = expectation_checks([{"type": "no_such_check", "nights": [1]}], TRUTH, NIGHTS)
    assert r.status == "fail" and "unknown expectation type" in r.detail


def test_expectation_that_crashes_fails():
    [r] = expectation_checks([{"type": "value", "column": "not_a_column", "nights": [1], "equals": 1}], TRUTH, NIGHTS)
    assert r.status == "fail" and "could not evaluate" in r.detail


def test_good_expectation_still_passes():
    [r] = expectation_checks([{"type": "value", "column": "tst_min", "nights": [2], "between": [400, 450]}], TRUTH, NIGHTS)
    assert r.status == "pass"


def test_runner_exits_non_zero_on_a_bad_expectation(tmp_path):
    spec = {"name": "bad_expectation", "description": "Has an expectation the tester doesn't know.",
            "nights": 8, "seed": 7, "expect": [{"type": "rows", "equals": 8}, {"type": "made_up_check"}]}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    run = subprocess.run([sys.executable, str(HERE / "agent_testing" / "run_layer1_tests.py"), "--skip-unit",
                          "--skip-daily", "--scenarios", str(path), "--out", str(tmp_path / "reports")],
                         cwd=HERE, capture_output=True, text=True, encoding="utf-8")
    assert run.returncode == 1, run.stdout + run.stderr
    report = next((tmp_path / "reports").glob("*.md")).read_text(encoding="utf-8")
    assert "ALL PASSED" not in report and "1 FAILED" in report
