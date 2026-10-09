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

For the iPhone (or Health Auto Export / Shortcuts) to reach the server, both must be on the same Wi-Fi. Find the
computer's IP (Windows: `ipconfig`, look for IPv4 Address. Mac: `ipconfig getifaddr en0`), then open
`http://<IP>:8000/health` in the iPhone's Safari. If it doesn't load, allow Python through the computer's firewall.

## What it stores

| Table | What's in it |
|---|---|
| `samples` | Heart rate, resting heart rate, HRV: value, start/end (UTC ms), **UTC offset**, source |
| `sleep_stages` | In bed / awake / core / deep / REM / unspecified: start/end, **offset at start and at end** (a night can cross a clock change), source |
| `users` | Settings: time zone, update time, age, training, training days, units |
| `nights` | Each person's processed nightly rows (everything the pipeline keeps, including baselines) |
| `runs` | What each processing run did: new nights, redone nights, what changed |

Readings are keyed by user + ID, and repeats are ignored, so sending the same data twice is always safe.
Readings from other apps and devices are stored too: the pipeline's cleaning step removes them, exactly as tested.

## How processing works (`processing.py`)

It reuses `DailyProcessor` from `preprocessing/incremental.py`, so results equal the tested pipeline.

- Runs in the background after new data arrives, and before the app reads results, but **only when something
  changed**: new readings, or the clock passing the person's update time.
- "Now" is the person's local time: from their time zone setting, or else the offset of their newest reading.
- Each run processes every ready night not yet processed, redoes the 2 nights before (late data), and saves
  the nightly table.

## API for the app (`api.py`)

Every endpoint takes `?user_id=<tester name>`. Unknown users get 404.

| Endpoint | Returns |
|---|---|
| `GET /api/today` | Last night's readiness, verdict and reason, metric rows with usual range and change, sleep stages, quality notes, update time, whether Update now can do anything |
| `GET /api/trends?nights=14\|28\|90` | One entry per night (readiness, HRV, resting HR, sleep, efficiency, fragmentation, usual bands) plus one-line summaries |
| `GET /api/profile` | Usual ranges, nights recorded, data sources, last update, settings |
| `GET /api/settings`, `PUT /api/settings` | Time zone, update time (`HH:MM`), age, training, training days (0 = Monday), units. PUT changes only the fields sent |
| `POST /api/update-now` | Processes last night early if its sleep has ended |
| `POST /api/demo/sam\|alex\|jordan` | Loads a demo person (`demo-sam` ...) with the clock fixed at 1 Oct 2026, 8:30 am. Testing only |

Placeholders, marked `"placeholder": true` in responses: the readiness formula and 40 / 70 cut-offs and the usual
range (top of `api.py`), and all wording (`explain.py`, to be replaced by the LLM).

## The four ways data arrives (`main.py`)

| Route | Endpoint | Time zone from |
|---|---|---|
| Our iPhone app | `POST /upload` | Sent with every reading (`tz_offset_min`, or `start_tz_min` / `end_tz_min` for sleep). Readings without it are rejected |
| Health export file | `POST /api/import` (form: `file`, `user_id`, `since_days`), status at `GET /api/import/status` | The dates in the file |
| Health Auto Export | `POST /api/hae?user_id=...` | The dates in the payload |
| Apple Shortcuts | `POST /api/shortcut` | The ISO 8601 dates sent |

### Health export from the command line

Faster for very large exports (several years, over 1 GB):

```bash
python import_export.py C:\Users\you\Downloads\export.zip --user tester1 --days 90
```

`--days 0` imports everything.

### Health Auto Export (no Mac, automatic, paid app feature)

1. Install **Health Auto Export – JSON+CSV** from the App Store. Sending to a server needs its **Premium** upgrade.
2. **Automations > new automation > REST API**. URL: `http://<computer-ip>:8000/api/hae?user_id=tester1`.
3. Format **JSON**. Metrics: **Heart Rate, Resting Heart Rate, Heart Rate Variability, Sleep Analysis**.
   Export sleep **unaggregated** (individual phases), or no sleep stages come through.
4. Run it once manually, then open the app.

Metrics we don't use (like steps) are listed as `ignored_metrics` in the reply.

### Apple Shortcuts (no Mac, free, once a day)

A shortcut reads the last 2 days and posts it to `POST /api/shortcut`. Each metric is one block (build one,
then duplicate it):

1. **Find Health Samples** where Type is *Heart Rate* and Start Date is in the last *2 days*, sorted by Start Date.
2. **Repeat with Each** sample > **Text**: `Start Date | End Date | Value | Source` (both dates as *ISO 8601* with
   *Include ISO 8601 Time* on) > **End Repeat**.
3. **Combine Text** (Repeat Results) with *New Lines*.
4. **Get Contents of URL**: `http://<computer-ip>:8000/api/shortcut`, Method *POST*, Request Body *Form* with
   fields `user`, `metric`, `rows` (= Combined Text).

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
.venv\Scripts\python -m pip install pytest httpx
.venv\Scripts\python -m pytest -q tests
```

About 2–3 minutes. They use a throwaway database, never `platform.db`.

| File | Checks |
|---|---|
| `test_storage.py` | Every ingestion route keeps the UTC offset. Data through the database gives exactly the pipeline's table |
| `test_processing.py` | Several runs a day give the same table as processing everything at once (including late HRV), update time, Update now, time zones |
| `test_api.py` | Today, Trends, Profile, Settings, Update now, demo mode, placeholder wording |
| `test_scenarios.py` | All Layer 1 tester scenarios through the server, plus the tester's own independent checks |
| `test_edges.py` | A night across a clock change, runs at the same time, changing the update time, one phone with two tester names, upgrading an old database |

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| iPhone can't reach the server | Wrong IP, server not started with `--host 0.0.0.0`, different Wi-Fi, or the firewall |
| `/upload` replies 400 "missing its UTC offset" | An old app build. Rebuild the iPhone app |
| Import says "No export.xml found" | Upload the zip made by the Health app, not a re-zipped folder |
| Import fails with an XML error | Unzip the export and upload `export.xml`, or use `import_export.py` |
| No sleep for a tester | The watch must be worn to bed with Sleep tracking on (Watch app > Sleep) |
| Today shows an older night | Last night is processed at the update time. Tap Update now after waking, or change the update time in Profile |
