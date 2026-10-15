"""
The old URLs, kept so older app builds and phone automations set up before /api/v1 keep working.
Each one does exactly what it did before by calling the new endpoint, and also:
  - logs a warning naming the URL to switch to
  - adds a Deprecation header (RFC 9745) to replies that worked
  - shows as deprecated in /docs
Remove this file once nothing logs these warnings any more.
"""

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, Response, UploadFile
from fastapi.responses import PlainTextResponse

from app.core.urls import API_V1, USER
from app.routers import demo, imports, processing_runs, profile, readings, settings, today, trends
from app.schemas.readings import Upload
from app.schemas.settings import Settings
from app.services import import_jobs

log = logging.getLogger("recovery.deprecated")

# Old route -> what replaces it.
REPLACEMENTS = {
    "POST /upload": f"POST {USER}/readings",
    "POST /api/hae": f"POST {USER}/readings/health-auto-export",
    "POST /api/shortcut": f"POST {USER}/readings/shortcuts",
    "POST /api/import": f"POST {USER}/imports",
    "GET /api/import/status": f"GET {USER}/imports/{{import_id}}",
    "GET /api/today": f"GET {USER}/today",
    "GET /api/trends": f"GET {USER}/trends",
    "GET /api/profile": f"GET {USER}/profile",
    "GET /api/settings": f"GET {USER}/settings",
    "PUT /api/settings": f"PATCH {USER}/settings",
    "POST /api/update-now": f"POST {USER}/processing-runs",
    "POST /api/demo/{person}": f"POST {API_V1}/demo-users/{{person}}",
}

# The day these URLs were deprecated, as the RFC 9745 header wants it (@ plus Unix seconds).
DEPRECATED_SINCE = "@" + str(int(datetime(2026, 10, 14, tzinfo=timezone.utc).timestamp()))


def mark_deprecated(request: Request, response: Response) -> None:
    route = request.scope.get("route")
    old = f"{request.method} {getattr(route, 'path', request.url.path)}"
    log.warning("deprecated URL %s used, switch to %s", old, REPLACEMENTS.get(old, "the /api/v1 version"))
    response.headers["Deprecation"] = DEPRECATED_SINCE


router = APIRouter(tags=["deprecated"], deprecated=True, dependencies=[Depends(mark_deprecated)])


# ---------------------------------------------------------------- ways data arrives


@router.post("/upload")
def upload(payload: Upload, background: BackgroundTasks):
    return readings.add_readings(payload.user_id, payload, background)


@router.post("/api/hae")
async def hae(request: Request, background: BackgroundTasks, user_id: str = "tester1"):
    return await readings.add_health_auto_export(user_id, request, background)


@router.post("/api/shortcut", response_class=PlainTextResponse)
def shortcut(background: BackgroundTasks, user: str = Form(...), metric: str = Form(...), rows: str = Form("")):
    return readings.add_shortcut_rows(user.strip(), background, metric, rows)


@router.post("/api/import")
def import_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form("tester1"),
    since_days: int = Form(90),
):
    imports.start_import(background, user_id, file, since_days)
    return {"started": True}


@router.get("/api/import/status")
def import_status():
    return import_jobs.IMPORT_STATUS


# ---------------------------------------------------------------- app screens


@router.get("/api/today")
def get_today(user_id: str):
    return today.today(user_id)


@router.get("/api/trends")
def get_trends(user_id: str, nights: int = 14):
    return trends.trends(user_id, nights)


@router.get("/api/profile")
def get_profile(user_id: str):
    return profile.profile(user_id)


@router.get("/api/settings")
def get_settings(user_id: str):
    return settings.get_settings(user_id)


@router.put("/api/settings")
def put_settings(user_id: str, changes: Settings):
    return settings.update_settings(user_id, changes)


@router.post("/api/update-now")
def update_now(user_id: str):
    return processing_runs.create_processing_run(user_id)


@router.post("/api/demo/{person}")
def load_demo(person: Literal["sam", "alex", "jordan"]):
    return demo.load_demo(person)
