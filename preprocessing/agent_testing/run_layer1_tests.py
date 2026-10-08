"""
Run the Layer 1 test suite and write a report.

    cd preprocessing
    python agent_testing/run_layer1_tests.py                      # unit tests + every scenario
    python agent_testing/run_layer1_tests.py --scenarios agent_testing/scenarios/night_shift.json
    python agent_testing/run_layer1_tests.py --skip-unit --skip-daily   # quick run

For each scenario:
  1. build the fake export and its exact truth          (scenario_builder.py)
  2. run the real preprocessing on it                    (pipeline.py)
  3. compare with the truth, the spec formulas, an independent z-score calculation,
     and the scenario's own expectations                  (checks.py)
  4. replay it day by day and confirm the daily updates match  (incremental.py)

Writes agent_testing/reports/layer1_report_<time>.md and .json. Exit code 1 if anything failed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time as clock
from datetime import datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

import pandas as pd  # noqa: E402

import config as C  # noqa: E402
import incremental as I  # noqa: E402
import pipeline as P  # noqa: E402
from checks import Result, expectation_checks, spec_checks, truth_checks, zscore_oracle  # noqa: E402
from scenario_builder import build, load_spec  # noqa: E402


def run_unit_tests() -> Result:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", str(ROOT / "tests")], cwd=ROOT,
                          capture_output=True, text=True)
    last = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
    return Result("Existing unit tests (pytest)", "pass" if proc.returncode == 0 else "fail",
                  last if proc.returncode == 0 else proc.stdout[-1500:])


def daily_check(zip_path: Path, name: str, late_hours) -> Result:
    recs, _ = P.load_export(zip_path, days=None)
    arrive = recs["end_local"].copy()
    if late_hours:
        hrv = recs["metric"] == "hrv_sdnn"
        arrive[hrv] = arrive[hrv] + pd.Timedelta(hours=late_hours)
    first_day = recs["start_local"].min().date()
    last_day = recs["end_local"].max().date() + timedelta(days=1)
    span = (last_day - first_day).days
    proc = I.DailyProcessor(name)
    prev, sync = None, datetime.combine(first_day + timedelta(days=max(span // 2, 1)), time(C.SIM_SYNC_HOUR))
    problems, runs = [], 0
    while sync.date() <= last_day:
        m = (arrive <= sync) if prev is None else ((arrive > prev) & (arrive <= sync))
        rep = proc.sync(recs[m], sync); runs += 1
        if rep.ready_through:
            diff = I.compare(proc.ml_table, I.full_reprocessing(recs[arrive <= sync], name, rep.ready_through))
            if len(diff):
                problems.append(f"run {runs} ({sync:%b %d}): {len(diff)} differences, e.g. "
                                + "; ".join(f"{r.night} {r.column}" for r in diff.head(3).itertuples()))
        prev, sync = sync, sync + timedelta(days=1)
    label = "Daily updates equal full reprocessing" + (f" (HRV {late_hours} h late)" if late_hours else "")
    return Result(label, "fail" if problems else "pass", "; ".join(problems[:5]) or f"{runs} daily runs")


def run_scenario(spec_path: Path, build_dir: Path, skip_daily: bool) -> dict:
    spec = load_spec(spec_path)
    t0 = clock.time()
    results = []
    try:
        sc = build(spec)
        zip_path = sc.save(build_dir)
        r = P.run_pipeline(zip_path, spec["name"], days=None)
        nights, ml = r.nights, r.ml_table
        results += truth_checks(sc, nights)
        results += spec_checks(nights, ml)
        results += zscore_oracle(nights)
        noise = sc.truth["noise"]
        if noise:
            removed = r.removal_log.groupby("reason")["removed"].sum().to_dict() if len(r.removal_log) else {}
            results.append(Result("Cleaning removed the injected noise", "pass" if removed else "fail",
                                  ", ".join(f"{k}: {v}" for k, v in removed.items()) or "nothing removed"))
        results += expectation_checks(spec.get("expect", []), sc.truth, nights)
        if not skip_daily:
            results.append(daily_check(zip_path, spec["name"], sc.truth.get("late_hrv_hours")))
    except Exception as ex:
        import traceback
        results.append(Result("Scenario ran without crashing", "fail", f"{type(ex).__name__}: {ex}\n"
                               + traceback.format_exc()[-1200:]))
    return {"scenario": spec["name"], "description": spec.get("description", ""), "file": str(spec_path),
            "seconds": round(clock.time() - t0, 1), "results": [r.__dict__ for r in results]}


def write_report(unit: Result | None, scenarios: list[dict], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fails = sum(r["status"] == "fail" for s in scenarios for r in s["results"]) + (unit is not None and unit.status == "fail")
    total = sum(len(s["results"]) for s in scenarios) + (unit is not None)
    lines = [f"# Layer 1 test report ({datetime.now():%Y-%m-%d %H:%M})", "",
             f"**{'ALL PASSED' if not fails else f'{fails} FAILED'}**: {total - fails} of {total} checks passed "
             f"across {len(scenarios)} scenarios.", ""]
    if unit:
        lines += [f"- Unit tests: **{unit.status}** ({unit.detail.splitlines()[-1] if unit.detail else ''})", ""]
    lines += ["| Scenario | Checks | Failed | Warnings | Time |", "|---|---|---|---|---|"]
    for s in scenarios:
        f = sum(r["status"] == "fail" for r in s["results"]); w = sum(r["status"] == "warn" for r in s["results"])
        lines.append(f"| {s['scenario']} | {len(s['results'])} | {f} | {w} | {s['seconds']}s |")
    for s in scenarios:
        lines += ["", f"## {s['scenario']}", "", s["description"], ""]
        for r in s["results"]:
            mark = {"pass": "✅", "fail": "❌", "warn": "⚠️"}[r["status"]]
            lines.append(f"- {mark} {r['check']}" + (f": {r['detail']}" if r["detail"] and r["status"] != "pass" else ""))
    md = out_dir / f"layer1_report_{stamp}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out_dir / f"layer1_report_{stamp}.json").write_text(
        json.dumps({"unit": unit.__dict__ if unit else None, "scenarios": scenarios}, indent=1, default=str), encoding="utf-8")
    return md


def main():
    ap = argparse.ArgumentParser(description="Layer 1 test suite")
    ap.add_argument("--scenarios", nargs="*", help="scenario JSON files (default: agent_testing/scenarios/*.json)")
    ap.add_argument("--skip-unit", action="store_true", help="don't run pytest first")
    ap.add_argument("--skip-daily", action="store_true", help="skip the day-by-day replay (faster)")
    ap.add_argument("--out", default=str(HERE / "reports"))
    args = ap.parse_args()

    files = [Path(f) for f in args.scenarios] if args.scenarios else sorted((HERE / "scenarios").glob("*.json"))
    unit = None if args.skip_unit else run_unit_tests()
    if unit:
        print(f"[unit tests] {unit.status}: {unit.detail.splitlines()[-1] if unit.detail else ''}", flush=True)
    results = []
    for f in files:
        res = run_scenario(f, HERE / "build", args.skip_daily)
        bad = [r for r in res["results"] if r["status"] == "fail"]
        print(f"[{res['scenario']}] {len(res['results']) - len(bad)}/{len(res['results'])} passed ({res['seconds']}s)"
              + "".join(f"\n   FAIL {r['check']}: {r['detail'][:300]}" for r in bad), flush=True)
        results.append(res)
    md = write_report(unit, results, Path(args.out))
    print(f"\nReport: {md}")
    failed = (unit and unit.status == "fail") or any(r["status"] == "fail" for s in results for r in s["results"])
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
