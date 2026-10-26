"""
Every number and message the sweat import uses lives here, so the server and the tests
always agree. See docs/layer3_spec.md for why each one is what it is.
"""

# ---------------------------------------------------------------- 1. The Nix export
SUMMARY_SHEET = "Workout Summary"
TIMESERIES_SHEET = "Timeseries Data"
SUMMARY_HEADER = "Data"
TIMESERIES_HEADER = "Minutes"
MISSING_TEXT = ("", "--")

# A real export unpacks to well under 1 MB. Anything far bigger is a mistake or a zip bomb.
# It's checked against the zip's own listing first, then again while reading, since a listing can lie.
MAX_UNZIPPED_BYTES = 20 * 1024 * 1024
# Parts are unpacked this much at a time, so a lying zip can't fill memory in one go.
READ_CHUNK_BYTES = 64 * 1024
# Excel always writes UTF-8 XML. Anything else is refused, so the DOCTYPE check can't be dodged.
XML_ENCODINGS = ("utf-8", "utf8")
# Start of a password-protected (or very old .xls) Excel file, which isn't a zip at all.
OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
# Nix workouts can't be older than this. Also stops an Excel day count like 1 meaning 1899.
EARLIEST_YEAR = 2000
# Bad values are quoted back in error messages, cut to this length.
ERROR_VALUE_MAX_CHARS = 40

# Summary labels we read, by the text before the brackets (lower case) -> our field name.
# Athlete Name, Height, Workout Name and Training Pace are left out on purpose.
SUMMARY_FIELDS = {
    "start time": "start",
    "end time": "end",
    "duration": "duration",
    "nix index": "nix_index",
    "workout type": "workout_type",
    "activity type": "activity_type",
    "weight": "weight",
    "total fluid loss": "fluid_loss",
    "sweat rate": "sweat_rate",
    "total electrolyte loss": "electrolytes",
    "electrolyte loss rate": "electrolyte_rate",
    "total sodium loss": "sodium",
    "sodium loss rate": "sodium_rate",
    "sweat composition": "sweat_composition",
}
REQUIRED_SUMMARY = {"start": "Start Time", "end": "End Time", "fluid_loss": "Total Fluid Loss"}

# Timeseries columns, same matching -> our field name.
TIMESERIES_FIELDS = {
    "minutes": "minute",
    "sweat rate": "sweat_rate",
    "respiration loss rate": "respiration_rate",
    "total fluid loss": "total_fluid",
    "electrolyte loss rate": "electrolyte_rate",
    "total electrolyte loss": "total_electrolytes",
    "sodium loss rate": "sodium_rate",
    "total sodium loss": "total_sodium",
}
REQUIRED_TIMESERIES = {
    "sweat_rate": "Sweat Rate",
    "respiration_rate": "Respiration Loss Rate",
    "total_fluid": "Total Fluid Loss",
}

# ---------------------------------------------------------------- 2. Units
# What kind of quantity each field is, so we know which units it may come in.
FIELD_KIND = {
    "fluid_loss": "volume",
    "sweat_rate": "volume_rate",
    "electrolytes": "mass",
    "electrolyte_rate": "mass_rate",
    "sodium": "mass",
    "sodium_rate": "mass_rate",
    "sweat_composition": "concentration",
    "weight": "body_weight",
    "respiration_rate": "volume_rate",
    "total_fluid": "volume",
    "total_electrolytes": "mass",
    "total_sodium": "mass",
}
# Units as Nix writes them (lower case, spaces removed) -> factor to our stored unit.
# Stored: volume ml, volume_rate L/h, mass mg, mass_rate mg/h, concentration mg/L, body weight kg.
OZ_TO_ML = 29.5735
UNIT_FACTORS = {
    "volume": {"oz": OZ_TO_ML, "ml": 1.0},
    "volume_rate": {"oz/hr": OZ_TO_ML / 1000, "ml/hr": 1 / 1000},
    "mass": {"mg": 1.0},
    "mass_rate": {"mg/hr": 1.0},
    "concentration": {"mg/oz": 1000 / OZ_TO_ML, "mg/ml": 1000.0},
    "body_weight": {"lb": 0.453592, "kg": 1.0},
}
# Which Nix setting a unit means. Metric is more precise (Customary rounds to 0.1 oz).
# A file mixing both counts as the less precise one.
UNIT_SYSTEM = {
    "oz": "customary",
    "oz/hr": "customary",
    "mg/oz": "customary",
    "ml": "metric",
    "ml/hr": "metric",
    "mg/ml": "metric",
}
# Far beyond anything a workout can produce, after conversion to our units. A value over these
# is a broken file, and refusing it keeps huge or infinite numbers out of the database.
PLAUSIBLE_MAX = {
    "volume": 30_000,  # ml, 30 L in one session
    "volume_rate": 10,  # L/h
    "mass": 100_000,  # mg
    "mass_rate": 20_000,  # mg/h
    "concentration": 10_000,  # mg/L
    "body_weight": 1_000,  # kg, only a suggestion anyway
}
UNIT_PRECISION = {"manual": 0, "customary": 1, "metric": 2}

