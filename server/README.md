# Server

FastAPI + SQLite. It receives Apple Health data four ways, stores only what Layer 1 needs, runs the Layer 1
preprocessing (`../preprocessing/`) and serves the app's API. It has no web page of its own: the computer view is
the Expo app in a browser (`../mobile/`).

## Run

```bash
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

- `http://localhost:8000/health` should show `{"ok":true}`.
- `http://localhost:8000/docs` lists every endpoint and lets you try them.
- The database is `platform.db` next to this file (git-ignored). Stop the server and delete it for a fresh start.
  Set `RECOVERY_DB` to use another file.
- Run one server process only (no `--workers`). Import progress and the per-person processing lock live in memory,
  so a second process would lose track of imports and could save two runs with the same number.

For the iPhone (or Health Auto Export / Shortcuts) to reach the server, both must be on the same Wi-Fi. Find the
computer's IP (Windows: `ipconfig`, look for IPv4 Address. Mac: `ipconfig getifaddr en0`), then open
`http://<IP>:8000/health` in the iPhone's Safari. If it doesn't load, allow Python through the computer's firewall.

## Code layout

`main.py` only puts the app together. Everything else is in `app/`:

| Folder | What's in it |
|---|---|
| `app/core/` | `db.py` (tables, saving and loading readings), `limits.py` (size limits and their messages), `json_values.py` |
| `app/schemas/` | Request bodies and response shapes, one file per area (`today.py`, `trends.py`, `settings.py` ...). The routes use them as `response_model`, so `/docs` and `openapi.json` describe every reply |
| `app/middleware/` | `size_limit.py`, the 413 for requests over the limit |
| `app/services/` | The work behind the endpoints: `processing.py`, `apple_export.py` (reads export files), `health_auto_export.py`, `shortcuts.py`, `import_jobs.py`, `readings.py`, `users.py`, `update_schedule.py` |
| `app/readiness/` | Placeholders: `scoring.py` (readiness score and cut-offs), `usual.py` (usual range, Worse / Usual / Better), `explain.py` (wording) |
| `app/routers/` | The endpoints, one file per screen or data route: `today`, `trends`, `profile`, `settings`, `update_now`, `demo`, `readings`, `imports`, `health` |

## API description (`openapi.json`)

`openapi.json` describes every endpoint, request and reply. The app's TypeScript types are generated from it.
After changing an endpoint or a schema, run `python export_openapi.py`, then `npm run api-types` in `../mobile/`.
A test fails if it's out of date.

## What it stores

| Table | What's in it |
|---|---|
| `samples` | Heart rate, resting heart rate, HRV: value, start/end (UTC ms), **UTC offset**, source |
| `sleep_stages` | In bed / awake / core / deep / REM / unspecified: start/end, **offset at start and at end** (a night can cross a clock change), source |
| `users` | Settings: time zone, update time, age, training, training days, units, weight |
| `nights` | Each person's processed nightly rows (everything the pipeline keeps, including baselines) |
| `runs` | What each processing run did: new nights, redone nights, what changed |
| `readiness_snapshots` | The first score each night got, with the exact inputs, kept for training even after late data changes the night |
| `checkins` | Morning check-in answers, one per night. The labels for the readiness model |
| `workouts` | Workouts and their effort and satisfaction ratings |

Readings are keyed by user + ID, and repeats are ignored, so sending the same data twice is always safe.
Readings from other apps and devices are stored too: the pipeline's cleaning step removes them, exactly as tested.

## How processing works (`app/services/processing.py`)

It reuses `DailyProcessor` from `preprocessing/layer1/incremental.py`, so results equal the tested pipeline.

- Runs in the background after new data arrives, and before the app reads results, but **only when something
  changed**: new readings, or the clock passing the person's update time.
- "Now" is the person's local time: from their time zone setting, or else the offset of their newest reading.
- Each run processes every ready night not yet processed, redoes the 2 nights before (late data), and saves
  the nightly table.

## API for the app (`app/routers/`)

