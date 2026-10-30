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
- A cell longer than `MAX_CELL_CHARS`. One shared string can fill thousands of cells, so reading it over and
  over would tie up the server.
- A minute number that isn't a whole number from 0 to `MAX_MINUTES` (one day), and any number so long it reads
  as infinity. An infinite Nix index is left out like an unreadable one.
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
- Duration differs from end minus start by more than `DURATION_CHECK_TOLERANCE_MIN`. The real times are then
  used for the session length, since a far-off Duration is a broken file.
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

## 5. One sweat session per workout (`server/app/services/sweat.py`)

One row per import or manual entry, and **at most one per workout**. Manual entry uses the same fields, so the
model doesn't care where the numbers came from. Typed-in numbers are in ml, mg and L/h (the app converts from the
person's Units first) and count as sweat data. They have no times of their own: they always use their workout's
current start and end, so they follow it if the workout is moved. The smallest values are 1 ml, 1 mg and 0.01 L/h,
so nothing typed in is stored as 0.

`user_id`, `id`, `workout_id`, `source` (nix, manual), start and end (UTC ms plus UTC offset in minutes),
`duration_min`, `fluid_loss_ml`, `sweat_rate_l_h`, `sodium_mg`, `sodium_rate_mg_h`, `electrolytes_mg`,
`electrolyte_rate_mg_h`, `sweat_composition_mg_l`, `nix_index`, `workout_type`, `sweat_detected`,
`unit_system` (metric, customary, or manual), `warnings`, `imported_at_ms`.

Tables `sweat_sessions` (keyed by user and id, one per workout) and `sweat_minutes` (Nix's per-minute series).
Ids are `nix-<start ms>-<end ms>` and `manual-<workout id>`. The raw `.xlsx` is not kept.

**Time zone:** the local times become real times with the person's **Time zone** setting for that date (so
daylight saving is right). Without one, the offset of their newest reading is used, then the phone's offset sent
with the upload (`tz_offset_min`). With none of these the import is refused and asks for a time zone. The times
then follow the same rules as workouts: not before 2000, not more than a day ahead, at most 24 hours long, and the
real end can't be before the real start. A session whose real start and end are the same is refused with a 400.

**Clock changes** (with a Time zone setting):
- A time in the hour skipped when clocks go forward doesn't exist, so the file is refused with a plain 400.
- A time in the hour repeated when clocks go back has two possible offsets. The pair of offsets whose length best
  fits the file's Duration wins, and between equal fits the one that overlaps a workout (else summer time).
- The reader lets an end be up to an hour before the start in local time (`DST_BACKWARD_MAX_MIN`), since 1:50 AM
  summer time to 1:10 AM winter time is a real 20 minutes. The server then checks the real times.
- The duration and minute-count warnings are worked out again with the real times, so a clock change doesn't
  look like a wrong duration.

**Saving is safe to repeat at the same moment** (a double tap): the save takes the database's write lock before
looking at what's already saved, so the second save sees the first.

**More precise data wins.** Precision: Metric Nix, then Customary Nix, then typed in. When a workout already has
sweat data (or the same file was saved to another workout):
- more precise new data replaces it (`replaces_less_precise` in the preview)
- less precise new data is refused with a 409, and the app says the more precise data was kept
  (`keeps_more_precise`)
- the same precision replaces it (`replaces`), and the very same file again changes nothing (`same`). Saving it again leaves the saved row as it is, import time included.

**Real sweat data beats breathing-only data** (decided 2026-10-26), before precision is looked at:
- a Nix file where no sweat was picked up never replaces a session that has sweat data, typed in or Nix. It's
  refused with a 409 (`keeps_sweat_data`, "the sweat data was kept")
- sweat data (typed in or Nix) always replaces a breathing-only session (`replaces`)
- between two breathing-only files, precision decides as above.
- a sweat file only races for precision against sweat data. A breathing-only copy of the same workout loses
  anyway, so it can't make a sweat file look less precise and get it refused.

## 6. Matching to a workout, and the API

