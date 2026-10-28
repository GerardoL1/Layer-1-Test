import os
import tempfile
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent
ROOT = SERVER.parent

# Use a throwaway database so tests never touch platform.db.
_tmp = tempfile.mkdtemp(prefix="recovery_test_")
os.environ["RECOVERY_DB"] = os.path.join(_tmp, "test.db")

# Create the tables up front, so any test file can run on its own.
from app.core import db  # noqa: E402
from app.services import processing  # noqa: E402
from layer1.samples import SAMPLE_DIR as SAMPLE_DATA  # noqa: E402, F401
from layer1.samples import SAMPLES  # noqa: E402, F401

db.init_db()
processing.init_db()
