# app/api/jobs.py
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, Body, Query
from fastapi.responses import HTMLResponse, PlainTextResponse
import httpx
import platform

from app.core.auth import verify_web_auth
from app.core.templates import templates
from app.core.configmanager import config
from app.core.job.tracker import job_tracker
from app.core.job.runner import JobRunner
from app.core.integration.omdbapi import helper

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# Pages
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}", response_class=HTMLResponse,
            dependencies=[Depends(verify_web_auth)])
def job_details_page(request: Request, job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("job_details.html", {"request": request, "job": job})


# ──────────────────────────────────────────────────────────────────────────────
# Basic job APIs
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/jobs/{job_id}", dependencies=[Depends(verify_web_auth)])
def get_job(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()

@router.get("/api/jobs", dependencies=[Depends(verify_web_auth)])
def list_jobs():
    return [job.to_dict() for job in job_tracker.list_jobs()]

@router.post("/api/jobs/{job_id}/cancel", dependencies=[Depends(verify_web_auth)])
def cancel_job(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if getattr(job, "runner", None):
        try:
            job.runner.cancel()
        except Exception:
            pass
    job.status = "Cancelled"
    return {"status": "cancelled"}

@router.delete("/api/jobs/{job_id}", dependencies=[Depends(verify_web_auth)])
def delete_job(job_id: str):
    """
    Hard delete: ensure job is stopped, remove from tracker, nuke temp folder (state+temps).
    Idempotent.
    """
    job = job_tracker.get_job(job_id)
    if not job:
        return {"status": "ok"}

    if getattr(job, "runner", None):
        try:
            job.runner.cancel()
        except Exception:
            pass

    try:
        from app.core.drive.manager import drive_tracker
        if getattr(job, "drive", None):
            drive_tracker.release_drive(job.drive)
    except Exception:
        pass

    job_tracker.remove_job(job_id, nuke_temp=True)
    return {"status": "deleted"}


# ──────────────────────────────────────────────────────────────────────────────
# Full text log
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/log", dependencies=[Depends(verify_web_auth)], response_class=PlainTextResponse)
def job_log(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    path = Path(job.temp_path) / "log.txt"
    if not path.exists():
        return ""
    return path.read_text(errors="ignore")


# ──────────────────────────────────────────────────────────────────────────────
# Output path (edit before lock) + ROM auto-proposal
# ──────────────────────────────────────────────────────────────────────────────

def _other_root() -> Path:
    base = (
        config.section("OTHER").get("outputdirectory")
        or config.section("Other").get("outputdirectory")
        or config.section("General").get("outputdirectory")
        or "~/TKAutoRipper/output/ISO"
    )
    return Path(str(base)).expanduser()

def _proposed_rom_path(job) -> Path:
    from app.core.job.job import sanitize_folder
    name = sanitize_folder(getattr(job, "disc_label", None) or "DISC")
    base_dir = _other_root() / name
    other_cfg = config.section("OTHER")
    use_comp = bool(other_cfg.get("usecompression", True))
    comp_alg = str(other_cfg.get("compression", "zstd")).lower()
    if use_comp and comp_alg == "zstd":
        return base_dir / f"{name}.iso.zst"
    if use_comp and comp_alg in {"bz2", "bzip2"}:
        return base_dir / f"{name}.iso.bz2"
    return base_dir / f"{name}.iso"

@router.get("/api/jobs/{job_id}/output", dependencies=[Depends(verify_web_auth)])
def get_output(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    dtype = (job.disc_type or "").lower()

    payload = {
        "output_path": str(job.output_path),
        "locked": bool(getattr(job, "output_locked", False)),
    }

    return payload

@router.put("/api/jobs/{job_id}/output", dependencies=[Depends(verify_web_auth)])
def set_output(job_id: str, payload: dict = Body(...)):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    dtype = (job.disc_type or "").lower()
    if dtype == "cd_audio" and platform.system() == "Linux":
        # abcde manages paths on Linux; we don't expose an override
        raise HTTPException(status_code=405, detail="Changing output path is not supported for Audio CD on Linux.")
    if getattr(job, "output_locked", False):
        raise HTTPException(status_code=409, detail="Output is locked for this job")

    raw = (payload or {}).get("path", "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Missing 'path'")

    p = Path(raw).expanduser()
    dtype = (job.disc_type or "").lower()

    # Video & audio must be a folder
    if dtype in {"dvd_video", "bluray_video", "cd_audio"}:
        if p.suffix:
            raise HTTPException(status_code=400, detail="For video/audio discs, output must be a folder (no filename).")
        p.mkdir(parents=True, exist_ok=True)
        job.output_path = p
        return {"status": "ok", "output_path": str(job.output_path), "type": dtype}

    # ROM & other must be a final file path
    if dtype in {"cd_rom", "dvd_rom", "bluray_rom", "other_disc"}:
        if not p.suffix:
            raise HTTPException(status_code=400, detail="For ROM/other discs, output must be a final file path (e.g., .../MyDisc.iso or .iso.zst).")
        other_cfg = config.section("OTHER")
        comp_alg = str(other_cfg.get("compression", "zstd")).lower()
        allowed = {".iso"}
        if other_cfg.get("usecompression", True):
            if comp_alg == "zstd":
                allowed.update({".zst", ".iso.zst"})
            elif comp_alg in {"bz2", "bzip2"}:
                allowed.update({".bz2", ".iso.bz2"})
        low = p.name.lower()
        valid = (p.suffix.lower() in allowed) or any(low.endswith(x) for x in allowed if x.startswith(".iso."))
        if not valid:
            raise HTTPException(status_code=400, detail=f"Invalid extension. Allowed: {sorted(allowed)}")
        p.parent.mkdir(parents=True, exist_ok=True)
        job.output_path = p.parent
        return {"status": "ok", "output_path": str(job.output_path), "type": dtype}

    # Fallback → treat as folder
    if p.suffix:
        raise HTTPException(status_code=400, detail="Output must be a folder for this disc type.")
    p.mkdir(parents=True, exist_ok=True)
    job.output_path = p
    return {"status": "ok", "output_path": str(job.output_path), "type": dtype}


# ──────────────────────────────────────────────────────────────────────────────
# Retry / Delete lifecycle
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/api/jobs/{job_id}/retry", dependencies=[Depends(verify_web_auth)])
def retry_job(job_id: str):
    """
    Retry allowed iff numeric step >= 2 (beyond ripping).
    Spawns a runner that continues from the step AFTER the last successful one.
    """
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")

    # FIX: use the actual 'step' field (there is no 'step_index')
    step_index = int(getattr(job, "step", 1) or 1)
    if step_index < 2:
        raise HTTPException(409, "Job is not retryable (step_index < 2)")
    if getattr(job, "runner", None) and job.status.lower() in ("running", "ripping", "queued"):
        raise HTTPException(409, "Job is currently running")

    job.status = "Queued"
    runner = JobRunner(job)
    job.runner = runner

    import threading
    threading.Thread(target=runner.retry_from_last, daemon=True).start()
    return {"status": "queued", "from_step": step_index + 1}


# ──────────────────────────────────────────────────────────────────────────────
# OMDb support
# ──────────────────────────────────────────────────────────────────────────────

def _omdb_key() -> str:
    key = config.section("General").get("omdbapikey") or config.section("GENERAL").get("omdbapikey")
    if not key:
        raise HTTPException(status_code=400, detail="OMDb API key not configured")
    return key

@router.get("/api/omdb/search", dependencies=[Depends(verify_web_auth)])
async def omdb_search(q: str = Query(..., min_length=2), type: str = Query(None, pattern="^(movie|series)$")):
    params = {"apikey": _omdb_key(), "s": q}
    if type:
        params["type"] = type
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://www.omdbapi.com/", params=params)
    data = r.json()
    if not data or data.get("Response") != "True":
        return {"results": []}
    results = [{"imdbID": x["imdbID"], "Title": x["Title"], "Year": x.get("Year"), "Type": x.get("Type")}
               for x in data.get("Search", [])[:10]]
    return {"results": results}

@router.put("/api/jobs/{job_id}/imdb", dependencies=[Depends(verify_web_auth)])
async def set_job_imdb(job_id: str, imdbID: str = Query(...), season: int | None = Query(None, ge=1, le=100)):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if getattr(job, "output_locked", False):
        raise HTTPException(status_code=409, detail="Output is locked for this job")

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("https://www.omdbapi.com/", params={"apikey": _omdb_key(), "i": imdbID, "plot": "short"})
    meta = r.json()
    if not meta or meta.get("Response") != "True":
        raise HTTPException(status_code=404, detail="IMDb ID not found")

    typ = (meta.get("Type") or "").lower()
    if season is not None and typ != "series":
        raise HTTPException(status_code=400, detail="Season is only valid for series")

    # Persist to job
    job.imdb_id = imdbID
    job.metadata = meta
    job.season = season

    # Move output to a Jellyfin-friendly folder layout
    from app.core.job.job import sanitize_folder
    current_dir = Path(str(job.output_path))
    type_root = current_dir.parent
    category = "Shows" if typ == "series" else "Movies"
    title = sanitize_folder(meta.get("Title", ""))
    suffix_year = f" ({meta.get('Year')})" if meta.get("Year") else ""
    target = type_root / category / f"{title}{suffix_year}"
    if typ == "series" and season:
        target = target / f"Season {season}"
    target.mkdir(parents=True, exist_ok=True)
    job.output_path = target

    # Best-effort NFO
    try:
        job.write_jellyfin_nfo(target)
    except Exception:
        pass

    return {
        "status": "ok",
        "title": meta.get("Title"),
        "year": meta.get("Year"),
        "type": typ,
        "season": season,
        "output_path": str(job.output_path),
        "imdb_id": job.imdb_id,
    }
    