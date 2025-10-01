# app/core/job/tracker.py
from __future__ import annotations

import uuid
import threading
from typing import Dict, List, Optional
from pathlib import Path
import json
import shutil

from app.core.configmanager import config
from .job import Job, STATE_FILENAME

class JobTracker:
    def __init__(self) -> None:
        self.jobs: Dict[str, Job] = {}
        self.lock = threading.Lock()
        # bootstrap from temp directory on startup
        self.temp_root = Path(config.section("General").get("tempdirectory") or "~/TKAutoRipper/temp").expanduser()
        try:
            self._bootstrap_from_state()
        except Exception:
            # non-fatal; continue with empty set
            pass

    # ── create/remove/get/list ───────────────────────────────
    def create_job(self, disc_type: str, drive: str, disc_label: str,
                   temp_dir: Path, output_dir: Path, steps_total: int) -> Job:
        with self.lock:
            job_id = str(uuid.uuid4())
            temp_path = Path(temp_dir) / job_id
            output_path = Path(output_dir)
            job = Job(
                job_id=job_id,
                disc_type=disc_type,
                drive=drive,
                disc_label=disc_label,
                temp_path=temp_path,
                output_path=output_path,
                steps_total=steps_total,
            )
            # initial save so the job appears after restart
            try: job.save_state()
            except Exception: pass
            self.jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                job.status = "Cancelled"
                try: job.save_state()
                except Exception: pass
                return True
            return False

    def remove_job(self, job_id: str, nuke_temp: bool = False) -> bool:
        with self.lock:
            job = self.jobs.pop(job_id, None)
        if not job:
            return False
        if nuke_temp:
            try:
                shutil.rmtree(job.temp_path, ignore_errors=True)
            except Exception:
                pass
        return True

    def list_jobs(self) -> List[Job]:
        return list(self.jobs.values())

    # ── bootstrap from state.json ────────────────────────────
    def _bootstrap_from_state(self) -> None:
        root = self.temp_root
        if not root.exists():
            return
        for d in root.iterdir():
            if not d.is_dir():
                continue
            state = d / STATE_FILENAME
            if not state.exists():
                continue
            try:
                data = json.loads(state.read_text(encoding="utf-8"))
                job_id = data.get("job_id") or d.name
                if job_id in self.jobs:
                    continue
                job = Job(
                    job_id=job_id,
                    disc_type=data.get("disc_type", "other_disc"),
                    drive=data.get("drive", ""),
                    disc_label=data.get("disc_label", d.name),
                    temp_path=d,
                    output_path=Path(data.get("output_path") or (d / "output")),
                    steps_total=int(data.get("steps_total", 1) or 1),
                )
                job.load_state()
                # Normalize any “running” states found on disk after a crash/reboot
                if (job.status or "").lower() in ("running", "queued"):
                    job.status = "Paused"
                self.jobs[job_id] = job
            except Exception:
                # if state is corrupted, remove the dir to avoid repeated errors
                try: shutil.rmtree(d, ignore_errors=True)
                except Exception: pass

# Singleton
job_tracker = JobTracker()
