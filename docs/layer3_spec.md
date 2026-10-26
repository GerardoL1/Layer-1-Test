# Layer 3 spec: Sweat (Nix biosensor)

Source of truth for the sweat import in `preprocessing/layer3/` and the server routes built on it.
Settings live in `preprocessing/layer3/config.py`. If this document and the config disagree, raise it.

**Objective:** record how much fluid and sodium each workout cost, so the app can suggest how to rehydrate and
the readiness model can (optionally, with low weight) use it.
**Timing:** per workout. Imported after the workout, or typed in by hand.

Layer 3 doesn't use any Layer 2 (patch) data. It needs the Layer 1 tab's workouts table (to attach a session to
a workout) and two settings: time zone and `weight_kg`.

## 1. The Nix export (.xlsx)

In the Nix app: Insights > Workouts > pick the workout > Export Workout, then save to Files. The file is an
Excel workbook. Checked against two real exports of the same workout (one per Nix unit setting).

- Two sheets, found by name: **Workout Summary** and **Timeseries Data**. Both are required.
- Column A and row 1 are empty, tables start at B2. Both sheets have many empty formatted rows after the data.
- Most numbers are stored as **text** ("2.1"). Minutes and Nix Index are real numbers. Both are accepted.
- `--` and an empty cell mean missing.
- Numbers are plain digits with an optional decimal part and thousands commas (`1,150`), as Nix writes them.
  Signs, exponents (`1e3`), underscores and non-ASCII digits are refused.
- If two sheets share a name, the first one is used. Two rows with the same label: the first one is used.

**Workout Summary:** a header row `Data | Value`, then one row per field. Rows are found by their label, not
their position. A label is matched on the text before the brackets (trimmed, any case), and the unit is the text
inside the brackets.

| Label | Customary unit | Metric unit | Used for |
|---|---|---|---|
| Athlete Name | | | **Never read.** Personal, not needed |
| Workout Name | | | Not stored |
| Height | ft | cm | Not read |
| Weight | lb | kg | Only a suggestion when the person has no weight in Settings, never stored |
| Start Time, End Time | | | **Required** |
| Duration | | | `HH:MM:SS`. Anything else: end minus start is used, with a warning |
| Nix Index | | | Stored as is. Left out (not an error) if it isn't a plain number |
| Workout Type, Activity Type | | | Workout type (Activity Type if Workout Type is missing) |
| Total Fluid Loss | oz | ml | **Required** |
| Sweat Rate | oz/hr | ml/hr | |
| Total Electrolyte Loss | mg | mg | |
| Electrolyte Loss Rate | mg/hr | mg/hr | |
| Total Sodium Loss | mg | mg | |
| Sodium Loss Rate | mg/hr | mg/hr | |
| Sweat Composition | mg/oz | mg/ml | |
| Training Pace | | | Not read |

**Timeseries Data:** a header row starting with `Minutes` (a unit after it, like `Minutes (min)`, is fine), then
one row per minute. Reading stops at the first
empty Minutes cell. "Total" columns are running totals. Columns are found by their header label.

| Column | Required |
|---|---|
| Minutes | yes |
| Sweat Rate (oz/hr or ml/hr) | yes |
| Respiration Loss Rate (oz/hr or ml/hr) | yes |
| Total Fluid Loss (oz or ml) | yes |
| Electrolyte Loss Rate (mg/hr), Total Electrolyte Loss (mg), Sodium Loss Rate (mg/hr), Total Sodium Loss (mg) | no |

**Dates:** `Oct 25, 2026 at 2:55 PM` (as exported, with a narrow no-break space before PM) and
`May 27, 2025, 12:42 PM` (the style in Nix's guide). Any kind of space is accepted (invisible zero-width
characters are dropped), and a 24-hour time without AM/PM too. Month names are read in English whatever the
computer's language. An Excel date cell (a day count) is read too. Dates before 2000 (`EARLIEST_YEAR`) are refused.
The file has **no time zone**: the times are the phone's local time.

## 2. Units

Nix has a Customary / Metric setting. Only the units in the labels change, everything else in the file is the
same. Units are matched in any case, with spaces ignored. Stored values always use one unit, whatever the file:

| From | To (stored) | Factor |
|---|---|---|
| oz | ml | × 29.5735 |
| ml | ml | × 1 |
| oz/hr | L/h | × 0.0295735 |
| ml/hr | L/h | ÷ 1000 |
| mg/oz | mg/L | ÷ 0.0295735 |
| mg/ml | mg/L | × 1000 |
| mg, mg/hr | mg, mg/h | × 1 |
| lb | kg | × 0.453592 |
| kg | kg | × 1 |

- A unit we don't know is an error that names the label. We never guess. A required field without a unit is the
  same error, and so is a unit written outside round brackets (`Total Fluid Loss ml`, `[ml]`).
- A converted value above `PLAUSIBLE_MAX` (for example 30 L of fluid or 10 L/h) is refused as far higher than a
  workout could produce. This also keeps infinite numbers out.
- `unit_system` is metric or customary from the units in the file. A file mixing both counts as customary, the
  less precise one.
- An unknown Weight unit just means no weight suggestion, since weight isn't needed for the import.
- The app shows numbers in the person's **Units** setting (metric or imperial). Storage doesn't change with it.
- Metric files are more precise (Customary rounds to 0.1 oz, about 3 ml). The export steps in the app say
  "Set Nix to Metric for the most accurate numbers."

