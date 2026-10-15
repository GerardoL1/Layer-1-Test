"""
Writes the API description (OpenAPI) to openapi.json, which the app's TypeScript types are made from.
Run it after changing an endpoint or a schema, then regenerate the app's types:

    python export_openapi.py
    cd ../mobile && npm run api-types

A test fails if openapi.json is out of date.
"""

import json
import os
import tempfile
from pathlib import Path

OUT = Path(__file__).with_name("openapi.json")


def spec_text() -> str:
    # Importing the app sets up the database, so point it at a throwaway one.
    os.environ.setdefault("RECOVERY_DB", os.path.join(tempfile.mkdtemp(prefix="openapi_"), "spec.db"))
    import main

    return json.dumps(main.app.openapi(), indent=2, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    OUT.write_text(spec_text(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUT}")
