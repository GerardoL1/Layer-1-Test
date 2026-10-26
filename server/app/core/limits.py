"""
Size limits for everything the server accepts, in one place. Requests over a limit get
a 413 with a plain-English message the app shows as is.
"""

import re

from app.core.urls import USER

MB = 1024 * 1024
GB = 1024 * MB

# Apple Health "Export All Health Data" zip uploaded to the imports endpoint.
MAX_EXPORT_UPLOAD_BYTES = 500 * MB

# JSON and form endpoints. The phone sends at most 2,000 readings per request (well under 1 MB),
# Health Auto Export and Shortcuts send a day or two of data.
MAX_JSON_BYTES = 20 * MB

# Settings, check-ins and workouts are a few hundred bytes each, so anything big is a mistake or abuse.
MAX_SMALL_JSON_BYTES = 64 * 1024

# A Nix workout export (.xlsx) is about 160 KB, so this leaves plenty of room.
MAX_NIX_UPLOAD_BYTES = 5 * MB

# Total unzipped size of everything inside an export zip. Checked from the zip's own listing
# before anything is read, so a zip that would unpack to something enormous is refused early.
MAX_UNZIPPED_BYTES = 4 * GB

# Which limit applies to which endpoint. {user_id} matches any one path segment.
LIMITS_BY_PATH = {
    USER + "/imports": MAX_EXPORT_UPLOAD_BYTES,
    USER + "/readings": MAX_JSON_BYTES,
    USER + "/readings/health-auto-export": MAX_JSON_BYTES,
    USER + "/readings/shortcuts": MAX_JSON_BYTES,
    USER + "/settings": MAX_SMALL_JSON_BYTES,
    USER + "/checkins/morning": MAX_SMALL_JSON_BYTES,
    USER + "/workouts": MAX_SMALL_JSON_BYTES,
    USER + "/workouts/{workout_id}/rating": MAX_SMALL_JSON_BYTES,
    USER + "/workouts/{workout_id}/sweat": MAX_SMALL_JSON_BYTES,
    USER + "/sweat/nix/preview": MAX_NIX_UPLOAD_BYTES,
    USER + "/sweat/nix": MAX_NIX_UPLOAD_BYTES,
    # Old URLs, kept while older app builds and phone automations still use them.
    "/api/import": MAX_EXPORT_UPLOAD_BYTES,
    "/upload": MAX_JSON_BYTES,
    "/api/hae": MAX_JSON_BYTES,
    "/api/shortcut": MAX_JSON_BYTES,
}
EXPORT_UPLOAD_PATHS = {USER + "/imports", "/api/import"}


def _pattern(template: str) -> re.Pattern:
    return re.compile("[^/]+".join(re.escape(part) for part in re.split(r"\{[^}]+\}", template)))


def limit_for(path: str) -> tuple[str, int] | None:
    """The endpoint template a request path belongs to and its limit, or None when it has no limit."""
    if path in LIMITS_BY_PATH:
        return path, LIMITS_BY_PATH[path]
    for template, limit in LIMITS_BY_PATH.items():
        if "{" in template and _pattern(template).fullmatch(path):
            return template, limit
    return None


def size_text(n: int) -> str:
    return f"{n / GB:g} GB" if n >= GB else f"{n / MB:g} MB"


def too_large_message(template: str, limit: int) -> str:
    if template in EXPORT_UPLOAD_PATHS:
        return (
            f"This file is too big. The limit is {size_text(limit)}. Unzip the export and upload "
            "export.xml instead, or run import_export.py on the server."
        )
    return f"This request is too big. The limit is {size_text(limit)}. Send less data at a time."
