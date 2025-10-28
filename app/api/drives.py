# app/api/drives.py

from fastapi import APIRouter, Depends, HTTPException, status, Form, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from pathlib import Path
from pydantic import BaseModel
import subprocess
import logging
from typing import Optional, List

from ..core.configmanager import config
from ..core.auth import verify_web_auth
from ..core.job.tracker import job_tracker
from ..core.drive.manager import drive_tracker
from ..core.job.runner import JobRunner
from ..core.job.job import sanitize_folder

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
    """
    Called by disc detection when a disc is inserted.
    Creates a Job with the correct output root based on disc_type:
      dvd_video   -> [DVD].outputdirectory
      bluray_video-> [BLURAY].outputdirectory
      cd_audio    -> [CD].outputdirectory  (abcde still owns layout on Linux)
      *_rom/other -> [OTHER].outputdirectory (ISO)
    """
    drive = payload.get("drive")
    disc_type = (payload.get("disc_type") or "").lower()
    disc_label = payload.get("disc_label")

    if not all([drive, disc_type, disc_label]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    # Ensure drive exists in tracker
    if not drive_tracker.get_drive(drive):
        drive_tracker.register_drive(drive, model="Unknown", capability=["Unknown"])

    # If drive is busy, do not create a new job
    drv = drive_tracker.get_drive(drive)
    if drv and not drv.is_available:
        return {"status": "Drive in use, skipping job creation"}

    # Resolve temp and output directories
    temp_dir = Path(config.get("General", "tempdirectory")).expanduser()

    # Map API disc types to config sections
    section_map = {
        "dvd_video": "DVD",
        "bluray_video": "BLURAY",
        "cd_audio": "CD",
        # ROM/unknown types use OTHER (ISO)
        "dvd_rom": "OTHER",
        "bluray_rom": "OTHER",
        "cd_rom": "OTHER",
        "other_disc": "OTHER",
    }
    cfg_section = section_map.get(disc_type, "OTHER")

    output_base = (
        config.get(cfg_section, "outputdirectory")
        or config.get("OTHER", "outputdirectory")
    )
    safe_label = sanitize_folder(disc_label or "DISC")
    output_dir = Path(str(output_base)).expanduser() / safe_label

    # Create job and start runner
    job = job_tracker.create_job(
        disc_type=disc_type,
        drive=drive,
        disc_label=disc_label,
        temp_dir=temp_dir,
        output_dir=output_dir,
        steps_total=1  # placeholder; the runner may adjust the effective step count
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