The API is versioned under `/api/v1`, and everything about one person is under `/api/v1/users/{user_id}`
(the tester name). Below, `.../` means `/api/v1/users/{user_id}/`. Unknown users get 404. Errors come back as
`{"detail": "..."}` with a message the app can show as is.

| Endpoint | Returns |
|---|---|
| `GET .../today` | Last night's readiness (score, status, confidence, contributions in points, illness flag, model version), verdict, reason and advice, metric rows with usual range and change, sleep stages, quality notes, update time, whether Update now can do anything |
| `GET .../trends?nights=14\|28\|90` | One entry per night (readiness, HRV, resting HR, sleep, efficiency, fragmentation, usual bands) plus one-line summaries |
| `GET .../profile` | Usual ranges, nights recorded, data sources, last update, settings |
| `GET .../settings`, `PATCH .../settings` | Time zone, update time (`HH:MM`), age, training, training days (0 = Monday), units, weight (`weight_kg`, 30 to 300). PATCH changes only the fields sent |
| `POST .../checkins/morning`, `GET .../checkins/morning`, `GET .../checkins/morning/{night}` | The morning check-in (1 to 10 scales, sore muscles, anything unusual, rehydrated). One answered on day D labels the night of D−1, and comes back with the score first shown for that night. Answering again replaces it |
| `POST .../workouts`, `GET .../workouts?days=28`, `GET .../workouts/{id}` | Workouts. The sender gives the id, so sending one again updates it |
| `PUT .../workouts/{id}/rating` | The after-workout check-in: effort and satisfaction (1 to 10). Load = effort × minutes |
| `POST .../processing-runs` | Update now: processes last night early if its sleep has ended |
| `POST /api/v1/demo-users/sam\|alex\|jordan` | Loads a demo person (`demo-sam` ...) with the clock fixed at 1 Oct 2026, 8:30 am. Testing only |

Placeholders, marked `"placeholder": true` in responses: the readiness formula and 40 / 70 cut-offs and the usual
range (`app/readiness/scoring.py` and `usual.py`), and all wording (`app/readiness/explain.py`, to be replaced by
the LLM).

The score and the wording go through two small interfaces, so the team's trained model and the LLM drop in
without touching the routes or the app: `ReadinessModel` (`app/readiness/model.py`, the placeholder formula is
`PlaceholderModel`, the inputs come from `features.py`) and `Explainer` (`TemplateExplainer` in `explain.py`).
See `docs/ml_llm_plan.md`.

## The four ways data arrives (`app/routers/readings.py` and `imports.py`)

| Route | Endpoint | Time zone from |
|---|---|---|
| Our iPhone app | `POST .../readings` (JSON: `samples`, `sleep`) | Sent with every reading (`tz_offset_min`, or `start_tz_min` / `end_tz_min` for sleep). Readings without it are rejected |
| Health export file | `POST .../imports` (form: `file`, and optionally `since_days` to keep only the last N days counted back from today; everything by default). Replies 202 with the import's `import_id` and a `Location` header. Progress at `GET .../imports/{import_id}`, latest import at `GET .../imports` | The dates in the file |
| Health Auto Export | `POST .../readings/health-auto-export` | The dates in the payload |
| Apple Shortcuts | `POST .../readings/shortcuts` (form: `metric`, `rows`) | The ISO 8601 dates sent |

### Health export from the command line

Faster for very large exports (several years, over 1 GB):

```bash
python import_export.py C:\Users\you\Downloads\export.zip --user tester1
```

Everything in the file is imported. `--days 90` keeps only the last 90 days, counted back from today.

### Training table for the readiness model

```bash
python export_training_table.py C:\Users\you\Desktop\training.csv
```

One row per person per night:
- the score first shown that morning and the exact inputs behind it (`readiness_snapshots`)
- that morning's check-in, which is the label (the check-in on day D labels night D−1)
- training load from rated workouts (effort × minutes) over the last 1, 3, 7 and 28 days up to that evening
- body weight

Options:
- `--user tester1` for one person (repeat it for several).
- `--labelled-only` keeps only nights with a check-in.
- `--include-catch-up` adds nights that came in a first sync or an import, which Today never showed.

