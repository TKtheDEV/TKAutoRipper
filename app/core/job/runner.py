# app/core/job/runner.py
from __future__ import annotations

import logging
import os
import platform
import re
import shlex
import signal
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple, Any
from fastapi import HTTPException

from app.core.drive.manager import drive_tracker
from .job import Job

_PLATFORM = platform.system()
IS_WINDOWS = _PLATFORM == "Windows"
IS_DARWIN = _PLATFORM == "Darwin"

# --------------------- step resolution ----------------------
def get_job_steps(job: Job) -> List[Tuple]:
    """
    Resolve disc type to the proper ripper and return the step tuples.

    Step tuple shapes supported (raw from rippers):
      (cmd, description, release_drive)
      (cmd, description, release_drive, weight)
      (cmd, description, release_drive, dest)
      (cmd, description, release_drive, progress_adapter)
      (cmd, description, release_drive, weight, dest)
      (cmd, description, release_drive, weight, dest, progress_adapter)

    The runner normalises them internally.
    """
    dtype = (job.disc_type or "").lower()

    # NOTE:
    #   On Windows we currently implement only the VIDEO rippers.
    #   ROM/audio rippers are Linux-only for now.
    if dtype == "cd_audio":
        if IS_WINDOWS:
            from app.core.rippers.audio.windows import rip_audio_cd
        elif IS_DARWIN:
            from app.core.rippers.audio.macos import rip_audio_cd
        else:
            from app.core.rippers.audio.linux import rip_audio_cd
        return rip_audio_cd(job)

    if dtype in ("cd_rom", "dvd_rom", "bluray_rom", "other_disc"):
        if IS_WINDOWS:
            from app.core.rippers.other.windows import rip_generic_disc
        elif IS_DARWIN:
            from app.core.rippers.other.macos import rip_generic_disc
        else:
            from app.core.rippers.other.linux import rip_generic_disc
        return rip_generic_disc(job)

    if dtype == "dvd_video":
        if IS_WINDOWS:
            from app.core.rippers.video.windows import rip_video_disc
        elif IS_DARWIN:
            from app.core.rippers.video.macos import rip_video_disc
        else:
            from app.core.rippers.video.linux import rip_video_disc
        return rip_video_disc(job, "DVD")

    if dtype == "bluray_video":
        if IS_WINDOWS:
            from app.core.rippers.video.windows import rip_video_disc
        elif IS_DARWIN:
            from app.core.rippers.video.macos import rip_video_disc
        else:
            from app.core.rippers.video.linux import rip_video_disc
        return rip_video_disc(job, "BLURAY")

    raise ValueError(f"Unsupported disc type: {dtype}")


# ---------------------- progress helpers ----------------------
_percent_re = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%")

# ── MakeMKV PRGV file parsing (title, overall, max=65536) ──
_PRGV_RE = re.compile(r"PRGV:(\d+),(\d+),(\d+)")


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


def _read_last_prgv(path: Path) -> tuple[Optional[float], Optional[float]]:
    """
    Returns (title_pct, step_pct) in 0..100 from makemkv_progress.txt.
    Reverse-scan to parse the most recent PRGV line.
    """
    try:
        if not path or not path.exists():
            return (None, None)
        lines = path.read_text(errors="ignore").splitlines()
        for line in reversed(lines):
            m = _PRGV_RE.search(line)
            if not m:
                continue
            title_v = float(m.group(1))
            step_v = float(m.group(2))
            max_v = float(m.group(3)) or 65536.0

            def pct(v: float) -> float:
                v = max(0.0, min(v, max_v))
                return (v / max_v) * 100.0

            return (pct(title_v), pct(step_v))
        return (None, None)
    except Exception:
        return (None, None)


