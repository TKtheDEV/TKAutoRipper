# app/core/job/tracker.py

import uuid
import threading
from typing import Dict, List, Optional
from pathlib import Path
from .job import Job  # Relative import

class JobTracker:
    def __init__(self):
        self.jobs: Dict[str, Job] = {}
        self.lock = threading.Lock()

    def create_job(self, disc_type: str, drive: str, disc_label: str,
                   temp_dir: Path, output_dir: Path, steps_total: int) -> Job:
        with self.lock:
            job_id = str(uuid.uuid4())
            temp_path = temp_dir / job_id
            output_path = output_dir
            job = Job(
                job_id=job_id,
                disc_type=disc_type,
                drive=drive,
                disc_label=disc_label,
                temp_path=temp_path,
                output_path=output_path,
                steps_total=steps_total,
            )
            self.jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Optional[Job]:
        return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                job.status = "Cancelled"
                return True
            return False

    def remove_job(self, job_id: str) -> bool:
        with self.lock:
            return self.jobs.pop(job_id, None) is not None

    def list_jobs(self) -> List[Job]:
        return list(self.jobs.values())

job_tracker = JobTracker()
