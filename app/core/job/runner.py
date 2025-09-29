# app/core/job/runner.py
from __future__ import annotations
import os
import re
import shlex
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from app.core.drive.manager import drive_tracker
from .job import Job

# ---------------------- step resolution ----------------------
def get_job_steps(job: Job) -> List[Tuple[List[str], str, bool, float]]:
    """
    Resolve disc-type to ripper and get steps.

    Each step tuple may be 3-, 4- or 5-elements:
        (cmd, description, release_drive)
        (cmd, description, release_drive, weight)
        (cmd, description, release_drive, weight, dest_path)  # dest is a Path to the final output of this step
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


# ---------------------- progress helpers ----------------------
_percent_re = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%")
_bytes_re   = re.compile(r"(\d+)\s+bytes")  # dd status=progress

def _find_percent(text: str) -> Optional[float]:
    m = _percent_re.search(text)
    if not m:
        return None
    try:
        v = float(m.group(1))
        if 0.0 <= v <= 100.0:
            return v
    except ValueError:
        pass
    return None

def _dd_percent_from_line(text: str, expected_bytes: Optional[int]) -> Optional[float]:
    if expected_bytes and expected_bytes > 0:
        m = _bytes_re.search(text)
        if m:
            done = float(m.group(1))
            return max(0.0, min(100.0, (done / expected_bytes) * 100.0))
    return None

def _makemkv_percent_from_file(progress_path: Path) -> Optional[float]:
    try:
        if progress_path and progress_path.exists():
            txt = progress_path.read_text(errors="ignore")
            p = _find_percent(txt) or _find_percent(txt.splitlines()[-1]) if txt else None
            return p
    except Exception:
        pass
    return None

# ---------------------- weighting policies ----------------------
ROM_WEIGHTS = { "cd_rom": (0.50, 0.50), "dvd_rom": (0.60, 0.40), "bluray_rom": (0.70, 0.30) }
VIDEO_WEIGHTS = { "dvd_video": (0.60, 0.40), "bluray_video": (0.70, 0.30) }

# ======================== Runner ==============================
class JobRunner:
    def __init__(self, job: Job, on_output: Optional[Callable[[str], None]] = None) -> None:
        self.job = job
        self.job.runner = self

        # multi-listener fan-out
        self._output_listeners: List[Callable[[str], None]] = []
        if on_output:
            self._output_listeners.append(on_output)

        self.process: Optional[subprocess.Popen] = None
        self._cancelled = False

        # extra progress channels
        self.job.title_progress = 0

        # rename / resume
        self._rename_event = threading.Event()
        self._pending_dest: Optional[Path] = None

    # --- pub/sub for WS listeners ---
    def add_output_listener(self, cb: Callable[[str], None]) -> None:
        if cb not in self._output_listeners:
            self._output_listeners.append(cb)

    def remove_output_listener(self, cb: Callable[[str], None]) -> None:
        try:
            self._output_listeners.remove(cb)
        except ValueError:
            pass

    def _emit_output(self, line: str) -> None:
        for cb in list(self._output_listeners):
            try:
                cb(line)
            except Exception:
                pass

    # ---------------- public API ----------------
    def run(self) -> None:
        threading.Thread(target=self._run_steps, daemon=True).start()

    def cancel(self) -> None:
        self._cancelled = True
        if self.process:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass
        self.job.status = "Cancelled"
        drive_tracker.release_drive(self.job.drive)
        subprocess.run(["eject", self.job.drive], check=False)

    def set_new_destination_and_resume(self, new_path_str: str) -> None:
        try:
            self._pending_dest = Path(new_path_str).expanduser()
        except Exception:
            return
        self._rename_event.set()

    # ---------------- internal ------------------
    def _run_steps(self) -> None:
        try:
            self.job.temp_path.mkdir(parents=True, exist_ok=True)
            # If output_path points to a file path (override set), ensure we have a directory object on job.output_path
            if self.job.override_filename:
                self.job.output_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                self.job.output_path.mkdir(parents=True, exist_ok=True)

            log_path = self.job.temp_path / "log.txt"
            with log_path.open("a", buffering=1) as log_file:
                self.job.status = "Running"

                raw_steps = get_job_steps(self.job)
                steps: List[Tuple[List[str], str, bool, float, Optional[Path]]] = []
                dtype = self.job.disc_type.lower()

                # normalize weights and accept optional dest (5th item)
                def norm_step(s, w):
                    if len(s) == 3:
                        cmd, desc, rel = s; return (cmd, desc, rel, w, None)
                    elif len(s) == 4:
                        cmd, desc, rel, w0 = s; return (cmd, desc, rel, w0, None)
                    elif len(s) == 5:
                        return s
                    else:
                        raise ValueError("Invalid step tuple length")

                if dtype == "cd_audio":
                    for s in raw_steps: steps.append(norm_step(s, 1.0))
                elif dtype in ROM_WEIGHTS:
                    w1, w2 = ROM_WEIGHTS[dtype]
                    for i, s in enumerate(raw_steps): steps.append(norm_step(s, w1 if i == 0 else w2))
                elif dtype in VIDEO_WEIGHTS:
                    w1, w2 = VIDEO_WEIGHTS[dtype]
                    for i, s in enumerate(raw_steps): steps.append(norm_step(s, w1 if i == 0 else w2))
                else:
                    n = max(1, len(raw_steps)); w = 1.0 / n
                    for s in raw_steps: steps.append(norm_step(s, w))

                self.job.steps_total = len(steps)
                total_done_weight = 0.0

                for idx, (cmd, description, release_after, weight, dest) in enumerate(steps, start=1):
                    if self._cancelled:
                        break

                    self.job.step = idx
                    self.job.step_description = description
                    self.job.step_progress = 0
                    self.job.title_progress = 0

                    # tool detection
                    cmd_str = " ".join(shlex.quote(str(x)) for x in cmd)
                    low_desc = description.lower()
                    is_dd         = " dd " in f" {cmd_str} " or cmd_str.startswith("dd ") or "creating iso" in low_desc
                    is_makemkv    = "makemkv" in cmd_str.lower() or "makemkv" in low_desc
                    is_handbrake  = "handbrakecli" in cmd_str.lower() or "handbrake" in low_desc
                    is_compress   = any(x in cmd_str.lower() for x in ("zstd", "bzip2", "bz2")) or "compressing" in low_desc

                    # --- Rename / collision handling ---
                    if dest is not None and dest.exists():
                        # Pause and wait for UI to provide a new path
                        self.job.status = "Waiting for output path"
                        self.job.waiting_for_rename = True
                        self.job.proposed_output = str(dest)
                        self._emit_output(f"[TKAR] Destination exists: {dest}. Waiting for user to rename...")
                        self._rename_event.clear()
                        self._rename_event.wait()
                        self.job.waiting_for_rename = False
                        if self._pending_dest:
                            # rewrite output path in command
                            if is_compress and "zstd" in cmd_str.lower():
                                new_cmd = []
                                it = iter(cmd)
                                for token in it:
                                    if token == "-o":
                                        _ = next(it, None)
                                        new_cmd.extend(["-o", str(self._pending_dest)])
                                    else:
                                        new_cmd.append(token)
                                cmd = new_cmd
                                dest = self._pending_dest
                            elif cmd and cmd[0] == "cp":
                                cmd = cmd[:-1] + [str(self._pending_dest)]
                                dest = self._pending_dest
                            else:
                                cmd[-1] = str(self._pending_dest)
                                dest = self._pending_dest
                            self.job.proposed_output = str(dest)

                    # dd size estimation
                    expected_bytes: Optional[int] = None
                    if is_dd:
                        try:
                            out = subprocess.run(
                                ["blockdev", "--getsize64", self.job.drive],
                                capture_output=True, text=True, check=False
                            ).stdout.strip()
                            expected_bytes = int(out) if out.isdigit() else None
                        except Exception:
                            expected_bytes = None

                    # optional MakeMKV progress file
                    makemkv_progress_path = self.job.temp_path / "makemkv_progress.txt" if is_makemkv else None

                    # lock output edits once we’re writing to a final destination
                    if dest is not None:
                        self.job.output_locked = True

                    # ensure destination directory exists (mkdir -p)
                    try:
                        if dest is not None:
                            dest.parent.mkdir(parents=True, exist_ok=True)
                    except Exception as _e:
                        self._emit_output(f"[TKAR] Could not create output directory '{dest.parent}': {_e}")
                        self.job.mark_failed()
                        return

                    # spawn
                    self.process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        preexec_fn=os.setsid if hasattr(os, "setsid") else None
                    )

                    # stream + parse
                    for raw_line in iter(self.process.stdout.readline, ""):
                        if self._cancelled:
                            break

                        chunk = raw_line.rstrip("\n")
                        if "\r" in chunk:
                            parts = [p for p in chunk.split("\r") if p]
                            line = parts[-1] if parts else ""
                        else:
                            line = chunk

                        # log memory + file + WS
                        self.job.append_stdout(line)
                        try:
                            log_file.write(line + "\n")
                        except Exception:
                            pass
                        self._emit_output(line)

                        # progress parsing
                        step_pct: Optional[float] = None
                        title_pct: Optional[float] = None

                        if is_makemkv:
                            p = _makemkv_percent_from_file(makemkv_progress_path)
                            step_pct = p if p is not None else _find_percent(line)
                            title_pct = step_pct

                        elif is_handbrake:
                            m = re.search(r"task\s+(\d+)\s+of\s+(\d+),\s*([0-9]+(?:\.[0-9]+)?)\s*%", line, re.I)
                            if m:
                                title_pct = float(m.group(3))
                            step_pct = _find_percent(line) if title_pct is None else title_pct

                        elif is_dd:
                            p = _dd_percent_from_line(line, expected_bytes)
                            step_pct = p if p is not None else _find_percent(line)

                        elif "abcde" in cmd_str or "ripping & encoding audio cd" in low_desc:
                            step_pct = _find_percent(line)

                        elif is_compress:
                            step_pct = _find_percent(line)

                        if title_pct is not None:
                            self.job.title_progress = int(max(0.0, min(100.0, title_pct)))

                        if step_pct is not None:
                            sp = max(0.0, min(100.0, step_pct))
                            self.job.step_progress = int(sp)
                            total = total_done_weight + (weight * (sp / 100.0))
                            self.job.progress = int(round(total * 100.0))

                    rc = 0 if self._cancelled else self.process.wait()
                    if not self._cancelled and rc == 0:
                        self.job.step_progress = 100
                        total_done_weight += weight
                        self.job.progress = int(round(total_done_weight * 100.0))
                    if release_after:
                        drive_tracker.release_drive(self.job.drive)
                        subprocess.run(["eject", self.job.drive], check=False)
                    if rc != 0 and not self._cancelled:
                        self.job.mark_failed()
                        self._emit_output(f"[TKAR] Step failed: {description} (rc={rc})")
                        break

                if not self._cancelled and self.job.status != "Failed":
                    self.job.mark_finished()
                    self.job.progress = 100
                    self.job.step_progress = 100
                    self.job.title_progress = 100

        except Exception as e:
            self.job.mark_failed()
            self._emit_output(f"[TKAR] Runner crashed: {e}")