`placeholder_score` is there to compare against, never to train on. It's real health data, so the command
refuses to write inside the repo folder. See `docs/ml_llm_plan.md`.

### Health Auto Export (no Mac, automatic, paid app feature)

1. Install **Health Auto Export – JSON+CSV** from the App Store. Sending to a server needs its **Premium** upgrade.
2. **Automations > new automation > REST API**. URL:
   `http://<computer-ip>:8000/api/v1/users/tester1/readings/health-auto-export`.
3. Format **JSON**. Metrics: **Heart Rate, Resting Heart Rate, Heart Rate Variability, Sleep Analysis**.
   Export sleep **unaggregated** (individual phases), or no sleep stages come through.
4. Run it once manually, then open the app.

Metrics we don't use (like steps) are listed as `ignored_metrics` in the reply.

### Apple Shortcuts (no Mac, free, once a day)

A shortcut reads the last 2 days and posts it to `POST .../readings/shortcuts`. Each metric is one block (build one,
then duplicate it):

1. **Find Health Samples** where Type is *Heart Rate* and Start Date is in the last *2 days*, sorted by Start Date.
2. **Repeat with Each** sample > **Text**: `Start Date | End Date | Value | Source` (both dates as *ISO 8601* with
   *Include ISO 8601 Time* on) > **End Repeat**.
3. **Combine Text** (Repeat Results) with *New Lines*.
4. **Get Contents of URL**: `http://<computer-ip>:8000/api/v1/users/tester1/readings/shortcuts`, Method *POST*,
   Request Body *Form* with fields `metric` and `rows` (= Combined Text).

| Health type in Shortcuts | `metric` value |
|---|---|
| Heart Rate | `heart_rate` |
| Resting Heart Rate | `resting_heart_rate` |
| Heart Rate Variability | `hrv_sdnn` |
| Sleep (Sleep Analysis) | `sleep` |

Then **Automation > Time of Day > Run Immediately**. Health data can't be read while the iPhone is locked, so pick
a time the phone is usually in use. The reply looks like `heart_rate: received 412, new 398`.

## Mock exports

Fake Apple Health exports in the real format, for testing without a watch:

```bash
python mock/make_mock_export.py --days 30
```

Files appear in `mock_exports/` (git-ignored). Options: `--days 60`, `--profile alex`, `--end 2026-10-01`.
The data is random but repeatable. The three in `../preprocessing/sample_data/` were made with it.

## Tests

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

About 2–3 minutes. They use a throwaway database, never `platform.db`.

| File | Checks |
|---|---|
| `test_storage.py` | Every ingestion route keeps the UTC offset. Data through the database gives exactly the pipeline's table |
| `test_processing.py` | Several runs a day give the same table as processing everything at once (including late HRV), update time, Update now, time zones |
| `test_api.py` | Today, Trends, Profile, Settings, Update now, demo mode, placeholder wording |
| `test_scenarios.py` | All Layer 1 tester scenarios through the server, plus the tester's own independent checks |
| `test_edges.py` | A night across a clock change, runs at the same time, changing the update time, one phone with two tester names, upgrading an old database |
| `test_limits.py` | Size limits: oversized requests and zips get a clear 413 |
| `test_short_night.py` | Short nights get their own status and wording |
| `test_openapi.py` | `openapi.json` is up to date and every v1 endpoint describes its reply |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| iPhone can't reach the server | Wrong IP, server not started with `--host 0.0.0.0`, different Wi-Fi, or the firewall |
| Uploads reply 400 "missing its UTC offset" | An old app build. Rebuild the iPhone app |
| Import says "No export.xml found" | Upload the zip made by the Health app, not a re-zipped folder |
| Import fails with an XML error | Unzip the export and upload `export.xml`, or use `import_export.py` |
| No sleep for a tester | The watch must be worn to bed with Sleep tracking on (Watch app > Sleep) |
| Today shows an older night | Last night is processed at the update time. Tap Update now after waking, or change the update time in Profile |
