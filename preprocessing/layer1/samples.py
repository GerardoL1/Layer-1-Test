"""The three mock Apple Health exports that ship with the repo, used by tests and tools."""

from pathlib import Path

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
EXPECTED_DIR = Path(__file__).resolve().parent.parent / "expected"

SAMPLES = {
    "sam": "mock_export_sam_steady.zip",
    "alex": "mock_export_alex_overreach.zip",
    "jordan": "mock_export_jordan_messy.zip",
}


def sample_path(person: str) -> Path:
    return SAMPLE_DIR / SAMPLES[person]
