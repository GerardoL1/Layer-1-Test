# Recovery Platform (Group 2)

Turns Apple Watch data into a general readiness score and muscle-specific fatigue scores, with plain-language explanations.

This repo currently holds the **Layer 1 test**: proving that data can travel the full path.

```
Apple Watch → iPhone Health app → mobile app → server → computer browser
```

| Folder | What it is |
|---|---|
| `mobile/` | Expo / React Native (TypeScript) iPhone app. Reads heart rate, resting heart rate and HRV from Apple Health and sends them to the server. |
| `preprocessing/` | Standalone Layer 1 preprocessing test platform (Streamlit). Turns one Health export into an ML-ready nightly table and shows every step. See `preprocessing/README.md`. |
| `docs/` | `layer1_spec.md`: the Layer 1 formulas and decisions (source of truth for testing). |
| `server/` | Python FastAPI server. Receives data three ways, stores it in SQLite, and shows a dashboard at `http://localhost:8000`. |

A computer can't read Apple Health data directly, so something on the iPhone always has to send the data. There are three ways, and all of them land in the same database and dashboard:

| Route | Needs a Mac? | Automatic? | Use it for |
|---|---|---|---|
| A. Health app export file | No | No, manual | Loading history; building the training dataset |
| B. Health Auto Export app | No | Yes, after setup | Ongoing data without building our app (paid app feature) |
| C. Our own iPhone app (`mobile/`) | Yes, to build it | Yes, when opened | The real product |

## Requirements

- Mac with Xcode (needed to build the iPhone app)
- iPhone paired with an Apple Watch that has been worn for a few hours
- Node.js 22.13+ (for the mobile app) and Python 3.10+
- Mac and iPhone on the same Wi-Fi

## 1. Start the server (any computer: Mac, Windows or Linux)

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` on the same computer to see the dashboard.

For routes B and C the iPhone must reach the server over Wi-Fi. Find the computer's IP (Mac: `ipconfig getifaddr en0`; Windows: `ipconfig`, look for IPv4 Address), then from the iPhone's Safari open `http://<IP>:8000/health`; you should see `{"ok":true}`.

## 2A. No Mac: import a Health export file

1. On the iPhone: **Health → profile picture (top right) → Export All Health Data → Export**. This can take a few minutes.
2. Send the `export.zip` to the computer running the server (AirDrop, email, iCloud Drive or Google Drive).
3. Open `http://localhost:8000`, choose the file under **Upload a Health export**, enter a tester name, and click **Import**.

Large exports (several years of data, or over 1 GB) are faster from the command line:

```bash
cd server
python import_export.py ~/Downloads/export.zip --user tester1 --days 90
```

Re-importing the same export is safe; duplicates are ignored.

## 2D. No Mac, free and automatic: Apple Shortcuts

A shortcut on the iPhone reads the last 2 days of Watch data and posts it to `POST /api/shortcut` once a day. Re-sending overlapping days is safe; duplicates are ignored.

Each metric is one block of four actions (build one, then duplicate it):

1. **Find Health Samples** where Type is *Heart Rate* and Start Date is in the last *2 days*, sorted by Start Date.
2. **Repeat with Each** sample → **Text**: `Start Date | End Date | Value | Source` (both dates formatted as *ISO 8601* with *Include ISO 8601 Time* on) → **End Repeat**.
3. **Combine Text** (Repeat Results) with *New Lines*.
4. **Get Contents of URL**: `http://<computer-ip>:8000/api/shortcut`, Method *POST*, Request Body *Form* with fields `user`, `metric`, `rows` (= Combined Text).

| Health type in Shortcuts | `metric` value |
|---|---|
| Heart Rate | `heart_rate` |
| Resting Heart Rate | `resting_heart_rate` |
| Heart Rate Variability | `hrv_sdnn` |
| Sleep (Sleep Analysis) | `sleep` |

Then **Automation → Time of Day → Run Immediately** to run it daily. Health data can't be read while the iPhone is locked, so choose a time the phone is usually in use. The server replies with a line such as `heart_rate: received 412, new 398`; add a **Show Result** action while testing to see it.

## Mock data (no watch needed)

