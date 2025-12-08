# app/core/drive/detector/macos.py

import time
import subprocess
import re
from typing import List

from app.core.drive.manager import drive_tracker
from app.core.job.tracker import job_tracker


def _safe_run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout or ""
    except Exception:
        return ""


def _list_optical_drives() -> list[int]:
    """
    Use `drutil list` to enumerate attached optical drives.

    Returns a list of drive indices: [0, 1, ...].

    If `drutil list` is empty but `drutil info` works, we fall back to [0].
    """
    out = _safe_run(["drutil", "list"])
    indices: list[int] = []

    for line in out.splitlines():
        m = re.match(r"\s*(\d+):\s+(.*)$", line.strip())
        if not m:
            continue
        idx = int(m.group(1))
        indices.append(idx)

    # Fallback: some macOS / drives don't give a nice "0: ..." line in `drutil list`,
    # but `drutil info` still works. Assume single drive at index 0 in that case.
    if not indices:
        info_out = _safe_run(["drutil", "info"])
        if info_out.strip():
            indices = [0]

    return indices


def _get_drive_model(index: int) -> str:
    """
    Use `drutil info -drive <index>` (or `drutil info` for index 0 fallback)
    to get a human-readable model name.
    """
    if index == 0:
        info = _safe_run(["drutil", "info"])
        # If the fallback didn't work, try explicit -drive 0
        if not info.strip():
            info = _safe_run(["drutil", "info", "-drive", "0"])
    else:
        info = _safe_run(["drutil", "info", "-drive", str(index)])

    if not info:
        return "Unknown"

    model = None
    lines = [ln.strip() for ln in info.splitlines() if ln.strip()]

    # Skip header, then take first non-header, non "Foo: Bar" line.
    for line in lines:
        lower = line.lower()
        if lower.startswith("vendor") and "product" in lower:
            continue
        if ":" in line:
            # lines like "Interconnect: USB"
            continue
        # Something like "HL-DT-ST BD-RE  BH16NS55   1.02"
        model = line.strip()
        break

    return model or "Unknown"


def _get_drive_capability(index: int) -> List[str]:
    """
    Infer capabilities (CD/DVD/BLURAY) from `drutil info` output.
    """
    if index == 0:
        info = _safe_run(["drutil", "info"])
        if not info.strip():
            info = _safe_run(["drutil", "info", "-drive", "0"])
    else:
        info = _safe_run(["drutil", "info", "-drive", str(index)])

    info = info.lower()
    if not info:
        return []

    caps = set()
    if "bd-write" in info or "bd-re" in info or "blu-ray" in info or "bluray" in info:
        caps.update(["BLURAY", "DVD", "CD"])
    if "dvd-write" in info or "dvd-rom" in info:
        caps.update(["DVD", "CD"])
    if "cd-write" in info or "cd-rom" in info:
        caps.add("CD")

    return sorted(caps)


def poll_for_drives(interval: int = 5):
    """
    Poll attached optical drives on macOS and sync with DriveTracker.

    Drives are identified by logical IDs:
        DRIVE0, DRIVE1, ...

    This means they appear in the UI even when empty (like Linux/Windows),
    and we can still distinguish multiple drives.
    """
    while True:
        indices = _list_optical_drives()
        current_ids = {f"DRIVE{idx}" for idx in indices}

        # --- Add new drives ---
        for idx in indices:
            drive_id = f"DRIVE{idx}"
            if not drive_tracker.get_drive(drive_id):
                model = _get_drive_model(idx)
                cap = _get_drive_capability(idx)
                drive_tracker.register_drive(path=drive_id, model=model, capability=cap)
                print(f"📦 Registered drive: {drive_id} ({model}) [{cap}]")

        # --- Remove stale drives ---
        tracked_devs = {d.path for d in drive_tracker.get_all_drives()}
        for dev in tracked_devs - current_ids:
            d = drive_tracker.get_drive(dev)
            if d:
                if d.job_id:
                    job = job_tracker.get_job(d.job_id)
                    if job and job.runner:
                        job.runner.cancel()
                        print(f"❌ Cancelled job {d.job_id} due to drive removal: {dev}")
                    else:
                        print(
                            f"⚠️ Could not find runner for job {d.job_id} during unplug of {dev}"
                        )
                drive_tracker.unregister_drive(dev)
                print(f"🗑️ Unregistered unplugged drive: {dev}")

        time.sleep(interval)