- The session is matched to the workout (Layer 1 tab's table) it overlaps most in time.
- No overlap: the preview lists workouts within `NEARBY_DAYS` (7), closest first, at most 5, and the person picks
  one or saves the file as a new workout. A new workout uses source `manual`, the type from the file, the times
  from the file, and an id built from the start time (`nix-<start ms>`), so sending it again can't make a second
  workout. If a workout with that id already exists, the file is saved to it as it is, never changing it. The
  precision check runs first, so a refused file never leaves an empty workout behind.
- The upload returns a **preview** and saves nothing. **Save** sends the same file again with the chosen
  workout. The server never holds unsaved health data between the two steps.
- The preview also offers the file's weight as a suggestion, only when Settings has no weight.

| Endpoint (under `/api/v1/users/{user_id}`) | Does |
|---|---|
| `POST /sweat/nix/preview` (file, `tz_offset_min`, optional `workout_id` or `new_workout`) | Numbers, matched workout, nearby workouts, and what saving to the matched (or given) workout would do: `existing`, plus `moves_from_workout` when the same file is saved on another workout and saving moves it. Saves nothing. The app asks again whenever the person picks a workout |
| `POST /sweat/nix` (file, `tz_offset_min`, `workout_id` or `new_workout`) | Saves to the picked workout, a new one, or the matched one. 400 if none, 409 if less precise |
| `PUT /workouts/{workout_id}/sweat` | Typed-in numbers (`fluid_loss_ml`, optional `sodium_mg`, `sweat_rate_l_h`) |
| `GET /workouts/{workout_id}/sweat` | The workout's sweat session, 404 if it has none |
| `GET /sweat/sessions?days=` | Sessions of workouts started in the last N days (for the SWEAT tags on Train) |
| `GET /sweat/daily?nights=14\|28\|90` | Sweat per day for the Trends chart, by the day the workout started, plus a placeholder summary |

Unreadable files get a 400 with the message from section 3. Uploads are limited to 5 MB (`MAX_NIX_UPLOAD_BYTES`).
The upload routes read the form themselves: no file part (or one sent without a filename) gets "Choose the Nix file
to upload.", and an odd or oversized text field gets a plain 400. Nothing from the upload is ever echoed back.
An unknown person gets 404 before the file is read.

## 7. For the readiness model and Today

- **Per-day table** (`daily_sweat_table`): `person_id`, `night_date`, `fluid_loss_pct_bw_1d`, `sodium_mg_1d`,
  `fluid_loss_pct_bw_2d`, `sodium_mg_2d`, `has_sweat_data`. Fluid loss as a share of body weight is
  `fluid_loss_ml` ÷ (`weight_kg` × 1000) × 100, Nix's total, which includes breathing. The 1d window is sessions
  that ended between the previous morning's update time and this night's morning (the next day at the update
  time), so mornings never overlap and each session counts for one night. The 2d window starts a day earlier.
  Only sessions where sweat was detected count, and `has_sweat_data` is about the 2d window. Missing stays empty
  (NaN), never 0. Sodium counts only when every sweaty session in the window has it, the same rule as Today's
  hydration panel and the Trends chart, since a total from some of them would look complete but isn't. It uses today's weight from Settings, since weight has no history yet. It joins the readiness
  training table on the night it leads into. Adding it to `server/export_training_table.py` is for the Layer 1 tab.
- Layer 3 may later be a low-weight readiness input (proposed cap ±5 points, still open). It enters only through
  `server/app/readiness/features.py`, which the Layer 1 tab owns.
- **Hydration line on Today:** `hydration_line(user_id, night_date)` returns the line, or None, for the morning
  after that night, for example "Yesterday's run cost about 0.7 L of sweat. Drink a little more than usual this
  morning." It uses the 1d window, only sweat-detected sessions, nothing under `HYDRATION_MIN_ML` (250 ml), the
  workout's type ("workouts" for more than one, lower case unless it's all capitals like HIIT), and litres or
  ounces from the person's Units. It says "This morning's" when the workouts started that morning, before the
  update time, else "Yesterday's". The Layer 1 tab
  wires it into `/today`. The wording and the advice are placeholders until the team decides them.
