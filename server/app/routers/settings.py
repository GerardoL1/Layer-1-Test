"""Reading and changing a person's settings."""

import json

from fastapi import APIRouter

from app.core import db
from app.schemas.settings import Settings
from app.services.users import read_settings
from layer1 import config as C

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def get_settings(user_id: str):
    return read_settings(user_id)


@router.put("/settings")
def put_settings(user_id: str, settings: Settings):
    """Changes only the fields that were sent. A new user is created by their first settings or data."""
    changes = settings.model_dump(exclude_unset=True)
    if "training_days" in changes and changes["training_days"] is not None:
        changes["training_days"] = json.dumps(changes["training_days"])
    if changes.get("update_time", "") is None:
        h, m = C.DEFAULT_UPDATE_TIME
        changes["update_time"] = f"{h:02d}:{m:02d}"
    with db.connect() as conn:
        conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        for col, value in changes.items():  # column names come from the Settings model, not the request
            conn.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (value, user_id))
    return read_settings(user_id)
