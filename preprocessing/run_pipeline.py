"""
Run the preprocessing without the visual platform.

    python run_pipeline.py path/to/export.zip --person alex --out alex_features.csv
    python run_pipeline.py --save-expected      # refresh expected/ from the sample files
"""
import argparse
from pathlib import Path

import pipeline as P

HERE = Path(__file__).parent
SAMPLES = {"sam": "mock_export_sam_steady.zip", "alex": "mock_export_alex_overreach.zip",
           "jordan": "mock_export_jordan_messy.zip"}


def save_expected():
    out = HERE / "expected"
    out.mkdir(exist_ok=True)
    for person, fname in SAMPLES.items():
        r = P.run_pipeline(HERE / "sample_data" / fname, person, days=None)
        r.ml_table.to_csv(out / f"{person}_features.csv", index=False)
        print(f"expected/{person}_features.csv  ({len(r.ml_table)} nights)")


def main():
    ap = argparse.ArgumentParser(description="Apple Health export -> ML-ready nightly table")
    ap.add_argument("path", nargs="?", help="export.zip or export.xml")
    ap.add_argument("--person", default="tester1", help="tester name stored in person_id")
    ap.add_argument("--days", type=int, default=90, help="days back from the newest record (0 = everything)")
    ap.add_argument("--out", help="CSV file to write (default: layer1_features_<person>.csv)")
    ap.add_argument("--save-expected", action="store_true", help="rebuild expected/ outputs from sample_data/")
    args = ap.parse_args()

    if args.save_expected:
        save_expected()
        return
    if not args.path:
        ap.error("give the path to an export, or use --save-expected")
    r = P.run_pipeline(args.path, args.person, args.days or None)
    out = args.out or f"layer1_features_{args.person}.csv"
    r.ml_table.to_csv(out, index=False)
    print(f"{out}: {len(r.ml_table)} nights, {int(r.ml_table['usable_sleep'].sum())} usable")
    if len(r.removal_log):
        print("Removed while cleaning:")
        print(r.removal_log.to_string(index=False))
    for note in r.notes:
        print("Note:", note)


if __name__ == "__main__":
    main()
