# ML and LLM plan

How the readiness model, the muscle fatigue model and the LLM explanation will fit into the platform.
The models are built by the team outside this repo and added later. This repo only gets the places they
plug into, and the data they'll be trained on. No ML or LLM code or dependencies go in until then.

## Data flow

```
Apple Watch ──> Layer 1 preprocessing ──> nightly feature table
                                              │
Nix sweat import or manual entry (Layer 3) ───┤ optional, low weight, capped
                                              ▼
                                   READINESS MODEL  (today: placeholder formula)
                                              │ score, status, confidence,
                                              │ contributions, illness flag
                                              ▼
                                   EXPLANATION  (today: templates, later: LLM)
                                              ▼
                                   app: Today, Trends

sEMG patch (Layer 2) ──> MUSCLE FATIGUE MODEL ──> per-muscle fatigue ──> Muscles, workout summary
                         (does not feed the general readiness score)

Morning and after-workout check-ins ──> the labels both models are trained on
```

## 1. General readiness score

Answers "is my body recovered enough to train hard today?" One model, fed by Layer 1 and optionally Layer 3.

**Inputs**, one row per person per night, using only what's known by the morning update time:
- Core, already computed: HRV (`hrv_ln`, `z_hrv`), overnight resting HR (`rhr_night_bpm`, `z_rhr`), total
  sleep (`tst_min`, `z_tst`), efficiency (`sleep_efficiency_pct`, `z_eff`), fragmentation
  (`fragmentation_per_hr`, `z_frag`). Both the raw value and the z-score.
- Derived, to add: HRV 7-night average against the 28-night baseline, sleep debt over the last 3 and 7
  nights, number of poor nights in a row. These need the person's earlier nights, not just one row.
- Lower weight: `waso_min`, bedtime and wake time against usual, `sleep_latency_min`, naps.
- Data quality, so thin data is trusted less: `flag_short_sleep`, `flag_no_hrv`, `flag_low_hr_coverage`,
  `flag_no_stages`, `hrv_count`, `hr_slot_count` (5-minute slots with heart rate, the coverage measure since
  spec decision 4), and the baseline sizes (`*_base_n`).
- Training load, to add: from logged workouts, effort (1 to 10) times minutes. Yesterday's load, hard days in
  the last 3, last 7 days against the last 28.
- Illness signals, later: respiratory rate and wrist temperature during sleep, used as a warning flag rather
  than a normal input. Not collected yet.
- Left out for now: deep, REM and core minutes (noisy), `apple_rhr_bpm` (duplicates our own).
- Layer 3, optional: fluid loss as a share of body weight and sodium loss from the last 1 to 2 days of
  workouts, plus a `has_sweat_data` flag. Missing stays empty, never 0. Low weight, possibly capped. The
  score has to work fully without it, since most people won't have a sweat sensor.

**Target:** the morning check-in answer "How ready do you feel to train hard today?" (1 to 10). A secondary
check is how the next workout went. Never the placeholder score.

**Models to compare** (built outside the repo): the current formula as the baseline, ridge regression,
LightGBM with SHAP (the likely one to ship), and a mixed-effects model for the report. Validation splits by
person and by time.

**What the server receives for each night:**
- `score` (0 to 100) and `status` (low, moderate, ready, or the no-score statuses building_baseline,
  short_sleep, no_data)
- `confidence`, for example high, medium, low, or "based on sleep only"
- `contributions`: a list of input, label, value and effect in points, like "HRV trend −8"
- `illness_flag` and `model_version`
- `placeholder: true` until the real model is in

## 2. Muscle fatigue (Layer 2)

A separate model. Per muscle, from the patch during workouts (signal strength per rep, rep speed if there's an
accelerometer), it gives fatigue per set and an estimated "ready again" time. Shown on Muscles and the workout
summary only. Labels come from the check-in's sore-muscle body map and soreness rating.

## 3. Check-ins are the labels

Designed in Figma (Round 5, Check-in v2). Every scale is 1 to 10 and 10 is always the good end. Each answer
is saved with the person, what it belongs to and when it was given.
- **Morning:** ready to train hard (the main target), sleep quality, physical fatigue, energy, stress,
  motivation, hydration, muscle soreness, which muscles are sore (14 body-map groups), anything unusual since
  yesterday (alcohol, feeling sick, late caffeine, travel, poor diet, none), and optionally whether you
  rehydrated after yesterday's workout (not really, somewhat, fully).
- **After a workout:** how hard it was and how happy you are with how it went (both 1 to 10). Effort times
  minutes is the training load.

## 4. LLM explanation

- Replaces the templates and keeps their outputs: verdict, reason and advice on Today, one-line summaries on
  Trends.
- Gets only structured inputs: score, status, confidence, contributions, illness flag and a little context
  (yesterday's workout, the hydration note). Never raw health records.
- Can't invent numbers or causes. Every claim comes from the contributions. Plain, short, not medical advice.
- If it fails or is slow, the templates are used. The app never waits on it to show the score.

## Decided (2026-10-23)

1. Trends shows the latest score. `readiness_snapshots` keeps the first score shown each morning, with the
   exact inputs, for training.
2. Illness: the score and status stay as they are. `illness_flag` is added and the app shows a warning banner
   (the Notice component). No new status.
3. The explanation may only cite inputs whose Last night row isn't "Usual", so the text never contradicts the
   rows.
4. Body weight is added to settings and to the setup "About you" step.
5. The morning check-in on day D belongs to the night of D−1 and to the snapshot first shown that morning.
6. The Layer 1 side owns workouts and check-ins storage and API.
7. Short nights stay as they are (no score). Still an open decision, see `open_decisions.md`.
8. Respiratory rate and wrist temperature come later, not now.

## Where it plugs in

- `server/app/readiness/model.py`: a `ReadinessModel` interface (`score(features) -> ReadinessResult`). The
  placeholder formula is one implementation. A trained model is another, chosen by a setting.
- `server/app/readiness/features.py`: builds one night's inputs from the person's nights up to that night,
  so derived history features have one place to live.
- `server/app/readiness/explain.py`: an `Explainer` interface. The templates are one implementation. A later
  LLM one runs in the background and is cached, with the templates as the fallback.
- `readiness_snapshots`, `checkins` and `workouts` tables, and `server/export_training_table.py`, which joins
  them into the training table (written outside the repo, since it's real health data).
