"""
Every number the preprocessing uses lives here, so the server version, the app,
and this test platform all use identical settings. Change a value here, rerun,
and the whole pipeline follows.
"""

# ---------------------------------------------------------------- 1. Load
# HealthKit record types we keep, and the short names used everywhere else.
QUANTITY_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
}
SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
SLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep_unspecified",
    "HKCategoryValueSleepAnalysisAsleep": "asleep_unspecified",  # older iOS name
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
}
ASLEEP_STAGES = ("core", "deep", "rem", "asleep_unspecified")

# Only process this many days back from the newest record (None = everything).
DEFAULT_DAYS = 90

# ---------------------------------------------------------------- 2. Clean
# A record counts as "from the watch" if its source name contains one of these.
WATCH_SOURCE_KEYWORDS = ("Apple Watch",)
# "In Bed" usually comes from the iPhone's Sleep Schedule, so it is kept from any source.
IN_BED_ANY_SOURCE = True

# Values outside these ranges are physically implausible and are dropped.
VALID_RANGES = {
    "heart_rate": (30, 220),          # bpm
    "resting_heart_rate": (30, 120),  # bpm
    "hrv_sdnn": (5, 300),             # ms
}
# Sleep segments shorter than this are treated as noise; longer than this are errors.
MIN_SLEEP_SEGMENT_SEC = 30
MAX_SLEEP_SEGMENT_HOURS = 16

# ---------------------------------------------------------------- 3. Sleep window
# Sleep pieces separated by more than this gap belong to different sleep sessions.
SESSION_GAP_MIN = 60
# A night is labelled by the evening it starts: onset minus this many hours, then take the date.
# 23:30 -> same date; 01:30 -> previous date. Daytime naps land on the following night's label.
NIGHT_SHIFT_HOURS = 12
# The main sleep of a night is its longest session; every other session that night is a nap.
# "In Bed" records count toward a night if they start or end within this many hours of the main sleep.
IN_BED_MATCH_HOURS = 3

# ---------------------------------------------------------------- 4. Nightly metrics
# An awake stretch inside the sleep window counts as an awakening if it lasts at least this long.
MIN_AWAKENING_MIN = 1.0
# Overnight resting heart rate = lowest rolling average over this many minutes of sleep.
RHR_WINDOW_MIN = 30
# ...and that window needs at least this many heart rate readings to count.
RHR_MIN_SAMPLES_IN_WINDOW = 3
# HRV is skewed, so z-scores use the natural log of the nightly mean.
HRV_LOG_TRANSFORM = True

# ---------------------------------------------------------------- 5. Missing data / quality
MIN_TST_FOR_USABLE_MIN = 180        # nights with less sleep are flagged short_sleep
MIN_HR_SAMPLES_PER_SLEEP_HOUR = 2   # fewer readings than this -> low_hr_coverage

# ---------------------------------------------------------------- 6. Baselines and z-scores
# Personal baseline = previous nights only (tonight is never in its own baseline).
BASELINE_WINDOW_NIGHTS = 28         # look back this many calendar nights (spec: 14 to 30)
BASELINE_MIN_NIGHTS = 7             # need at least this many usable values before a z-score is shown
# Metrics that get a baseline and z-score: column -> (z-score column, label, which usable flag gates it).
# z = (tonight - baseline mean) / baseline SD. For resting HR and fragmentation, higher is worse;
# the sign is left as-is here, and flipping happens when the readiness score is built.
ZSCORE_METRICS = {
    "hrv_ln": ("z_hrv", "HRV (log of nightly mean SDNN)", "usable_hrv"),
    "rhr_night_bpm": ("z_rhr", "Overnight resting HR", "usable_rhr"),
    "tst_min": ("z_tst", "Total sleep time", "usable_sleep"),
    "sleep_efficiency_pct": ("z_eff", "Sleep efficiency", "usable_sleep"),
    "fragmentation_per_hr": ("z_frag", "Fragmentation (awakenings per hour)", "usable_sleep"),
}
# If a baseline's standard deviation is below this share of its mean, use this floor instead,
# so a very steady baseline doesn't turn tiny changes into huge z-scores.
MIN_SD_FRACTION_OF_MEAN = 0.02

# ---------------------------------------------------------------- Daily updates (incremental processing)
# When each night is processed. The user picks a daily update time (in Profile); last night is
# processed once the clock passes it the next day. (8, 0) = 8:00 am. Night-shift users pick a later
# time. Nights with no sleep data get their flagged row at the same time.
DEFAULT_UPDATE_TIME = (8, 0)
# The user can also tap "Update now" earlier: last night is then processed straight away, as long
# as its main sleep has ended (so tapping before bed never creates tonight's row early).
# "Recompute the last N nights": each run processes the newest night(s) AND redoes the
# N - 1 nights processed just before, to pick up data that synced late (HRV, sleep stages and
# Apple's daily resting HR can arrive a day or more after waking). 1 = never redo anything.
# 3 because with a morning update time, a late reading can land two updates later.
RECOMPUTE_NIGHTS = 3
# Each run also redoes the nights the previous run processed for the first time (so a
# catch-up's older nights get their late data too), but only those from the last few days.
LATE_DATA_DAYS = 3
# Simulation only: the hour of day the phone syncs in the "Daily updates" tab and the tests
# (a morning sync, to match automatic background sync).
SIM_SYNC_HOUR = 8
