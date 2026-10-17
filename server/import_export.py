"""
Load an Apple Health export from the command line (handy for very large files).

    python import_export.py ~/Downloads/export.zip --user tester1

Everything in the file is imported. --days 90 keeps only the last 90 days, counted back from today.
"""

import argparse

from app.core import db
from app.services.apple_export import import_export

parser = argparse.ArgumentParser(description="Import an Apple Health export into the platform database.")
parser.add_argument("path", help="export.zip or export.xml from the Health app")
parser.add_argument("--user", default="tester1", help="tester name to store the data under")
parser.add_argument("--days", type=int, default=0, help="only import the last N days, from today (0 = everything)")
args = parser.parse_args()

db.init_db()
conn = db.connect()
counts = import_export(
    args.path, conn, args.user, args.days or None, progress=lambda c: print("  so far:", c, flush=True)
)
conn.close()
print("Done:", counts)
