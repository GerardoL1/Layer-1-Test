"""
The Apple Health export import that runs in the background after an upload.
One import at a time, and its progress is kept in IMPORT_STATUS for the app to poll.
Only the latest import is remembered, and only until the server restarts.
"""

import uuid
from pathlib import Path

from app.core import db
from app.services import processing
from app.services.apple_export import import_export

IMPORT_STATUS: dict = {"state": "idle"}


def is_busy() -> bool:
    return IMPORT_STATUS.get("state") in ("queued", "running", "processing")


def queue(user_id: str, file_name: str, file_bytes: int) -> dict:
    """Starts a fresh status for a new import and returns it."""
    IMPORT_STATUS.clear()
    IMPORT_STATUS.update(
        import_id=uuid.uuid4().hex,
        state="queued",
        user_id=user_id,
        counts={},
        error=None,
        file_name=file_name,
        file_bytes=file_bytes,
        read_fraction=0.0,
        reading=None,
        nights_ready=None,
    )
    return dict(IMPORT_STATUS)


def for_user(user_id: str) -> list[dict]:
    """This person's imports. That's the latest one, if it was theirs."""
    return [dict(IMPORT_STATUS)] if IMPORT_STATUS.get("user_id") == user_id else []


def find(user_id: str, import_id: str) -> dict | None:
    return next((job for job in for_user(user_id) if job.get("import_id") == import_id), None)


def run_import(path: str, user_id: str, since_days: int | None):
    IMPORT_STATUS.update(state="running", user_id=user_id, counts={}, error=None, read_fraction=0.0, reading=None)
    try:
        conn = db.connect()
        counts = import_export(
            path,
            conn,
            user_id,
            since_days,
            progress=lambda c: IMPORT_STATUS.update(counts=c),
            on_position=lambda share, reading: IMPORT_STATUS.update(read_fraction=round(share, 3), reading=reading),
        )
        conn.close()
        if counts.get("new"):
            IMPORT_STATUS.update(state="processing")
            processing.process_user(user_id)
        with db.connect() as conn:
            nights = conn.execute("SELECT COUNT(*) FROM nights WHERE user_id = ?", (user_id,)).fetchone()[0]
        IMPORT_STATUS.update(state="done", counts=counts, nights_ready=nights)
    except Exception as e:  # report any parsing problem to whoever is polling the status
        IMPORT_STATUS.update(state="error", error=str(e))
    finally:
        Path(path).unlink(missing_ok=True)
