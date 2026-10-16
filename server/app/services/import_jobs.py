"""
The Apple Health export import that runs in the background after an upload.
One import at a time, and its progress is kept in IMPORT_STATUS for the app to poll.
Only the latest import is remembered, and only until the server restarts.
"""

import threading
import uuid
from pathlib import Path

from app.core import db
from app.services import processing
from app.services.apple_export import import_export

IMPORT_STATUS: dict = {"state": "idle"}

# Uploads arrive on several threads at once. Checking for a free slot and taking it happen
# under this lock, so two uploads sent at the same moment can't both get in.
_slot = threading.Lock()


class Busy(Exception):
    """Another import is already queued or running."""


def is_busy() -> bool:
    return IMPORT_STATUS.get("state") in ("queued", "running", "processing")


def reserve(user_id: str, file_name: str) -> dict:
    """
    Takes the one import slot before the upload is read, or raises Busy.
    Returns the status it replaced, so release() can put it back if the upload is no good.
    """
    with _slot:
        if is_busy():
            raise Busy()
        previous = dict(IMPORT_STATUS)
        IMPORT_STATUS.clear()
        IMPORT_STATUS.update(
            import_id=uuid.uuid4().hex,
            state="queued",
            user_id=user_id,
            counts={},
            error=None,
            file_name=file_name,
            file_bytes=0,
            read_fraction=0.0,
            reading=None,
            nights_ready=None,
        )
        return previous


def release(previous: dict) -> None:
    """The upload was refused, so free the slot and show what was there before."""
    IMPORT_STATUS.clear()
    IMPORT_STATUS.update(previous)


def uploaded(file_bytes: int) -> dict:
    """The file is saved and checked. Returns the queued import's status."""
    IMPORT_STATUS.update(file_bytes=file_bytes)
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
