"""Update now: process last night early, once its sleep has ended."""

from fastapi import APIRouter

from app.core import db
from app.services import processing
from app.services.users import require_user

router = APIRouter(prefix="/api", tags=["processing"])


@router.post("/update-now")
def update_now(user_id: str):
    with db.connect() as conn:
        require_user(conn, user_id)
    report = processing.process_user(user_id, update_now=True)
    if report is None or not report.new_nights:
        return {
            "processed": False,
            "new_nights": [],
            "message": "Nothing new to process. Last night's sleep hasn't ended or hasn't synced yet.",
        }
    return {"processed": True, "new_nights": [d.isoformat() for d in report.new_nights], "message": "Updated."}
