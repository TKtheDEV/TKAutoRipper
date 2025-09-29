# app/api/jobs.py
from fastapi import APIRouter, Depends, HTTPException, Request, Body, Query
from fastapi.responses import HTMLResponse, PlainTextResponse, JSONResponse
from pathlib import Path
import httpx

from app.core.auth import verify_web_auth
from app.core.job.tracker import job_tracker
from app.core.drive.manager import drive_tracker
from app.core.templates import templates
from app.core.configmanager import config
from app.core.job.job import sanitize_folder

router = APIRouter()

# ---------- Pages ----------
@router.get("/jobs/{job_id}", response_class=HTMLResponse,
            dependencies=[Depends(verify_web_auth)])
def job_details_page(request: Request, job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return templates.TemplateResponse("job_details.html", {"request": request, "job": job})

# ---------- Basic job APIs ----------
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
    if job.runner:
        job.runner.cancel()
    drive_tracker.release_drive(job.drive)
    return {"status": "cancelled"}

# ---------- Full text log ----------
@router.get("/jobs/{job_id}/log", dependencies=[Depends(verify_web_auth)], response_class=PlainTextResponse)
def job_log(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    path = job.temp_path / "log.txt"
    if not path.exists():
        return ""
    return path.read_text(errors="ignore")

# ---------- Output path (edit before lock) ----------
@router.get("/api/jobs/{job_id}/output", dependencies=[Depends(verify_web_auth)])
def get_output(job_id: str):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "output_path": str(job.output_path),
        "override_filename": job.override_filename,
        "locked": bool(job.output_locked),
    }

@router.put("/api/jobs/{job_id}/output", dependencies=[Depends(verify_web_auth)])
def set_output(job_id: str, payload: dict = Body(...)):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
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
        job.override_filename = None
        return {"status": "ok", "output_path": str(job.output_path), "override_filename": None, "type": dtype}

    # ROM must be a final file path
    if dtype in {"cd_rom", "dvd_rom", "bluray_rom"}:
        if not p.suffix:
            raise HTTPException(status_code=400, detail="For ROM discs, output must be a final file path (e.g. .../MyDisc.iso or .iso.zst).")

        other_cfg = config.section("OTHER")
        comp_alg = str(other_cfg.get("compression", "zstd")).lower()
        allowed = {".iso"}
        if other_cfg.get("usecompression", True):
            if comp_alg == "zstd":
                allowed.update({".zst", ".iso.zst"})
            elif comp_alg in {"bz2", "bzip2"}:
                allowed.update({".bz2", ".iso.bz2"})

        full_name = p.name.lower()
        valid = (
            p.suffix.lower() in allowed or
            any(full_name.endswith(x) for x in allowed if x.startswith(".iso."))
        )
        if not valid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid extension for ROM disc. Allowed: {sorted(allowed)}"
            )

        p.parent.mkdir(parents=True, exist_ok=True)
        job.output_path = p.parent
        job.override_filename = p.name
        return {"status": "ok", "output_path": str(job.output_path), "override_filename": job.override_filename, "type": dtype}

    # fallback → treat as folder
    if p.suffix:
        raise HTTPException(status_code=400, detail="Output must be a folder for this disc type.")
    p.mkdir(parents=True, exist_ok=True)
    job.output_path = p
    job.override_filename = None
    return {"status": "ok", "output_path": str(job.output_path), "override_filename": None, "type": dtype}

# ---------- OMDb support ----------
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
    results = [
        {"imdbID": x["imdbID"], "Title": x["Title"], "Year": x.get("Year"), "Type": x.get("Type")}
        for x in data.get("Search", [])[:10]
    ]
    return {"results": results}

def _jellyfin_target_dir(current_dir: Path, title: str, year: str, typ: str, season: int | None) -> Path:
    base = current_dir.parent if current_dir.exists() else current_dir.parent
    clean = sanitize_folder(title)
    typ = (typ or "").lower()
    if typ == "series" and season:
        return base / clean / f"Season {season}"
    y = f" ({year})" if year else ""
    return base / f"{clean}{y}"

@router.put("/api/jobs/{job_id}/imdb", dependencies=[Depends(verify_web_auth)])
async def set_job_imdb(job_id: str, imdbID: str = Query(...), season: int | None = Query(None, ge=1, le=100)):
    job = job_tracker.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if getattr(job, "output_locked", False):
        raise HTTPException(status_code=409, detail="Output is locked for this job")

    # Fetch OMDb metadata
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

    # Compute and switch output dir
    current_dir = Path(str(job.output_path))
    target_dir = _jellyfin_target_dir(current_dir, meta.get("Title", ""), meta.get("Year", ""), typ, season)
    target_dir.mkdir(parents=True, exist_ok=True)
    job.output_path = target_dir

    # Write NFO for Jellyfin
    try:
        job.write_jellyfin_nfo(target_dir)
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
