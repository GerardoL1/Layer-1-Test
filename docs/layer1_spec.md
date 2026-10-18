# Layer 1 spec: Systemic Recovery & Readiness (Apple Watch)

Source of truth for the preprocessing in `preprocessing/` and for anyone (person or agent) testing it.
Settings live in `preprocessing/layer1/config.py`; if this document and the config disagree, raise it.

**Objective:** track global autonomic recovery and sleep architecture overnight.
**Timing:** consolidated overnight sleep.

## 1. Pre-process and clean

- Inputs: timestamped sleep stage intervals (`HKCategoryValueSleepAnalysis`), overnight HRV (SDNN), heart rate, Apple's resting heart rate.
- Keep **Apple Watch** records only. Exception: **In Bed** records from the iPhone (or the watch) are kept, for
  time in bed. In Bed from other apps (Oura, sleep apps) is dropped, since it would stretch time in bed.
- A record counts as Apple Watch data when its source name contains "Apple Watch" (`WATCH_SOURCE_KEYWORDS`), and
  In Bed counts as the iPhone's when the name contains "iPhone" (`IN_BED_SOURCE_KEYWORDS`). Known gaps: a
  third-party app named "... for Apple Watch" is counted as the watch, and a watch renamed without those words is
  missed. Matching on the device type instead is planned for the production work.
- Before matching, source names are folded to plain text (Unicode NFKC, invisible zero-width characters removed,
  runs of spaces made one space), so a non-breaking space, a double space or full-width letters still match.
- **Units:** heart rate and resting HR are kept in bpm, HRV in ms. Known other units are converted (count/s to
  count/min, s to ms, `UNIT_FACTORS`). A reading in a unit we don't know is dropped ("Unknown unit") rather than
  guessed. A reading with no unit is taken to be in the usual one.
- **Export zips:** the export is the `.xml` file whose top element is `<HealthData>`, whatever it is called
  (so `export_cda.xml` and Mac `__MACOSX/` copies are skipped). The 4 GB unzipped limit applies to that file only.
  Only the first 1 MB of each `.xml` is read to find it (`EXPORT_PEEK_BYTES`). An export that is damaged,
  encrypted or packed in a way we can't unpack is refused with a message to export again.
