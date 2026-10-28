"""Trends: one entry per night over the last 14, 28 or 90 nights, plus one-line summaries."""

from datetime import timedelta

from fastapi import APIRouter, HTTPException

from app.core import db
from app.core.json_values import r1
from app.core.urls import USER
from app.readiness.explain import get_explainer
from app.readiness.features import build_features
from app.readiness.model import get_model
from app.readiness.scoring import LOW_BELOW, READY_FROM
from app.readiness.usual import METRICS, usual_range
from app.schemas.trends import Trends
from app.services import processing
from app.services.users import night_rows, require_user

router = APIRouter(prefix=USER, tags=["trends"])

TREND_RANGES = (14, 28, 90)


@router.get("/trends", response_model=Trends, response_model_exclude_unset=True)
def trends(user_id: str, nights: int = 14):
    if nights not in TREND_RANGES:
        raise HTTPException(422, f"nights must be one of {', '.join(map(str, TREND_RANGES))}")
    processing.process_user(user_id)
    with db.connect() as conn:
        require_user(conn, user_id)
    table = night_rows(user_id)
    if table.empty:
        return {"user_id": user_id, "nights": nights, "rows": []}
    last = table["night_date"].iloc[-1]
    model = get_model()
    # Each night's score uses the full history up to that night, not just the nights on screen.
    first = int((table["night_date"] > last - timedelta(days=nights)).to_numpy().argmax())
    rows = []
    for i in range(first, len(table)):
        row = table.iloc[i].to_dict()
        # Trends stays light: the contributions are only on Today.
        result = model.score(build_features(table.iloc[: i + 1]))
        entry = {
            "night_date": row["night_date"].isoformat(),
            "readiness": result.to_api(with_contributions=False),
            "usable_sleep": bool(row["usable_sleep"]),
            "quality_notes": row.get("quality_notes") or None,
            "deep_min": r1(row.get("deep_min")),
            "core_min": r1(row.get("core_min")),
            "rem_min": r1(row.get("rem_min")),
            "unspecified_min": r1(row.get("unspecified_min")),
        }
        for key, col, _label, _unit, zcol, _up in METRICS:
            lo, hi = usual_range(row, col)
            entry[key] = {"value": r1(row.get(col)), "z": r1(row.get(zcol)), "usual_low": lo, "usual_high": hi}
        rows.append(entry)
    return {
        "user_id": user_id,
        "nights": nights,
        "cutoffs": {"low_below": LOW_BELOW, "ready_from": READY_FROM},
        "placeholder": True,
        "rows": rows,
        "summaries": get_explainer().trends(rows),
    }
