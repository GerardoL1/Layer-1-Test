"""
The fourth way data arrives: the Apple Health export file. The upload is checked here,
then imported in the background. The app polls the import it got back until it's done.
"""

import shutil
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Response, UploadFile

from app.core.urls import USER
from app.services import import_jobs
from app.services.apple_export import ExportTooLarge, check_unzipped_size

router = APIRouter(prefix=USER + "/imports", tags=["imports"])


def start_import(background: BackgroundTasks, user_id: str, file: UploadFile, since_days: int) -> dict:
    """Saves the upload, checks it, and queues the import. Returns the new import's status."""
    if import_jobs.is_busy():
        raise HTTPException(409, "An import is already running. Wait for it to finish.")
    filename = file.filename or ""
    if not filename.lower().endswith((".zip", ".xml")):
        raise HTTPException(400, "Upload the export.zip (or export.xml) from the Health app.")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix)
    with tmp:
        shutil.copyfileobj(file.file, tmp)
    try:
        check_unzipped_size(tmp.name)
    except ExportTooLarge as e:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(413, str(e)) from None
    except zipfile.BadZipFile:
        Path(tmp.name).unlink(missing_ok=True)
        raise HTTPException(
            400, "That zip file can't be opened. Upload the export.zip made by the Health app."
        ) from None
    job = import_jobs.queue(user_id, filename, Path(tmp.name).stat().st_size)
    background.add_task(import_jobs.run_import, tmp.name, user_id, since_days or None)
    return job


@router.post("", status_code=202)
def create_import(
    user_id: str,
    background: BackgroundTasks,
    response: Response,
    file: UploadFile = File(...),
    since_days: int = Form(90),
):
    """
    Upload export.zip (or export.xml). Replies 202 straight away with the import's status,
    and its address in the Location header. since_days 0 imports everything.
    """
    job = start_import(background, user_id, file, since_days)
    here = router.prefix.format(user_id=quote(user_id, safe=""))
    response.headers["Location"] = f"{here}/{job['import_id']}"
    return job


@router.get("")
def list_imports(user_id: str):
    """This person's latest import, if the server still remembers it. Used to pick an import up again."""
    return import_jobs.for_user(user_id)


@router.get("/{import_id}")
def get_import(user_id: str, import_id: str):
    job = import_jobs.find(user_id, import_id)
    if job is None:
        raise HTTPException(404, "No import with that id. The server may have restarted since it started.")
    return job
