# app/core/drive/detector/macos.py

import time
import subprocess
import re
from typing import List

from app.core.drive.manager import drive_tracker
from app.core.job.tracker import job_tracker
from app.core.drive.mac_state import (
    drive_id_for,
    update_mapping,
    forget_drive,
)


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
    Probe `drutil status -drive N` across a reasonable range to discover drives.

    `drutil list` is unreliable with some USB enclosures; status probing tends
    to be more consistent when multiple drives are attached.
    """
    indices: list[int] = []
    for idx in range(0, 12):
        status_out = _safe_run(["drutil", "status", "-drive", str(idx)])
        if status_out.strip():
            indices.append(idx)
    return sorted(set(indices))


def _status_device(index: int) -> tuple[str | None, str | None]:
    """
    Return (device_path, type_string) from drutil status for a given index.
    """
    if index == 0:
        out = _safe_run(["drutil", "status"])
        if not out.strip():
            out = _safe_run(["drutil", "status", "-drive", "0"])
    else:
        out = _safe_run(["drutil", "status", "-drive", str(index)])

    if not out.strip():
        return (None, None)

    dev_path = None
    type_str = None
    for line in out.splitlines():
        m_dev = re.search(r"Name:\s+(/dev/disk\S+)", line)
        if m_dev:
            dev_path = m_dev.group(1)
        if line.strip().startswith("Type:"):
            type_str = line.split(":", 1)[1].strip()
    return (dev_path, type_str)


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
    miss_counts: dict[str, int] = {}

    while True:
        indices = _list_optical_drives()
        current_ids: set[str] = set()
        device_owner = {
            d.device: d.path for d in drive_tracker.get_all_drives() if d.device
        }

        # --- Add new drives ---
        for idx in indices:
            dev_path, type_str = _status_device(idx)
            drive_id = drive_id_for(idx, dev_path)
            if dev_path:
                update_mapping(drive_id, dev_path)

            current_ids.add(drive_id)

            if not drive_tracker.get_drive(drive_id):
                model = _get_drive_model(idx)
                cap = _get_drive_capability(idx)
                drive_tracker.register_drive(
                    path=drive_id, model=model, capability=cap, device=dev_path
                )
                print(f"📦 Registered drive: {drive_id} ({model}) [{cap}]")
            else:
                # update device if we learned it
                if dev_path:
                    drive_tracker.set_device(drive_id, dev_path)

        # --- Remove stale drives ---
        tracked_devs = {d.path for d in drive_tracker.get_all_drives()}
        for dev in tracked_devs - current_ids:
            miss_counts[dev] = miss_counts.get(dev, 0) + 1
            # tolerate a couple of empty/failed drutil polls before treating as gone
            if miss_counts[dev] < 3:
                continue

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
            forget_drive(dev)
            miss_counts.pop(dev, None)

        # reset miss counter for drives that are present again
        for dev in tracked_devs & current_ids:
            miss_counts.pop(dev, None)

        time.sleep(interval)
