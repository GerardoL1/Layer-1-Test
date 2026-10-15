"""Profile: usual ranges, how many nights are recorded, data sources and settings."""

from fastapi import APIRouter

from app.core import db
from app.core.json_values import clean
from app.core.urls import USER
from app.readiness.usual import BASE_COLUMN, METRICS, usual_range
from app.schemas.profile import Profile
from app.services import processing
from app.services.users import last_run, night_rows, read_settings, require_user
from layer1 import config as C

router = APIRouter(prefix=USER, tags=["profile"])


@router.get("/profile", response_model=Profile)
def profile(user_id: str):
    processing.ensure_processed(user_id)
    with db.connect() as conn:
        require_user(conn, user_id)
        run = last_run(conn, user_id)
        sources = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT source FROM samples WHERE user_id = ? AND source IS NOT NULL "
                "UNION SELECT DISTINCT source FROM sleep_stages WHERE user_id = ? AND source IS NOT NULL",
                (user_id, user_id),
            )
        ]
    table = night_rows(user_id)
    usual = []
    if not table.empty:
        latest = table.iloc[-1].to_dict()
        for key, col, label, unit, _z, _up in METRICS:
            lo, hi = usual_range(latest, col)
            base = BASE_COLUMN.get(col, col)
            usual.append(
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "usual_low": lo,
                    "usual_high": hi,
                    "baseline_nights": clean(latest.get(f"{base}_base_n")),
                    "placeholder": True,
                }
            )
    return {
        "user_id": user_id,
        "settings": read_settings(user_id),
        "nights_total": int(len(table)),
        "nights_usable": int(table["usable_sleep"].sum()) if len(table) else 0,
        "first_night": table["night_date"].iloc[0].isoformat() if len(table) else None,
        "last_night": table["night_date"].iloc[-1].isoformat() if len(table) else None,
        "baseline_window_nights": C.BASELINE_WINDOW_NIGHTS,
        "baseline_min_nights": C.BASELINE_MIN_NIGHTS,
        "usual_ranges": usual,
        "sources": sorted(sources),
        "last_update_local": run["sync_local"] if run else None,
    }
