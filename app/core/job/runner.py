# app/core/job/runner.py
from __future__ import annotations
import os
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from app.core.drive.manager import drive_tracker
from .job import Job


# ------------------------------------------------------------
def get_job_steps(job: Job) -> List[Tuple[List[str], str, bool, float]]:
    """
    Resolve disc-type to ripper and get steps.

    Each step tuple may be 3- or 4-elements:
        (cmd, description, release_drive)                # equal weight
        (cmd, description, release_drive, weight:float)   # custom weight
    """
    dtype = job.disc_type.lower()

    if dtype == "cd_audio":
        from app.core.rippers.audio.linux import rip_audio_cd
        return rip_audio_cd(job)

    if dtype in ("cd_rom", "dvd_rom", "bluray_rom"):
        from app.core.rippers.other.linux import rip_generic_disc
        return rip_generic_disc(job)

    if dtype == "dvd_video":
        from app.core.rippers.video.linux import rip_video_disc
        return rip_video_disc(job, "DVD")

    if dtype == "bluray_video":
        from app.core.rippers.video.linux import rip_video_disc
        return rip_video_disc(job, "BLURAY")

    raise ValueError(f"Unsupported disc type: {dtype}")


# ============================================================
class JobRunner:
    """
    Runs a Job in a background thread.
    """

    def __init__(
        self,
        job: Job,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.job = job
        self.job.runner = self
        self.on_output = on_output
        self.process: Optional[subprocess.Popen] = None
        self._cancelled = False

    # ── public API ───────────────────────────────────────────
    def run(self) -> None:
        threading.Thread(target=self._run_steps, daemon=True).start()

    def cancel(self) -> None:
        """
        External cancellation: kill current process-group, free drive,
        mark job cancelled.
        """
        self._cancelled = True
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass

        self.job.status = "Cancelled"
        drive_tracker.release_drive(self.job.drive)
        subprocess.run(["eject", self.job.drive], check=False)

    # ── internal ────────────────────────────────────────────
    def _run_steps(self) -> None:
        try:
            raw_steps = get_job_steps(self.job)

            # normalise to 4-tuple and compute weights
            prepared: List[Tuple[List[str], str, bool, float]] = []
            explicit_weights: List[float] = []

            for tpl in raw_steps:
                if len(tpl) == 3:          # no weight given
                    cmd, desc, rel = tpl
                    prepared.append((cmd, desc, rel, 0.0))
                elif len(tpl) == 4:
                    cmd, desc, rel, w = tpl
                    prepared.append((cmd, desc, rel, w))
                    explicit_weights.append(w)
                else:
                    raise ValueError("Step tuples must be 3 or 4 elements")

            # If no step provided a weight or weights don't sum to 1,
            # distribute evenly.
            if not explicit_weights or abs(sum(explicit_weights) - 1.0) > 1e-6:
                even = 1.0 / len(prepared)
                prepared = [(c, d, r, even) for (c, d, r, _) in prepared]

            self.job.steps_total = len(prepared)

            completed_fraction = 0.0

            for idx, (cmd, desc, release_after, weight) in enumerate(prepared, 1):
                if self._cancelled:
                    return

                self.job.update_step(desc, idx)
                self.job.step_progress = 0

                ok = self._run_step(cmd, weight, completed_fraction)
                if not ok:
                    self.job.mark_failed()
                    drive_tracker.release_drive(self.job.drive)
                    return

                completed_fraction += weight

                if release_after:
                    subprocess.run(["eject", self.job.drive], check=False)
                    drive_tracker.release_drive(self.job.drive)

            self.job.mark_finished()

        except Exception as exc:
            self.job.append_stdout(f"Fatal JobRunner exception: {exc}")
            self.job.mark_failed()
            drive_tracker.release_drive(self.job.drive)

    # --------------------------------------------------------
    def _run_step(
        self,
        command: List[str],
        weight: float,
        fraction_before: float,
    ) -> bool:
        """
        Execute a single command, stream stdout, update progress.

        * `weight`            → fraction of total job time this step represents
        * `fraction_before`   → cumulative progress already achieved (0-1)
        """
        log_path = self.job.temp_path / "log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(log_path, "a") as lf:

                self.process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    preexec_fn=os.setsid,  # new process-group
                )

                line_count = 0
                for line in self.process.stdout:
                    line = line.rstrip()
                    line_count += 1

                    self.job.append_stdout(line)
                    lf.write(line + "\n")
                    lf.flush()
                    if self.on_output:
                        self.on_output(line)

                    # naive but smooth progress: bump 0-99 within the step
                    if line_count % 20 == 0:                      # reduce chatter
                        self._update_progress(
                            step_pct=min(99, self.job.step_progress + 1),
                            weight=weight,
                            done_before=fraction_before,
                        )

                self.process.wait()

                # mark step 100 %
                self._update_progress(100, weight, fraction_before)

                return self.process.returncode == 0

        except Exception as exc:
            self.job.append_stdout(f"Exception while running command: {exc}")
            return False

    # --------------------------------------------------------
    def _update_progress(self, step_pct: int, weight: float, done_before: float) -> None:
        """
        Recalculate job.progress given the current step percentage.

        total = done_before + (step_pct/100) * weight
        """
        self.job.step_progress = step_pct
        total_fraction = done_before + (step_pct / 100.0) * weight
        self.job.progress = int(total_fraction * 100)
