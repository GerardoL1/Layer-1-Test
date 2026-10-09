"""
The Layer 1 tester's edge-case scenarios, run through the server instead of the
pipeline directly: export -> database -> DailyProcessor -> saved nightly table.

Each scenario must
  1. give exactly the same table as the pipeline processing everything at once, and
  2. pass the tester's own independent checks (truth, spec formulas, z-scores, expectations).

    python -m pytest -q tests/test_scenarios.py
"""
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

import db
import incremental as I
import pipeline as P
import processing
from apple_export import import_export
from conftest import ROOT

TESTER = ROOT / "preprocessing" / "agent_testing"
sys.path.insert(0, str(TESTER))
from checks import expectation_checks, spec_checks, truth_checks, zscore_oracle  # noqa: E402
from scenario_builder import build, load_spec  # noqa: E402

SCENARIOS = sorted((TESTER / "scenarios").glob("*.json"))


@pytest.mark.parametrize("path", SCENARIOS, ids=[p.stem for p in SCENARIOS])
def test_scenario_through_server(path, tmp_path):
    spec = load_spec(path)
    sc = build(spec)
    zip_path = tmp_path / "export.zip"
    zip_path.write_bytes(sc.export_zip())

    user = f"sc_{spec['name']}"
    # A fixed clock the morning after the scenario's last evening, past the 8:00 update time.
    end = date.fromisoformat(spec.get("end_date", "2026-10-01"))
    clock = datetime.combine(end + timedelta(days=1), datetime.min.time()).replace(hour=9)
    with db.connect() as conn:
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user, clock.isoformat()))
        import_export(zip_path, conn, user)
    processing.process_user(user, force=True)

    with db.connect() as conn:
        server_nights = processing.load_nights(conn, user)
        ready = conn.execute("SELECT ready_through FROM runs WHERE user_id = ? ORDER BY run DESC LIMIT 1",
                             (user,)).fetchone()["ready_through"]
    server_ml = P.build_ml_table(server_nights, user)

    # 1. Same as processing everything at once (up to the same last night).
    records, _ = P.load_export(zip_path, days=None)
    full = I.full_reprocessing(records, user, date.fromisoformat(ready))
    problems = I.compare(server_ml, full)
    assert problems.empty, problems.head(20).to_string()

    # 2. The tester's own checks, on the nights the scenario has data for.
    last_data_night = P.run_pipeline(zip_path, user, days=None).nights["night_date"].max()
    nights = server_nights[server_nights["night_date"] <= last_data_night].reset_index(drop=True)
    ml = P.build_ml_table(nights, user)
    results = (truth_checks(sc, nights) + spec_checks(nights, ml) + zscore_oracle(nights)
               + expectation_checks(spec.get("expect", []), sc.truth, nights))
    failed = [f"{r.check}: {r.detail}" for r in results if r.status == "fail"]
    assert not failed, "\n".join(failed)
    assert results, "no checks ran"
