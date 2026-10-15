"""
PLACEHOLDER readiness score: an equal-weight average of the z-scores and its 40 / 70 cut-offs.
Not decided yet, so don't tune these numbers without the team.
"""

import pandas as pd

# +1 means a higher value is better, -1 means higher is worse.
READINESS_SIGNS = {"z_hrv": 1, "z_rhr": -1, "z_tst": 1, "z_eff": 1, "z_frag": -1}
READINESS_CENTER, READINESS_POINTS_PER_SD = 50, 10
LOW_BELOW, READY_FROM = 40, 70

READINESS_METHOD = (
    "Placeholder: 50 + 10 x the average of the available z-scores "
    "(HRV, sleep time and efficiency count up, resting HR and fragmentation count down), "
    "clipped to 0-100. Weights and cut-offs are not decided yet."
)


def readiness(row) -> dict:
    zs = [sign * row[z] for z, sign in READINESS_SIGNS.items() if pd.notna(row.get(z))]
    if not zs:
        # No score: still learning the person's normal, a recorded night that was too short
        # (kept out of the baselines, so there's nothing to compare), or no sleep at all.
        if row.get("usable_sleep"):
            status = "building_baseline"
        elif pd.notna(row.get("tst_min")) and row.get("flag_short_sleep"):
            status = "short_sleep"
        else:
            status = "no_data"
        score = None
    else:
        score = int(round(min(100, max(0, READINESS_CENTER + READINESS_POINTS_PER_SD * sum(zs) / len(zs)))))
        status = "low" if score < LOW_BELOW else "moderate" if score < READY_FROM else "ready"
    return {"score": score, "status": status, "z_count": len(zs), "placeholder": True}
