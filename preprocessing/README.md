# Layer 1 preprocessing (test platform)

A standalone tool that takes **one Apple Health export** and shows, step by step, how it becomes an
**ML-ready table: one row per person per night**. Nothing is trained here.

It's separate from `server/` and `mobile/` on purpose. Later, the same `pipeline.py` is meant to run on
the server, so the app can send raw data and get preprocessed results back.

```
Apple Health export
  1. Load        keep heart rate, resting HR, HRV (SDNN), sleep
  2. Clean       Apple Watch only, no duplicates, no impossible values
  3. Sleep window  join sleep pieces into sessions, pick each night's main sleep
  4. Nightly metrics  TST, efficiency, fragmentation, overnight HRV, overnight resting HR
  5. Missing data  every calendar night gets a row; flags and usable_* columns
  6. Baselines   previous 28 nights (not tonight), z-scores after 7 nights
  7. ML table    fixed columns + empty readiness_label  ->  CSV
  8. Daily updates  replay the file one sync at a time; only new nights are processed
```

## Run it (Windows, Mac or Linux)

Needs Python 3.10 or newer.

```bash
cd preprocessing
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

A browser tab opens at `http://localhost:8501`. Pick a sample file in the sidebar, or upload an export
(Health > profile picture > Export All Health Data). Very large exports load faster with the
**File path on this computer** option. Each tab is one step; the last tab downloads the CSV.

Without the visual platform:

```bash
python run_pipeline.py path\to\export.zip --person alex --days 90
```

## Files

| File | What it is |
|---|---|
| `pipeline.py` | The preprocessing. One function per step, plus `run_pipeline()` |
| `config.py` | Every threshold and window length in one place |
| `app.py` | The Streamlit platform that visualises each step |
| `incremental.py` | Daily updates: processes only the nights each sync needs (used by tab 8) |
| `run_pipeline.py` | Command-line runner; `--save-expected` rebuilds `expected/` |
| `sample_data/` | Three mock exports (same generator as `server/mock/`), dated Sep 1 to Oct 1, 2026 |
| `expected/` | The ML tables those three files must produce |
| `tests/` | `python -m pytest -q` |
| `agent_testing/` | Layer 1 tester: edge-case scenarios with exact truth, independent checks, reports. See its README |

## Sample files

| File | Story | What to look for |
|---|---|---|
| `mock_export_alex_overreach.zip` | Hard training block in the last 9 days | Tab 6: HRV z-score falls below −2, resting HR z-score rises above +2 |
| `mock_export_sam_steady.zip` | Steady and well recovered | z-scores stay near 0 |
| `mock_export_jordan_messy.zip` | Real-world mess | Tab 2: duplicates, glitches, other apps removed. Tab 3: naps ignored, iPhone In Bed used. Tab 5: missing nights and missing HRV |

## Decisions built in

- **Fragmentation = awakenings per hour of sleep.** The spec's *awake minutes ÷ time in bed* is kept as
  `waso_pct_of_tib`, but when there's no iPhone In Bed data it equals 100 − efficiency, so it adds nothing.
- **Time in bed** comes from iPhone *In Bed* records when they exist, otherwise sleep onset to final awakening
  (`tib_source` says which).
- **Overnight resting HR** is the lowest 30-minute average heart rate during sleep. Apple's own resting HR is a
  whole-day number and is kept only as `apple_rhr_bpm` for comparison.
- **HRV** is the mean SDNN inside the sleep window, log-transformed for z-scores. Apple Watch takes only a few
  readings a night, so nights with none are flagged, not filled in.
- **Baselines** use only earlier nights and only usable values; z-scores need at least 7 nights.
- **Signs are not flipped.** A high `z_rhr` or `z_frag` is the bad direction; flipping belongs to the
  readiness score, which isn't built here.
- **No motion-artifact filtering.** HealthKit gives processed values, not raw sensor signals.
- **Nights with missing data stay in the table** with flags, so the modelling step decides how to handle them.

## Daily updates (tab 8)

The first sync loads the whole history; after that each sync brings about one day (simulated at 8 am). Tab 8 replays a file
that way, with **Add next day**, **Skip ahead 3 days** and **Start over** buttons. Each run follows three rules:

1. **A night is processed at the user's update time the next day** (`DEFAULT_UPDATE_TIME`, 8:00 by default), or
   straight away if they tap **Update now** after waking. Night-shift users pick a later time.
2. **Each run processes the new night and redoes the 2 nights before it** (`RECOMPUTE_NIGHTS = 3`), plus any night the
   previous run added, to pick up data that synced late. Tick *HRV syncs a day late* to watch this fix a night;
   set it to 1 to see it fail.
3. **Skipped days are caught up**: every ready night not yet processed is processed.

New nights read only their own raw data; their baselines come from the saved nightly rows of earlier nights.
After every run the tab checks the result against processing all received data at once.
`tests/test_incremental.py` checks the same thing for all three samples, late data and skipped days.

## Changing the preprocessing

Edit `config.py` or `pipeline.py`, then run the tests. If the sample outputs changed **on purpose**, refresh
them and commit the new CSVs:

```bash
python -m pytest -q
python run_pipeline.py --save-expected
```

When this logic moves to the server or app, the `expected/` CSVs are the check that the new version
produces the same numbers.
