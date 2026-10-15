"""Update now: start a processing run, which handles last night early once its sleep has ended."""

from fastapi import APIRouter

from app.core import db
from app.core.urls import USER
from app.schemas.processing import ProcessingRun
from app.services import processing
from app.services.users import require_user

router = APIRouter(prefix=USER, tags=["processing"])


@router.post("/processing-runs", response_model=ProcessingRun)
def create_processing_run(user_id: str):
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
