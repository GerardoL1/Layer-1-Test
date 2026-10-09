# Recovery Platform (Group 2)

A gym recovery and readiness platform. Each morning it gives a **readiness score (0–100)** for the whole body,
and later **muscle-specific fatigue**, with a plain-language explanation of why.

This repo holds **Layer 1: systemic recovery from the Apple Watch** (overnight HRV, resting heart rate,
heart rate and sleep stages), working end to end. Layers 2 (sEMG patch) and 3 (sweat biosensor), the ML models
and the LLM explanations come later.

```
Apple Watch ──> iPhone Health app ──> our iPhone app ─────┐
                                  ──> Health export file ─┤
                                  ──> Health Auto Export ─┼──> server ──> app (iPhone + computer)
                                  ──> Apple Shortcuts ────┘    stores readings with their time zone,
                                                               runs the Layer 1 preprocessing every morning
```

| Folder | What it is |
|---|---|
| `docs/layer1_spec.md` | **Source of truth** for every Layer 1 formula and decision |
| `preprocessing/` | The Layer 1 pipeline (raw readings to one row per night), its tests, the Layer 1 tester and a Streamlit test platform. See `preprocessing/README.md` |
| `server/` | FastAPI + SQLite. Receives data four ways, runs the pipeline, serves the app's API. See `server/README.md` |
| `mobile/` | One Expo app for iPhone **and** computer (Expo web). Today, Trends, Profile, Setup. See `mobile/README.md` |
| `.github/workflows/ci.yml` | Runs all tests on every push |

## Try it in 5 minutes (Windows, no iPhone needed)

Needs Python 3.10+ and Node.js 22.13+. Open two Command Prompt windows.

**Window 1, the server:**

```bash
cd server
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Mac/Linux: `python3 -m venv .venv` and `source .venv/bin/activate`.

**Window 2, the app in your browser:**

```bash
cd mobile
npm install
npx expo start --web
```

Open `http://localhost:8081`. In **Test build** at the bottom of the first screen, click **Sam**, **Alex** or
**Jordan** to load a demo person (mock data with the clock fixed at 1 Oct 2026, 8:30 am):

| Demo | Story |
|---|---|
| Sam | Steady and well recovered |
| Alex | Normal for 3 weeks, then a hard training block: HRV drops, resting HR rises, shorter and broken sleep |
| Jordan | Real-world gaps: missed nights, nights without HRV, iPhone "In Bed" records |

To use your own data on a computer: in Test build, type a tester name, click **Use this tester**, then in Setup or
Profile choose **Import Apple Health export** (on the iPhone: Health > profile picture > Export All Health Data).

## Getting real data in

| Route | Needs a Mac? | Automatic? | How |
|---|---|---|---|
| Our iPhone app | Yes, to build it | Yes: on open, in the background, and before Update now | `mobile/README.md` |
| Health export file | No | No, manual | Profile > Import Apple Health export, or `python import_export.py` (`server/README.md`) |
| Health Auto Export app | No | Yes (paid app feature) | `server/README.md` |
| Apple Shortcuts | No | Yes, once a day | `server/README.md` |

Every route stores each reading with its UTC offset, so nights are worked out in the person's local time,
even after travel or a clock change.

## How a night becomes a score

1. Readings arrive and are stored (Apple Watch data is kept, everything else is removed during cleaning).
2. Each person picks an **update time** (default 8:00). Once it passes, last night is processed. **Update now**
   on Today processes it early if the sleep has ended.
3. Each run also redoes the 2 previous nights, to catch data that synced late. Results equal processing
   everything at once (the tests check this).
4. The app shows the score, the "Last night" numbers against your usual, and 14 / 28 / 90-night trends.

## Placeholders (not decided yet)

These work, but are clearly marked in code and in the API (`"placeholder": true`) until the team decides:

| What | Current placeholder | Where |
|---|---|---|
| Readiness score | 50 + 10 × average of the z-scores (HRV, sleep time and efficiency up; resting HR and fragmentation down), clipped 0–100 | `server/api.py` |
| Low / Moderate / Ready cut-offs | 40 / 70 | `server/api.py` |
| "Your usual" range and Worse / Usual / Better | Baseline mean ± 1 SD | `server/api.py` |
| Verdict, reason and Trends sentences | Simple templates, to be written by the LLM | `server/explain.py` |
| Morning check-in, reminder, export, delete | Shown as "Coming soon" | `mobile/` |

## Tests

```bash
cd preprocessing
python -m pytest -q
python agent_testing/run_layer1_tests.py
```

```bash
cd server
.venv\Scripts\python -m pip install pytest httpx
.venv\Scripts\python -m pytest -q tests
```

```bash
cd mobile
npx tsc --noEmit
npx expo lint
npm test
```

GitHub Actions runs all of these (with a quick Layer 1 tester run) on every push. Results are under the
repo's **Actions** tab. Run the tests and the Layer 1 tester after every change to `preprocessing/`.

## Health data

Never commit real health data. Only the mock exports in `preprocessing/sample_data/` belong in git.
`*.db` files and raw uploads are git-ignored.

## Test-only settings to remove before real users

- **No login yet:** the tester name is trusted as-is. The **Test build** section and demo mode
  (`POST /api/demo/...`, `demo-*` users) are for testing only.
- Open CORS (`allow_origins=["*"]`) in `server/main.py`.
- `NSAllowsArbitraryLoads` in `mobile/app.json` (allows plain `http`). Real deployments need HTTPS.

## Next steps

- Team decision on the readiness weights and cut-offs, then the ML readiness model
- LLM explanations (replace `server/explain.py`)
- Morning check-in (training labels), data export and delete
- Layer 2 (sEMG patch) and Layer 3 (sweat biosensor), the Muscles and Train tabs
- Figma: add the Update time row, Update now and Import Apple Health export
