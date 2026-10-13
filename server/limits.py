"""
Size limits for everything the server accepts, in one place. Requests over a limit get
a 413 with a plain-English message the app shows as is.
"""

MB = 1024 * 1024
GB = 1024 * MB

# Apple Health "Export All Health Data" zip uploaded at POST /api/import.
MAX_EXPORT_UPLOAD_BYTES = 500 * MB

# JSON and form endpoints. The phone sends at most 2,000 readings per /upload (well under 1 MB),
# Health Auto Export and Shortcuts send a day or two of data.
MAX_JSON_BYTES = 20 * MB

# Total unzipped size of everything inside an export zip. Checked from the zip's own listing
# before anything is read, so a zip that would unpack to something enormous is refused early.
MAX_UNZIPPED_BYTES = 4 * GB

# Which limit applies to which endpoint.
LIMITS_BY_PATH = {
    "/api/import": MAX_EXPORT_UPLOAD_BYTES,
    "/upload": MAX_JSON_BYTES,
    "/api/hae": MAX_JSON_BYTES,
    "/api/shortcut": MAX_JSON_BYTES,
}


def size_text(n: int) -> str:
    return f"{n / GB:g} GB" if n >= GB else f"{n / MB:g} MB"


def too_large_message(path: str, limit: int) -> str:
    if path == "/api/import":
        return (f"This file is too big. The limit is {size_text(limit)}. Unzip the export and upload "
                "export.xml instead, or run import_export.py on the server.")
    return f"This request is too big. The limit is {size_text(limit)}. Send less data at a time."