# Weight from the file is only offered as a suggestion, and only inside the same range Settings allows.
WEIGHT_RANGE_KG = (30, 300)

# ---------------------------------------------------------------- 3. Checks (warnings, the import still goes ahead)
# Total fluid loss should be about sweat rate x duration.
FLUID_CHECK_TOLERANCE = 0.15
# ...but Customary rounds to 0.1 oz, so small totals get this much slack too.
FLUID_CHECK_ABS_ML = 5.0
# The timeseries has one row per minute, so its length should match the duration.
MINUTES_CHECK_TOLERANCE = 2
# Duration should match end minus start (the times only have whole minutes).
DURATION_CHECK_TOLERANCE_MIN = 2

# ---------------------------------------------------------------- 4. No sweat detected
# Sweat counts as detected once the sweat rate rises above breathing loss by more than this (L/h).
# Just over one Customary rounding step (0.1 oz/hr is about 0.003 L/h), so rounding alone never counts.
SWEAT_ABOVE_RESPIRATION_L_H = 0.004
# When a minute has no breathing value, a sweat rate above this (L/h) still counts as sweat.
# Breathing loss alone is a few tens of ml/h, so this is clearly sweating.
SWEAT_RATE_CLEARLY_L_H = 0.1

# ---------------------------------------------------------------- Messages
# Shown as is on the "We couldn't read this file" screen.
EXPORT_HINT = "Use the Excel file from Export Workout in the Nix app. It ends in .xlsx."
ERR_NOT_XLSX = "This isn't an Excel file. " + EXPORT_HINT
ERR_PDF = "This is a PDF, not the Excel export. Export the workout again and pick the .xlsx file."
ERR_PROTECTED = "This file is password-protected or in the old Excel format, so we can't read it. " + EXPORT_HINT
ERR_IMPLAUSIBLE = "'{label}' is far higher than a workout could produce ('{value}'). Export the workout again."
ERR_DAMAGED = "This file is damaged or can't be opened. Export the workout again from the Nix app."
ERR_TOO_BIG = "This file is far bigger than a Nix export. " + EXPORT_HINT
ERR_MISSING_SHEET = "This file has no '{sheet}' sheet, so it isn't a Nix workout export. " + EXPORT_HINT
ERR_MISSING_HEADER = "The '{sheet}' sheet doesn't have its '{header}' heading. Export the workout again."
ERR_MISSING_ROW = "This file has no '{label}'. Export the workout again from the Nix app."
ERR_MISSING_COLUMN = "The '{sheet}' sheet has no '{label}' column. Export the workout again from the Nix app."
ERR_UNKNOWN_UNIT = "We don't recognise the unit in '{label}'. Set Nix to Metric or Customary and export again."
ERR_BAD_NUMBER = "We couldn't read the number for '{label}' ('{value}')."
ERR_NEGATIVE = "'{label}' can't be negative ('{value}')."
ERR_BAD_DATE = "We couldn't read the {label} ('{value}')."
ERR_END_BEFORE_START = "The workout ends before it starts. Export the workout again from the Nix app."

WARN_FLUID_MISMATCH = (
    "Total fluid loss ({fluid:.0f} ml) doesn't match the sweat rate over the workout (about {expected:.0f} ml)."
)
WARN_MINUTES_MISMATCH = "The minute-by-minute data covers {rows} minutes, but the workout lasted {minutes:.0f}."
WARN_DURATION_UNREADABLE = "We couldn't read the duration ('{value}'), so it comes from the start and end times."
WARN_DURATION_MISMATCH = "The duration ({duration:.0f} min) doesn't match the start and end times ({span:.0f} min)."
WARN_NO_SWEAT = (
    "Nix didn't pick up any sweat this session. Only breathing loss was recorded, so this won't count as sweat data."
)
