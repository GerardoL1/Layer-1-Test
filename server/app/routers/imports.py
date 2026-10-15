"""The fourth way data arrives: the Apple Health export file, imported in the background."""

import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.services import import_jobs
from app.services.apple_export import ExportTooLarge, check_unzipped_size

router = APIRouter(prefix="/api/import", tags=["imports"])


@router.post("")
async def import_upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form("tester1"),
    since_days: int = Form(90),
):
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
    import_jobs.queue(user_id, filename, Path(tmp.name).stat().st_size)
    background.add_task(import_jobs.run_import, tmp.name, user_id, since_days or None)
    return {"started": True}


@router.get("/status")
def import_status():
    return import_jobs.IMPORT_STATUS
