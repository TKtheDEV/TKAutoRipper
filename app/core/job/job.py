# app/core/job/job.py

from dataclasses import dataclass, field, asdict
from collections import deque
from typing import Optional
from pathlib import Path
import time


@dataclass
class Job:
    job_id: str
    disc_type: str
    drive: str
    disc_label: str
    temp_path: Path
    output_path: Path
    output_path_lock: bool = False
    start_time: float = field(default_factory=time.time)
    steps_total: int = 1
    step: int = 1
    step_description: str = "Initializing"
    step_progress: int = 0
    status: str = "Queued"
    progress: int = 0
    stdout_log: deque = field(default_factory=lambda: deque(maxlen=15))
    runner: Optional["JobRunner"] = None  # forward reference

    def update_step(self, description: str, step: Optional[int] = None):
        if step:
            self.step = step
        self.step_description = description
        self.step_progress = 0

    def update_progress(self, progress: int):
        self.progress = progress

    def append_stdout(self, line: str):
        self.stdout_log.append(line)

    def mark_failed(self):
        self.status = "Failed"

    def mark_finished(self):
        self.status = "Finished"

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "disc_type": self.disc_type,
            "drive": self.drive,
            "disc_label": self.disc_label,
            "temp_path": str(self.temp_path),
            "output_path": str(self.output_path),
            "output_path_lock": self.output_path_lock,
            "start_time": self.start_time,
            "steps_total": self.steps_total,
            "step": self.step,
            "step_description": self.step_description,
            "step_progress": self.step_progress,
            "status": self.status,
            "progress": self.progress,
            "stdout_log": list(self.stdout_log),
        }
