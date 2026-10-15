"""When last night gets processed: the next update time, and whether Update now can do anything."""

from datetime import datetime, time, timedelta

from app.core import db
from layer1 import incremental as I
from layer1 import pipeline as P


def next_update(now: datetime, update_time: tuple) -> datetime:
    at = datetime.combine(now.date(), time(*update_time))
    return at if at > now else at + timedelta(days=1)


def can_update_now(conn, user_id: str, now: datetime, update_time: tuple, ready_through) -> bool:
    """True when "Update now" would process a night that isn't processed yet."""
    since = int((now - timedelta(days=3)).timestamp() * 1000)  # rough, local vs UTC doesn't matter here
    recent = db.load_records(conn, user_id, since_ms=since, sleep_only=True)
    if recent.empty:
        return False
    stages = P.clean(recent)[0]["sleep_stages"]  # same cleaning as processing (watch only, no In Bed)
    if stages.empty:
        return False
    newest = I.latest_ready_night(now, stages, update_time, update_now=True)
    return ready_through is None or newest > ready_through