## 3. Checks

**Errors** (the file is refused, with a plain message for the "We couldn't read this file" screen):
- Not a real `.xlsx`: a PDF or anything else renamed. A password-protected or old `.xls` file has its own message.
- A damaged file: anything that goes wrong while unpacking or reading the workbook. The server never answers a
  broken file with a 500.
- A file that unpacks to more than `MAX_UNZIPPED_BYTES`. This is checked against the zip's listing first, then
  counted while unpacking (a chunk at a time), since a crafted zip can lie about its sizes.
- XML Excel never writes: anything other than UTF-8, or a DOCTYPE or ENTITY.
- A missing sheet, a missing `Data` or `Minutes` header, a missing required row or column.
- A unit we don't know (names the label), a number we can't read, a negative number (including `-0`), or a value
  far beyond a workout.
- A date we can't read or before 2000, or an end before the start.
- Bad values are quoted in the message, cut to 40 characters.
- Over the upload size limit (the server's `limits.py`, batch 2).

**Warnings** (the import goes ahead, the warning is stored and shown):
- Total fluid loss doesn't match sweat rate × duration within ±15% (`FLUID_CHECK_TOLERANCE`), allowing
  `FLUID_CHECK_ABS_ML` for rounding on small totals.
- The number of minutes in the timeseries differs from the duration by more than `MINUTES_CHECK_TOLERANCE`.
- Duration differs from end minus start by more than `DURATION_CHECK_TOLERANCE_MIN`.
- Duration isn't `HH:MM:SS`, so end minus start was used instead.

## 4. No sweat detected

Nix only counts sweat once it starts (often after about 15 minutes), and in a cool gym it may pick up none at all.

- `sweat_detected = false` when the sweat rate never rises above the respiration loss rate in any minute **and**
  total electrolyte and total sodium loss are 0 (or missing).
- "Rises above" means by more than `SWEAT_ABOVE_RESPIRATION_L_H` (0.004 L/h), just over one Customary rounding
  step (0.1 oz/hr), so rounding alone never counts as sweat.
- A minute with no respiration value counts as sweat when its sweat rate is above `SWEAT_RATE_CLEARLY_L_H`
  (0.1 L/h). Breathing loss alone is a few tens of ml/h.
- Then fluid loss and sweat rate are what Nix recorded (breathing loss only), and sodium, electrolytes, their rates
  and sweat composition are stored as **missing (null), never 0**.
- These sessions are kept and shown, with a warning on "Check your import": *Nix didn't pick up any sweat this
  session. Only breathing loss was recorded, so this won't count as sweat data.* They never count as sweat data
  for the readiness model.

## 5. One sweat session (what's stored, batch 2)

One row per import or manual entry. Manual entry uses the same fields, so the model doesn't care where the
numbers came from.

`user_id`, `id`, `workout_id`, `source` (nix, manual), start and end (UTC ms plus UTC offset in minutes),
`duration_min`, `fluid_loss_ml`, `sweat_rate_l_h`, `sodium_mg`, `sodium_rate_mg_h`, `electrolytes_mg`,
`electrolyte_rate_mg_h`, `sweat_composition_mg_l`, `nix_index`, `workout_type`, `sweat_detected`,
`unit_system` (metric, customary, or manual), `warnings`, `imported_at_ms`.

The per-minute series is kept in its own table (minute, sweat and respiration rate, running totals).
The raw `.xlsx` is not kept.

**Time zone:** the local times become real times with the person's **Time zone** setting for that date (so
daylight saving is right). Without one, the offset of their newest reading is used, then the phone's offset sent
with the upload.

**The same session twice** (same source, start and end): the more precise file wins. A Metric file replaces a
Customary one, a Customary file never replaces a Metric one, and the same file again changes nothing.

## 6. Matching to a workout (batch 2)

- The session is matched to the workout (Layer 1 tab's table) it overlaps most in time.
- No overlap: the preview lists nearby workouts, closest first, and the person picks one or saves the file as a
  new workout. A new workout uses source `manual`, the type from the file, the times from the file, and an id
  built from the start time, so sending it again can't make a second workout.
- The upload returns a **preview** and saves nothing. **Save** sends the same file again with the chosen
  workout. The server never holds unsaved health data between the two steps.

## 7. For the readiness model and Today (batch 2)

- **Per-day table:** `person_id`, local date, fluid loss as a share of body weight (`fluid_loss_ml` ÷
  (`weight_kg` × 1000) × 100, Nix's total, which includes breathing), `sodium_mg`, `has_sweat_data`. Uses the
  workouts of the last 1 to 2 days that ended before the morning update time, and only sessions where sweat was
  detected. Missing stays empty, never 0. It joins the readiness training table on the night it leads into.
- Layer 3 may later be a low-weight readiness input (proposed cap ±5 points, still open). It enters only through
  `server/app/readiness/features.py`, which the Layer 1 tab owns.
- **Hydration line on Today:** a service function returns the line, or nothing, for a person and night, for
  example "Yesterday's run cost about 0.9 L of sweat. Drink a little more than usual this morning." The Layer 1
  tab wires it into `/today`. The rehydration advice is a placeholder until the team decides it.