def _start_makemkv_watcher(
    progress_path: Path,
    job: Job,
    stop_evt: threading.Event,
    weight: float,
    total_done_weight: float,
) -> threading.Thread:
    """
    Background thread: poll makemkv_progress.txt 5×/sec and update
    job.step_progress, job.title_progress and job.progress.
    """

    def run():
        last_step = -1
        last_title = -1
        while not stop_evt.is_set():
            t_pct, s_pct = _read_last_prgv(progress_path)
            changed = False
            if s_pct is not None:
                sp = int(max(0.0, min(100.0, s_pct)))
                if sp != last_step:
                    last_step = sp
                    job.step_progress = sp
                    total = total_done_weight + (weight * (sp / 100.0))
                    job.progress = int(round(total * 100.0))
                    changed = True
            if t_pct is not None:
                tp = int(max(0.0, min(100.0, t_pct)))
                if tp != last_title:
                    last_title = tp
                    job.title_progress = tp
                    changed = True
            if changed:
                try:
                    job.save_state()
                except Exception:
                    pass
            stop_evt.wait(0.2)  # ~5 Hz

    th = threading.Thread(target=run, daemon=True)
    th.start()
    return th


# ---------------------- weighting policies ----------------------
ROM_WEIGHTS = {
    "cd_rom": (0.50, 0.50),
    "dvd_rom": (0.60, 0.40),
    "bluray_rom": (0.70, 0.30),
    "other_disc": (0.60, 0.40),
}
VIDEO_WEIGHTS = {
    "dvd_video": (0.60, 0.40),
    "bluray_video": (0.70, 0.30),
}

# ---------------------- output lock policy ----------------------
def _lock_index_for(dtype: str, steps_count: int) -> int | None:
    """
    Return the 1-based step index at which we should lock (and create) output path,
    or None if we never lock (cd_audio).

    Policy:
      - dvd_video / bluray_video:       2
      - *rom / other_disc:              2 if exists, else after step 1 finishes (encoded as 0)
      - cd_audio:                       None (abcde manages folders)
    """
    d = (dtype or "").lower()
    if d in {"dvd_video", "bluray_video"}:
        return 2
    if d in {"cd_rom", "dvd_rom", "bluray_rom", "other_disc"}:
        return 2 if steps_count >= 2 else 0  # 0 = lock after step 1 completes
    if d == "cd_audio":
        return None
    return 2

# ---------------------- drive eject helper ----------------------
def _eject_drive(drive: str) -> None:
    """
    Cross-platform drive eject helper.

    On Linux/BSD: uses the 'eject' command.
    On Windows: uses Shell.Application COM object and the 'Eject' verb
                on the drive (e.g. 'E:\\').
    On macOS:   uses 'drutil tray eject -drive <index>' for DRIVE<N> IDs.
    """
    if not drive:
        return

    try:
        if IS_WINDOWS:
            # Ensure Windows-style "E:\" form for the Shell API.
            ps_drive = drive.rstrip("\\") + "\\"
            ps_script = (
                "$ErrorActionPreference = 'Stop'; "
                f"$drive = '{ps_drive}'; "
                "$shell = New-Object -ComObject Shell.Application; "
                "$ns = $shell.NameSpace(17); "
                "$item = $ns.ParseName($drive); "
                "if ($item -ne $null) { $item.InvokeVerb('Eject') } "
                "else { throw 'Drive not found for eject' }"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                check=True,
            )

        elif IS_DARWIN:
            cmd = ["drutil", "tray", "eject", drive]
            subprocess.run(cmd, check=True)

        else:
            # Linux / other Unix-like: assume a real device node, e.g. /dev/sr0
            subprocess.run(["eject", drive], check=True)

    except subprocess.CalledProcessError as e:
        logging.warning(f"⚠️ Eject command failed for {drive}: {e}")
        raise HTTPException(status_code=500, detail=f"Eject failed: {e}")
    except Exception as e:
        logging.error(f"Unexpected error ejecting {drive}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Unexpected eject error: {e}"
        )

