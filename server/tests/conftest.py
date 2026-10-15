import os
import tempfile
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
ROOT = SERVER.parent

# Use a throwaway database so tests never touch platform.db.
_tmp = tempfile.mkdtemp(prefix="recovery_test_")
os.environ["RECOVERY_DB"] = os.path.join(_tmp, "test.db")

SAMPLE_DATA = ROOT / "preprocessing" / "sample_data"
SAMPLES = {
    "sam": "mock_export_sam_steady.zip",
    "alex": "mock_export_alex_overreach.zip",
    "jordan": "mock_export_jordan_messy.zip",
}

# Create the tables up front, so any test file can run on its own.
from app.core import db  # noqa: E402
from app.services import processing  # noqa: E402

db.init_db()
processing.init_db()
