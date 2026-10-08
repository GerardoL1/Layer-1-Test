# Layer 1 spec: Systemic Recovery & Readiness (Apple Watch)

Source of truth for the preprocessing in `preprocessing/` and for anyone (person or agent) testing it.
Settings live in `preprocessing/config.py`; if this document and the config disagree, raise it.

**Objective:** track global autonomic recovery and sleep architecture overnight.
**Timing:** consolidated overnight sleep.

## 1. Pre-process and clean

- Inputs: timestamped sleep stage intervals (`HKCategoryValueSleepAnalysis`), overnight HRV (SDNN), heart rate, Apple's resting heart rate.
- Keep **Apple Watch** records only. Exception: iPhone **In Bed** records are kept (used for time in bed).
- Remove exact duplicates and physically impossible values (HR outside 30–220 bpm, resting HR outside 30–120, SDNN outside 5–300 ms).
- Remove sleep pieces shorter than 30 s or longer than 16 h.
- **Primary sleep window** = first asleep piece (onset) to last asleep piece (final awakening). Awake time before onset or after final awakening does not count.
- Sleep pieces less than 60 min apart form one session. Each night's **main sleep is its longest session**; other sessions are naps and are ignored.
- A night is labelled by the evening it starts: onset minus 12 h, then take the local date.
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
- `usable_hrv`: usable sleep and ≥ 1 HRV reading in the window.
- `usable_rhr`: usable sleep, a valid overnight resting HR, and ≥ 2 HR readings per hour of sleep.
- `quality_notes` explains every incomplete night; empty when complete, except the informational
  note "no sleep stages" (older watches), which can appear on an otherwise usable night.

## Daily updates

- Each user picks a daily **update time** (default 8:00, `DEFAULT_UPDATE_TIME`). Last night is processed once
  the clock passes it the next day. Night-shift users pick a later time. Nights with no sleep data get their
  flagged row at the same time.
- **Update now**: the user can tap it earlier. Last night is then processed straight away if its main sleep has
  already ended; tapping before bed never creates tonight's row.
- Each run processes every ready night not yet processed (catches up skipped days). It also redoes the 2 nights
  processed before (`RECOMPUTE_NIGHTS = 3`), plus every night the previous run processed for the first time if it
  is from the last 3 days (`LATE_DATA_DAYS`), to pick up data that synced late.
- Results must equal processing all received data at once.

## 4. Readiness score (0–100): not built yet

Combines the z-scores, fragmentation and duration. Weights to be decided by the team / ML model.
`readiness_label` in the ML table is an empty placeholder for the training label.
