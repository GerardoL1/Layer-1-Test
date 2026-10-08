# Layer 1 tester

Tools for testing the Layer 1 preprocessing against `docs/layer1_spec.md`. A person can run them,
and so can the Claude "layer1-tester" skill, which also invents new edge-case scenarios.

```bash
cd preprocessing
python -m pip install -r requirements.txt
python agent_testing/run_layer1_tests.py                   # full run, about 5 minutes
python agent_testing/run_layer1_tests.py --skip-unit --skip-daily   # quick run, about 30 seconds
python agent_testing/run_layer1_tests.py --scenarios agent_testing/scenarios/09_loose_strap.json
```

Reports are written to `agent_testing/reports/` (Markdown + JSON). Exit code 1 means something failed.

## How it avoids "grading its own homework"

| Layer | What it checks | Where the right answer comes from |
|---|---|---|
| Truth checks | Sleep time, stages, awake minutes, awakenings, time in bed, HRV, naps, sleep window | The scenario builder wrote every record, so it knows the exact answers |
| Resting HR | Lowest 30-min average during sleep | A separate implementation in `checks.py` |
| Spec formulas | Efficiency, both fragmentation versions, ln(HRV), usable flags, notes, one row per night | Re-implemented from the spec, not imported from the pipeline |
| Z-scores | Every baseline and z-score | Re-computed independently (28 previous nights, ≥ 7 values, SD floor) |
| Story expectations | "HRV should drop in the last 5 nights", "night 12 is flagged" | Written in each scenario before running |
| Daily updates | Day-by-day results equal one full run | `incremental.py` vs the full pipeline |
| Unit tests | The 28 existing tests | `tests/` |

The tester was checked by planting six bugs in the pipeline (baseline too short, awakenings off by one,
third-party sleep app not filtered, 20-min resting HR window, wrong night date, 2 h short-sleep threshold).
All six were caught; with no bug planted, everything passed.

## Files

| File | What it is |
|---|---|
| `scenario_builder.py` | Scenario JSON → fake Apple Health export + exact truth. Event types are listed at the top of the file |
| `checks.py` | All checks and the expectation types a scenario can use |
| `run_layer1_tests.py` | Runs everything and writes the report |
| `scenarios/` | Edge-case people. `01`–`11` are the starter set; the tester skill adds `agent_*.json` |

## Starter scenarios

| Scenario | What it tests |
|---|---|
| 01 steady baseline | Nothing flagged, z-scores near 0 |
| 02 overreach block | HRV down, resting HR up, less and more broken sleep → z-scores move the bad way |
| 03 missed nights and HRV | Missing nights still get a flagged row; nights without HRV stay out of the HRV baseline |
| 04 short and late nights | 2.5 h night flagged; falling asleep at 2:30 am still counts for the previous evening |
| 05 night shift and naps | Day sleep is the main sleep; afternoon naps ignored |
| 06 older watch, no stages | Total sleep still right; nights noted as having no stages |
| 07 time zone travel | Flying west and back: one row per night, labelled by local time |
| 08 noisy export | Duplicates, impossible HR, other apps removed without changing any nightly value |
| 09 loose strap | Sparse HR → overnight resting HR flagged and kept out of the baseline |
| 10 late HRV sync | HRV arriving 26 h late is picked up by the daily redo |
| 11 new user | 6 nights → no z-scores yet |
