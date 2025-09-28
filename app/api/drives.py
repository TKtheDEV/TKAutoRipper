from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from pathlib import Path
from pydantic import BaseModel
import subprocess
import logging

from ..core.configmanager import config
from ..core.auth import verify_web_auth
from ..core.job.tracker import job_tracker
from ..core.drive.manager import drive_tracker
from ..core.job.runner import JobRunner

router = APIRouter()
security = HTTPBasic()


def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = config.get("auth", "username")
    correct_password = config.get("auth", "password")
    if not (
        secrets.compare_digest(credentials.username, correct_username) and
        secrets.compare_digest(credentials.password, correct_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@router.post("/api/drives/insert", dependencies=[Depends(verify_auth)])
def insert_drive(payload: dict):
    drive = payload.get("drive")
    disc_type = payload.get("disc_type")
    disc_label = payload.get("disc_label")

    if not all([drive, disc_type, disc_label]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    if not drive_tracker.get_drive(drive):
        drive_tracker.register_drive(drive, model="Unknown", capability=["Unknown"])

    if not drive_tracker.get_drive(drive).is_available:
        return {"status": "Drive in use, skipping job creation"}

    temp_dir = Path(config.get("General", "tempdirectory")).expanduser()
    output_base = config.get(disc_type.upper(), "outputdirectory") or config.get("OTHER", "outputdirectory")
    output_dir = Path(output_base).expanduser() / disc_label

    job = job_tracker.create_job(
        disc_type=disc_type,
        drive=drive,
        disc_label=disc_label,
        temp_dir=temp_dir,
        output_dir=output_dir,
        steps_total=1  # placeholder; real runner may update this
    )
    drive_tracker.assign_job(drive, job.job_id)

    runner = JobRunner(job)
    runner.run()

    return {"status": "Job started", "job_id": job.job_id}


@router.post("/api/drives/remove", dependencies=[Depends(verify_auth)])
def remove_drive(payload: dict):
    drive = payload.get("drive")
    drive_obj = drive_tracker.get_drive(drive)
    if not drive_obj:
        return {"status": "Drive not tracked"}

    job_id = drive_obj.job_id
    if job_id:
        job = job_tracker.get_job(job_id)
        if job and job.runner:
            job.runner.cancel()
        job_tracker.cancel_job(job_id)

    drive_tracker.release_drive(drive)
    return {"status": "Drive released and job cancelled" if job_id else "Drive released"}


@router.get("/api/drives", dependencies=[Depends(verify_web_auth)])
def list_drives():
    import logging
    logging.info(f"DriveTracker ID: {id(drive_tracker)}")
    return [
        {
            "path": d.path,
            "model": d.model,
            "capability": d.capability,
            "job_id": d.job_id if d.job_id else None,
            "disc_label": d.disc_label if d.disc_label else None,
            "blacklisted": d.blacklisted
        }
        for d in drive_tracker.get_all_drives()
    ]

class DriveEjectRequest(BaseModel):
    path: str

@router.post("/api/drives/eject", dependencies=[Depends(verify_web_auth)])
def eject_drive(request: DriveEjectRequest):
    drive = request.path
    drv = drive_tracker.get_drive(drive)
    if not drv:
        raise HTTPException(status_code=404, detail="Drive not found")

    # Cancel running job if any
    if drv.job_id:
        job = job_tracker.get_job(drv.job_id)
        if job and job.runner:
            job.runner.cancel()
            logging.info(f"❌ Cancelled job {job.job_id} due to web eject")

    # Attempt eject
    try:
        subprocess.run(["eject", drive], check=True)
        logging.info(f"🛑 Ejected drive: {drive}")
    except subprocess.CalledProcessError as e:
        logging.warning(f"⚠️ Eject command failed: {e}")
        raise HTTPException(status_code=500, detail=f"Eject failed: {e}")

    return {"status": "ok"}