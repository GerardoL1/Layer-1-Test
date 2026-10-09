"""
PLACEHOLDER wording for Today's verdict and reason, and the one-line Trends summaries.

Simple templates built from the Worse / Usual / Better labels until the LLM writes
these. Keep the inputs and outputs the same and only this file needs replacing.
"""

VERDICT = {
    "low": "Take a recovery day.",
    "moderate": "Train, but keep it moderate.",
    "ready": "Good to train hard.",
    "building_baseline": "Still learning your normal.",
    "no_data": "No sleep recorded for this night.",
}

ADVICE = {
    "low": "Keep today light: walking, mobility, an early night.",
    "moderate": "A normal session is fine. Leave the hardest work for another day.",
    "ready": "Your body looks recovered.",
}

# What each metric being worse or better means, in plain words.
PHRASES = {
    "hrv": {"worse": "your HRV is below your usual", "better": "your HRV is above your usual"},
    "rhr": {"worse": "your resting heart rate stayed higher overnight",
            "better": "your resting heart rate was lower than usual overnight"},
    "sleep": {"worse": "you slept less than usual", "better": "you slept more than usual"},
    "awakenings": {"worse": "you woke more often", "better": "you woke less than usual"},
}


def _join(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


def today_text(status: str, metrics: list[dict], baseline_nights: int | None, min_nights: int) -> tuple[str, str]:
    """Returns (verdict, reason) for Today."""
    verdict = VERDICT.get(status, "")
    if status == "no_data":
        return verdict, "Wear your watch to bed with Sleep tracking on, and the next night will show here."
    if status == "building_baseline":
        have = baseline_nights or 0
        return verdict, (f"Your score starts after {min_nights} nights of sleep. "
                         f"{have} of {min_nights} so far.")
    by_key = {m["key"]: m.get("direction") for m in metrics}
    worse = [PHRASES[k]["worse"] for k in PHRASES if by_key.get(k) == "worse"]
    better = [PHRASES[k]["better"] for k in PHRASES if by_key.get(k) == "better"]
    if worse:
        first = _join(worse)
        reason = first[0].upper() + first[1:] + "."
    elif better:
        first = _join(better)
        reason = first[0].upper() + first[1:] + "."
    else:
        reason = "Your numbers are within your usual range."
    return verdict, f"{reason} {ADVICE.get(status, '')}".strip()


def _run(values: list, test) -> int:
    """How many of the most recent values in a row pass test (missing nights are skipped)."""
    n = 0
    for v in reversed([v for v in values if v is not None]):
        if not test(v):
            break
        n += 1
    return n


def _nights(n: int) -> str:
    return "last night" if n == 1 else f"the last {n} nights"


def band_summary(rows: list[dict], key: str) -> str | None:
    """'Below your usual range for the last 5 nights.' for one metric."""
    points = [r[key] for r in rows]
    flags = []
    for p in points:
        if p["value"] is None or p["usual_low"] is None:
            flags.append(None)
        else:
            flags.append("below" if p["value"] < p["usual_low"] else "above" if p["value"] > p["usual_high"] else "in")
    known = [f for f in flags if f is not None]
    if not known:
        return None
    last = known[-1]
    n = _run(flags, lambda f: f == last)
    if last == "in":
        return "Within your usual range." if n >= 3 else "Back within your usual range."
    return f"{last.capitalize()} your usual range for {_nights(n)}."


def readiness_summary(rows: list[dict]) -> str | None:
    statuses = [r["readiness"]["status"] for r in rows if r["readiness"]["score"] is not None]
    if not statuses:
        return None
    last = statuses[-1]
    n = _run(statuses, lambda s: s == last)
    word = {"low": "Low", "moderate": "Moderate", "ready": "Ready"}[last]
    before = statuses[-n - 1] if len(statuses) > n else None
    if before and n <= 7:
        was = {"low": "Low", "moderate": "Moderate", "ready": "Ready"}[before]
        direction = "Slid" if ["low", "moderate", "ready"].index(last) < ["low", "moderate", "ready"].index(before) else "Climbed"
        return f"{direction} from {was} into {word} over {_nights(n)}."
    return f"{word} for {_nights(n)}."


def sleep_summary(rows: list[dict]) -> str | None:
    """Compares the last 7 nights with the 7 before."""
    sleep = [r["sleep"]["value"] for r in rows]
    recent = [v for v in sleep[-7:] if v is not None]
    before = [v for v in sleep[-14:-7] if v is not None]
    if len(recent) < 3 or len(before) < 3:
        return None
    diff = sum(recent) / len(recent) - sum(before) / len(before)
    if abs(diff) < 15:
        return "About the same amount of sleep as the week before."
    amount = f"{round(abs(diff) / 60, 1):g} hours" if abs(diff) >= 90 else f"{round(abs(diff) / 5) * 5} min"
    return f"About {amount} {'less' if diff < 0 else 'more'} sleep a night this week than the week before."


def trends_summaries(rows: list[dict]) -> dict:
    return {
        "readiness": readiness_summary(rows),
        "hrv": band_summary(rows, "hrv"),
        "rhr": band_summary(rows, "rhr"),
        "sleep": sleep_summary(rows),
        "efficiency": band_summary(rows, "efficiency"),
    }