# ======================== Runner ==============================
class JobRunner:
    def __init__(self, job: Job, on_output: Optional[Callable[[str], None]] = None) -> None:
        self.job = job
        self.job.runner = self

        # multi-listener fan-out (WS + file)
        self._output_listeners: List[Callable[[str], None]] = []
        if on_output:
            self._output_listeners.append(on_output)

        self.process: Optional[subprocess.Popen] = None
        self._cancelled = False

        # progress
        self.job.title_progress = 0

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
        threading.Thread(target=self._run_steps, args=(1,), daemon=True).start()

    def retry_from_last(self) -> None:
        """
        Start from the step AFTER the last successful one.
        Caller guarantees job.step >= 2 (API side).
        """
        current_step = int(getattr(self.job, "step", 1) or 1)
        # If the current step was incomplete, retry it; otherwise move to the next one.
        step_progress = int(getattr(self.job, "step_progress", 0) or 0)
        start_index = current_step if step_progress < 100 else current_step + 1
        start_index = max(1, start_index)
        threading.Thread(target=self._run_steps, args=(start_index,), daemon=True).start()

    def cancel(self) -> None:
        self._cancelled = True
        if self.process:
            try:
                if IS_WINDOWS:
                    self.process.terminate()
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except Exception:
                pass
        self.job.status = "Cancelled"
        drive_tracker.release_drive(self.job.drive)
        _eject_drive(self.job.drive)

    # ---------------- internal ------------------
    def _run_steps(self, start_index: int = 1) -> None:
        try:
            self.job.temp_path.mkdir(parents=True, exist_ok=True)
            log_path = self.job.temp_path / "log.txt"
            with log_path.open("a", buffering=1) as log_file:
                self.job.status = "Running"

                raw_steps = get_job_steps(self.job)
                # normalised: (cmd, desc, release_after, weight, dest, progress_adapter)
                steps: List[Tuple[List[str], str, bool, float, Optional[Path], Any]] = []

                dtype = (self.job.disc_type or "").lower()
                is_rom = dtype in {"cd_rom", "dvd_rom", "bluray_rom", "other_disc"}
                is_video = dtype in {"dvd_video", "bluray_video"}

                # normalize weights / dest / progress adapter
                def _has_adapter(x: Any) -> bool:
                    return hasattr(x, "on_line") or callable(x)

                def norm_step(s, default_weight: float):
                    if len(s) == 3:
                        cmd, desc, rel = s
                        return (cmd, desc, rel, default_weight, None, None)
                    if len(s) == 4:
                        cmd, desc, rel, x = s
                        if isinstance(x, (int, float)):
                            return (cmd, desc, rel, float(x), None, None)
                        if _has_adapter(x):
                            return (cmd, desc, rel, default_weight, None, x)
                        # assume dest
                        return (cmd, desc, rel, default_weight, x, None)
                    if len(s) == 5:
                        cmd, desc, rel, a, b = s
                        if isinstance(a, (int, float)):
                            # (cmd, desc, rel, weight, dest/adapter)
                            if _has_adapter(b):
                                return (cmd, desc, rel, float(a), None, b)
                            return (cmd, desc, rel, float(a), b, None)
                        # (cmd, desc, rel, dest, adapter?)
                        adapter = b if _has_adapter(b) else None
                        dest = a
                        return (cmd, desc, rel, default_weight, dest, adapter)
                    if len(s) == 6:
                        cmd, desc, rel, weight, dest, adapter = s
                        return (cmd, desc, rel, float(weight), dest, adapter)
                    raise ValueError("Invalid step tuple length")

                if dtype == "cd_audio":
                    for s in raw_steps:
                        steps.append(norm_step(s, 1.0))
                elif dtype in ROM_WEIGHTS:
                    w1, w2 = ROM_WEIGHTS[dtype]
                    for i, s in enumerate(raw_steps):
                        steps.append(norm_step(s, w1 if i == 0 else w2))
                elif dtype in VIDEO_WEIGHTS:
                    w1, w2 = VIDEO_WEIGHTS[dtype]
                    for i, s in enumerate(raw_steps):
                        steps.append(norm_step(s, w1 if i == 0 else w2))
                else:
                    n = max(1, len(raw_steps))
                    w = 1.0 / n
                    for s in raw_steps:
                        steps.append(norm_step(s, w))

                self.job.steps_total = len(steps)
                lock_at = _lock_index_for(self.job.disc_type, len(steps))

                # prefill total progress if resuming past some steps
                total_done_weight = 0.0
                if start_index > 1:
                    for i, (_c, _d, _r, w, _dest, _ad) in enumerate(steps, start=1):
                        if i < start_index:
                            total_done_weight += w
                    self.job.progress = int(round(total_done_weight * 100.0))
                    self.job.step = start_index

                for idx, step_tuple in enumerate(steps, start=1):
                    if idx < start_index:
                        continue
                    if self._cancelled:
                        break

                    cmd, description, release_after, weight, dest, progress_adapter = step_tuple

                    # --- Rebuild steps at runtime to pick up renamed output paths (ROM/VIDEO)
                    if (is_rom or is_video) and idx >= 2:
                        fresh_raw = get_job_steps(self.job)
                        if 1 <= idx <= len(fresh_raw):
                            fresh = fresh_raw[idx - 1]
                            # re-normalise using existing weight
                            f_cmd, f_desc, f_rel, _fw, f_dest, f_ad = norm_step(fresh, weight)
                            cmd, description, release_after, dest, progress_adapter = (
                                f_cmd,
                                f_desc,
                                f_rel,
                                f_dest,
                                f_ad,
                            )

                    self.job.step = idx
                    self.job.step_description = description
                    self.job.step_progress = 0
                    self.job.title_progress = 0
                    try:
                        self.job.save_state()
                    except Exception:
                        pass

                    # tool detection (generic; no OS-specific bits here)
                    cmd_str = " ".join(shlex.quote(str(x)) for x in cmd)
                    low_desc = description.lower()
                    is_makemkv = "makemkv" in cmd_str.lower() or "makemkv" in low_desc
                    is_handbrake = "handbrakecli" in cmd_str.lower() or "handbrake" in low_desc
                    is_compress = any(
                        x in cmd_str.lower() for x in ("zstd", "bzip2", "bz2")
                    ) or "compressing" in low_desc

                    makemkv_progress_path: Optional[Path] = None
                    mm_stop_evt: Optional[threading.Event] = None
                    mm_thread: Optional[threading.Thread] = None

                    # HandBrake title counting data
                    hb_total_titles: Optional[int] = None

                    if is_makemkv:
                        makemkv_progress_path = self.job.temp_path / "makemkv_progress.txt"

                    if is_handbrake:
                        try:
                            hb_total_titles = sum(
                                1 for _ in self.job.temp_path.rglob("*.mkv")
                            )
                        except Exception:
                            hb_total_titles = None

                    # per-step adapter state (for dd/abcde/etc; implemented in rippers)
                    adapter_state: dict = {}
                    if progress_adapter and hasattr(progress_adapter, "on_start"):
                        try:
                            progress_adapter.on_start(self.job, cmd, adapter_state)
                        except Exception:
                            pass

                    # -------- lock output at the right time --------
                    if lock_at and lock_at > 0 and not getattr(
                        self.job, "output_locked", False
                    ):
                        if idx == lock_at:
                            self.job.output_locked = True
                            try:
                                if is_rom:
                                    Path(self.job.output_path).parent.mkdir(
                                        parents=True, exist_ok=True
                                    )
                                else:
                                    Path(self.job.output_path).mkdir(
                                        parents=True, exist_ok=True
                                    )
                            except Exception:
                                pass
                            try:
                                self.job.save_state({"output_locked": True})
                            except Exception:
                                pass
                            self._emit_output("[TKAR] Output path locked")

                    # spawn (IMPORTANT: run inside the job's temp dir so MakeMKV writes PRGV here)
                    popen_kwargs = dict(
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        universal_newlines=True,
                        cwd=str(self.job.temp_path),
                    )

                    if IS_WINDOWS:
                        try:
                            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                        except AttributeError:
                            pass
                    else:
                        popen_kwargs["preexec_fn"] = os.setsid

                    self.process = subprocess.Popen(cmd, **popen_kwargs)

                    # If this is a MakeMKV step, start the PRGV watcher
                    if is_makemkv and makemkv_progress_path:
                        mm_stop_evt = threading.Event()
                        mm_thread = _start_makemkv_watcher(
                            makemkv_progress_path,
                            self.job,
                            mm_stop_evt,
                            weight,
                            total_done_weight,
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

                        # progress parsing (stdout-based)
                        step_pct: Optional[float] = None
                        title_pct: Optional[float] = None

                        if is_handbrake:
                            m = re.search(
                                r"(?:encoding:\s*)?task\s+(\d+)\s+of\s+(\d+),\s*([0-9]+(?:\.[0-9]+)?)\s*%",
                                line,
                                re.I,
                            )
                            cur_title_pct = None
                            if m:
                                cur_title_pct = float(m.group(3))
                                title_pct = cur_title_pct

                            if hb_total_titles is None or hb_total_titles == 0:
                                try:
                                    hb_total_titles = sum(
                                        1 for _ in self.job.temp_path.rglob("*.mkv")
                                    )
                                except Exception:
                                    hb_total_titles = 0

                            if (
                                hb_total_titles
                                and hb_total_titles > 0
                                and self.job.output_path
                                and Path(self.job.output_path).exists()
                            ):
                                try:
                                    produced = 0
                                    out_path = Path(self.job.output_path)
                                    for ext in ("*.mkv", "*.mp4", "*.m4v"):
                                        produced += sum(
                                            1 for _ in out_path.rglob(ext)
                                        )
                                    per_title = 100.0 / hb_total_titles
                                    in_title = (cur_title_pct or 0.0) * (
                                        per_title / 100.0
                                    )
                                    step_pct = min(
                                        100.0, produced * per_title + in_title
                                    )
                                except Exception:
                                    if cur_title_pct is not None:
                                        step_pct = cur_title_pct
                            else:
                                if cur_title_pct is not None:
                                    step_pct = cur_title_pct

                        elif is_makemkv:
                            p = _find_percent(line)
                            if p is not None:
                                step_pct = p
                                title_pct = p

                        elif is_compress:
                            step_pct = _find_percent(line)

                        # delegate extra parsing to a per-step progress adapter (dd, abcde, …)
                        if progress_adapter:
                            try:
                                if hasattr(progress_adapter, "on_line"):
                                    sp2, tp2 = progress_adapter.on_line(
                                        line, adapter_state, self.job
                                    )
                                else:
                                    sp2, tp2 = progress_adapter(
                                        line, adapter_state, self.job
                                    )
                                if sp2 is not None:
                                    step_pct = sp2
                                if tp2 is not None:
                                    title_pct = tp2
                            except Exception:
                                pass

                        if title_pct is not None:
                            self.job.title_progress = int(
                                max(0.0, min(100.0, title_pct))
                            )

                        if step_pct is not None:
                            sp = max(0.0, min(100.0, float(step_pct)))
                            self.job.step_progress = int(sp)
                            total = total_done_weight + (weight * (sp / 100.0))
                            self.job.progress = int(round(total * 100.0))

                    rc = 0 if self._cancelled else self.process.wait()

                    # stop MakeMKV watcher if we started it
                    if mm_stop_evt:
                        mm_stop_evt.set()
                    if mm_thread:
                        mm_thread.join(timeout=0.5)

                    if not self._cancelled and rc == 0:
                        self.job.step_progress = 100
                        total_done_weight += weight
                        self.job.progress = int(round(total_done_weight * 100.0))
                        try:
                            self.job.save_state()
                        except Exception:
                            pass

                        # Post-step lock for ROM/OTHER pipelines with single step (lock_at == 0)
                        if (
                            lock_at == 0
                            and idx == 1
                            and not getattr(self.job, "output_locked", False)
                        ):
                            self.job.output_locked = True
                            try:
                                if is_rom:
                                    Path(self.job.output_path).parent.mkdir(
                                        parents=True, exist_ok=True
                                    )
                                else:
                                    Path(self.job.output_path).mkdir(
                                        parents=True, exist_ok=True
                                    )
                            except Exception:
                                pass
                            try:
                                self.job.save_state({"output_locked": True})
                            except Exception:
                                pass
                            self._emit_output("[TKAR] Output path locked")

                    if release_after:
                        if self.job.drive:
                            drive_tracker.release_drive(self.job.drive)
                            _eject_drive(self.job.drive)
                        self.job.drive = None
                        try:
                            self.job.save_state({"drive": None})
                        except Exception:
                            pass

                    if rc != 0 and not self._cancelled:
                        self.job.status = "Failed"
                        self._emit_output(
                            f"[TKAR] Step failed: {description} (rc={rc})"
                        )
                        try:
                            self.job.save_state()
                        except Exception:
                            pass
                        break

                if not self._cancelled and self.job.status != "Failed":
                    self.job.status = "Finished"
                    self.job.progress = 100
                    self.job.step_progress = 100
                    self.job.title_progress = 100
                    try:
                        self.job.save_state()
                    except Exception:
                        pass

        except Exception as e:
            self.job.status = "Failed"
            self._emit_output(f"[TKAR] Runner crashed: {e}")
            try:
                self.job.save_state()
            except Exception:
                pass
