"""Demo mode (temporary, remove later): load one of the mock people with a fixed clock."""

from typing import Literal

from fastapi import APIRouter

from app.core import db
from app.services import processing
from app.services.apple_export import import_export
from layer1.samples import sample_path

router = APIRouter(prefix="/api", tags=["demo"])

# The mock people last sleep on the night of 30 Sep 2026 (they wake on 1 Oct), so the demo
# clock sits just after that night's update time.
DEMO_CLOCK = "2026-10-01T08:30:00"


@router.post("/demo/{person}")
def load_demo(person: Literal["sam", "alex", "jordan"]):
    """Load a mock person as demo-<name> with a fixed clock. Reloading starts them fresh."""
    user_id = f"demo-{person}"
    with db.connect() as conn:
        for table in ("samples", "sleep_stages", "nights", "runs", "users"):
            conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
        conn.execute("INSERT INTO users (user_id, clock_local) VALUES (?, ?)", (user_id, DEMO_CLOCK))
        import_export(sample_path(person), conn, user_id)
    processing.process_user(user_id, force=True)
    return {"user_id": user_id, "clock_local": DEMO_CLOCK}
