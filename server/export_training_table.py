"""
Write the readiness model's training table to a CSV (one row per person per night).

    python export_training_table.py C:\\Users\\you\\Desktop\\training.csv
    python export_training_table.py training.csv --user tester1 --labelled-only

This is real health data, so it's refused inside the repo folder. Keep it out of git and share it only
with the team members building the model.
"""

import argparse
import sys
from pathlib import Path

from app.core import db
from app.services import processing, training_table

REPO = Path(__file__).resolve().parent.parent

parser = argparse.ArgumentParser(description="Export the readiness model's training table.")
parser.add_argument("out", help="CSV file to write, outside the repo folder")
parser.add_argument("--user", action="append", help="only this tester (repeat for several). Default: everyone")
parser.add_argument("--labelled-only", action="store_true", help="only nights that have a morning check-in")
parser.add_argument(
    "--include-catch-up", action="store_true", help="also nights added in a catch-up run, never shown on Today"
)
args = parser.parse_args()

out = Path(args.out).resolve()
if out.is_relative_to(REPO):
    sys.exit(f"Refusing to write health data inside the repo ({REPO}). Pick a folder outside it, like your Desktop.")

db.init_db()
processing.init_db()
with db.connect() as conn:
    table = training_table.build(conn, args.user, include_catch_up=args.include_catch_up)
if args.labelled_only:
    table = table[table["checkin_ready_to_train"].notna()]
out.parent.mkdir(parents=True, exist_ok=True)
table.to_csv(out, index=False)
labelled = int(table["checkin_ready_to_train"].notna().sum())
print(f"{out}: {len(table)} nights, {labelled} with a check-in, {table['person_id'].nunique()} people")