Three fake testers in the real Apple Health export format, each with a different story:

| File | Tester | Story |
|---|---|---|
| `mock_export_sam_steady.zip` | sam | Good sleep, stable HRV and resting HR |
| `mock_export_alex_overreach.zip` | alex | Normal for 3 weeks, then a hard training block: shorter, broken sleep, HRV drops, resting HR rises |
| `mock_export_jordan_messy.zip` | jordan | Real-world gaps: missed nights, days with no HRV, iPhone "In Bed" records, watch not always worn |

Upload them on the dashboard like a real export (use the tester names above), or make fresh ones dated up to today:

```bash
cd server
python mock/make_mock_export.py --days 30
```

Files appear in `server/mock_exports/`. Options: `--days 60`, `--profile alex`, `--end 2026-10-01`. The data is random but repeatable, so everyone on the team gets the same numbers.

## 2B. No Mac: Health Auto Export (automatic)

1. Install **Health Auto Export – JSON+CSV** from the App Store. Sending data automatically to a server needs its **Premium** upgrade.
2. In the app: **Automations → new automation → REST API**.
3. Set the URL to `http://<computer-ip>:8000/api/hae?user_id=tester1` (use each tester's own name).
4. Export format **JSON**. Choose the metrics **Heart Rate, Resting Heart Rate, Heart Rate Variability, Sleep Analysis**.
5. Run it once manually, then check the dashboard.

The server keeps a copy of every payload in `server/hae_raw/` so you can inspect exactly what the app sent. Metrics we don't use yet (like steps) are listed as "ignored" in the server log. Sleep stages only come through when sleep is exported unaggregated (as individual phases); if the dashboard shows no sleep for these testers, check the app's sleep export setting and look at the raw file.

## 2C. With a Mac: build our iPhone app

```bash
cd mobile
npm install
npx expo run:ios --device
```

Before the first build:
- In `mobile/app.json`, change `ios.bundleIdentifier` (`com.group2.recoverytest`) to something unique to your team.
- On the iPhone, turn on Settings → Privacy & Security → Developer Mode.
- Sign in with your Apple ID in Xcode → Settings → Accounts if asked. Free accounts work, but the app expires after 7 days.
- If the phone blocks the app on first launch, trust it in Settings → General → VPN & Device Management.

The app does **not** run in Expo Go because HealthKit needs a development build.

## 3. Run the test (route C)

1. In the app, enter the server address (e.g. `http://192.168.1.50:8000`) and a tester name.
2. Tap **Connect Apple Health** and allow all three data types. Allow the local network prompt too.
3. Tap **Send to platform**.
4. On the Mac, open `http://localhost:8000` to see the chart, sleep table and summary.
5. Compare a few readings with Health → Heart → Heart Rate. Tap Send again; it should report **0 new** (duplicates are ignored).

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| 0 samples read | Permissions off: Settings → Health → Data Access & Devices → Recovery Test |
| "Network request failed" | Wrong IP, server not running, different Wi-Fi, or Mac firewall |
| Crash when sending | Send was tapped before Connect Apple Health |
| Only a few HRV samples | Normal; the watch measures HRV only a few times per day |
| Import says "No export.xml found" | Upload the zip made by the Health app, not a re-zipped folder |
| Import fails with an XML error | Unzip the export and upload `export.xml` directly, or use `import_export.py` |
| No sleep in the dashboard | The watch must be worn to bed with Sleep tracking on (Watch app → Sleep) |

## Test-only settings to remove before real users

- `NSAllowsArbitraryLoads` in `mobile/app.json` (allows plain `http`). Real deployments need HTTPS.
- Open CORS (`allow_origins=["*"]`) in `server/main.py`.
- No login yet: the tester name is trusted as-is.

`*.db` files and `server/hae_raw/` are git-ignored because they contain real health data. Never commit them.

## Next steps

- Layer 1 metrics from the sleep and vitals tables (TST, efficiency, fragmentation, z-scores)
- Local SQLite buffer on the phone with anchored (incremental) sync
- User accounts and login
- Workout log and daily readiness / soreness self-reports (training labels)
- EMG and GSR sensors over Bluetooth (ESP32)
