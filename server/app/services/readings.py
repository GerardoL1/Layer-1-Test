"""Saving readings from any route, then processing in the background if anything was new."""

from fastapi import BackgroundTasks

from app.core import db
from app.services import processing


def save_readings(background: BackgroundTasks, user_id: str, samples: list, stages: list) -> int:
    """Returns how many readings were new. Repeats are ignored."""
    with db.connect() as conn:
        added = db.add_readings(conn, user_id, samples, stages)
    if added:
        background.add_task(processing.process_user, user_id)
    return added
