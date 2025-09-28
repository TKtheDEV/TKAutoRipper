# app/api/jobs.py
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.core.auth import verify_web_auth
from app.core.job.tracker import job_tracker
from app.core.drive.manager import drive_tracker
from app.core.templates import templates

router = APIRouter()


@router.get("/jobs/{job_id}", response_class=HTMLResponse,
            dependencies=[Depends(verify_web_auth)])
def job_details_page(request: Request, job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("job_details.html", {"request": request, "job": job})


@router.get("/api/jobs/{job_id}", dependencies=[Depends(verify_web_auth)])
def get_job(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/api/jobs", dependencies=[Depends(verify_web_auth)])
def list_jobs():
    return [job.to_dict() for job in job_tracker.list_jobs()]


# NEW ─────────────────────────────────────────────────────────
@router.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(verify_web_auth)])
def cancel_job(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.runner:
        job.runner.cancel()
    job_tracker.cancel_job(job_id)
    drive_tracker.release_drive(job.drive)
    return {"status": "cancelled"}