- **Dates:** readings dated before 2000 or more than a day in the future are refused (counted as unreadable,
  or a 400 for our app's batches). The pipeline also drops records more than a day ahead.
- Remove exact duplicates and physically impossible values (HR outside 30–220 bpm, resting HR outside 30–120, SDNN outside 5–300 ms).
- Remove sleep pieces shorter than 30 s or longer than 16 h.
- **Overlapping pieces** (two watches, or a stage written on top of another) never count the same minute twice.
  Each overlapping moment goes to one stage: deep, REM and core beat unspecified asleep, which beats awake
  (`SLEEP_STAGE_PRIORITY`). Between equal stages the piece that started first wins. Pieces are trimmed to the parts
  they win.
- **Primary sleep window** = first asleep piece (onset) to last asleep piece (final awakening). Awake time before onset or after final awakening does not count.
- Sleep pieces less than 60 min apart form one session. Each night's **main sleep is its longest session**; other sessions are naps and are ignored.
- A night is labelled by the evening it starts: onset minus 12 h, then take the local date.
  - Known limit: crossing the date line changes the local date by a whole day, so one calendar date can be
    skipped (it shows as a night with no data) or two sleeps can fall on the same date (the longer one is the
    main sleep). This is left as is.
- *Motion-artifact filtering is not possible:* HealthKit only provides processed values, not raw motion signals.

## 2. Core metrics (per night)

| Metric | Definition | Column |
|---|---|---|
| Total Sleep Time | Core + Deep + REM (+ unspecified asleep) minutes inside the window | `tst_min` |
| Time in Bed | iPhone In Bed span (widened to include the sleep window) if present, else onset to final awakening | `tib_min`, `tib_source` |
| Sleep Efficiency | TST ÷ Time in Bed × 100 | `sleep_efficiency_pct` |
| Fragmentation (original spec) | Awake minutes after onset ÷ Time in Bed × 100 | `waso_pct_of_tib` |
| Fragmentation (used) | Awakenings (awake stretches ≥ 1 min, touching pieces merged) per hour of sleep | `fragmentation_per_hr` |
| HRV_night | Mean SDNN of readings inside the window | `hrv_night_ms`, `hrv_ln` = ln(mean) |
| RHR_night | Lowest 30-min rolling average heart rate inside the window (window must be full length and hold ≥ 3 readings) | `rhr_night_bpm` |

Why two fragmentation columns: without In Bed data, time in bed = TST + awake minutes, so the original formula equals 100 − efficiency and adds no information.

## 3. Personal baselines (z-scores)

- Baseline for night *d* = usable values from the **previous 28 calendar nights** (never night *d* itself).
- A z-score exists only when the baseline has **≥ 7** usable values and night *d*'s own value is usable.
- z = (tonight − mean) ÷ SD (sample SD, ddof = 1). SD floor: max(SD, 0.02 × |mean|).
- HRV is log-transformed before z-scoring (`z_hrv` uses `hrv_ln`).
- Signs are not flipped: high `z_rhr` / `z_frag` is the bad direction.

| z column | Value | Gated by |
|---|---|---|
| `z_hrv` | `hrv_ln` | `usable_hrv` |
| `z_rhr` | `rhr_night_bpm` | `usable_rhr` |
| `z_tst` | `tst_min` | `usable_sleep` |
| `z_eff` | `sleep_efficiency_pct` | `usable_sleep` |
| `z_frag` | `fragmentation_per_hr` | `usable_sleep` |

## Missing data and quality

- Every calendar night between the first and last night gets a row, even with no data.
- `usable_sleep`: sleep recorded and TST ≥ 180 min.
- A recorded night shorter than that (`flag_short_sleep`) is kept as a row but is not usable, so it gets no
  z-scores and stays out of every baseline. The app shows it as a short night, with its own wording, rather than
  "no sleep recorded".
- `usable_hrv`: usable sleep and ≥ 1 HRV reading in the window.
- `usable_rhr`: usable sleep, a valid overnight resting HR, and heart rate in ≥ 2 five-minute slots per hour of
  sleep (`HR_COVERAGE_SLOT_MIN`, `MIN_HR_SLOTS_PER_SLEEP_HOUR`). Slots, not readings, so a burst of readings
  in a few minutes doesn't make a night look covered.
- `quality_notes` explains every incomplete night; empty when complete, except the informational
  note "no sleep stages" (older watches), which can appear on an otherwise usable night.

## Daily updates

- Each user picks a daily **update time** (default 8:00, `DEFAULT_UPDATE_TIME`). Last night is processed once
  the clock passes it the next day. Night-shift users pick a later time. Nights with no sleep data get their
  flagged row at the same time.
- **Update now**: the user can tap it earlier. Last night is then processed straight away if its main sleep has
  already ended; tapping before bed never creates tonight's row.
  - Ended means nothing asleep has been recorded for 30 minutes (`UPDATE_NOW_QUIET_MIN = 30`). A tap in the
    middle of the night, before the watch has synced the rest of the sleep, waits instead of processing half a
    night.
  - Only nights before today count, so a nap earlier today never becomes tonight's row.
- Each run processes every ready night not yet processed (catches up skipped days). It also redoes the 2 nights
  processed before (`RECOMPUTE_NIGHTS = 3`), plus every night the previous run processed for the first time if it
  is from the last 3 days (`LATE_DATA_DAYS`), to pick up data that synced late.
- Results must equal processing all received data at once.
- **Late data on the server:** when new readings belong to a night older than the ones a run redoes (data sent in
  pieces, a first sync of history, an import, or data that arrives days late), the server rebuilds that person's
  nights from all their readings, so the rule above holds however late data arrives.
- The standalone daily simulation (`DailyProcessor` on its own, as in the Layer 1 tester's daily replay and the
  Streamlit "Daily updates" tab) only redoes the nights described above. There, a reading more than about 3 days
  late is not picked up.

## 4. Readiness score (0–100): not built yet

Combines the z-scores, fragmentation and duration. Weights to be decided by the team / ML model.
`readiness_label` in the ML table is an empty placeholder for the training label.
