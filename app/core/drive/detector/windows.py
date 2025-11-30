# app/core/drive/detector/windows.py

import time
import json
import subprocess
from typing import List, Set, Optional
from ctypes import windll

from app.core.drive.manager import drive_tracker
from app.core.job.tracker import job_tracker

# WinAPI constant for GetDriveTypeW
DRIVE_CDROM = 5


def _iter_cdrom_drive_letters() -> Set[str]:
    """
    Return a set of drive letters (like 'D:') that are CD/DVD/BD drives
    according to GetDriveTypeW.
    """
    drive_bits = windll.kernel32.GetLogicalDrives()
    letters: Set[str] = set()

    for i in range(26):
        if drive_bits & (1 << i):
            letter = chr(ord("A") + i)
            root_path = f"{letter}:\\"

            # GetDriveTypeW returns DRIVE_CDROM for optical drives
            drive_type = windll.kernel32.GetDriveTypeW(root_path)
            if drive_type == DRIVE_CDROM:
                # Use 'D:' style path as our canonical identifier
                letters.add(f"{letter}:")

    return letters


def _ps_query_cdrom(drive: str) -> Optional[dict]:
    """
    Use PowerShell + CIM to get info for a specific optical drive.

    drive: 'D:' (no trailing backslash)

    Returns a dict with keys like Drive, Name, MediaType, or None if not found.
    """
    drive = drive.rstrip("\\/")

    try:
        # This PowerShell command:
        #   Get-CimInstance -ClassName Win32_CDROMDrive |
        #   Where-Object {$_.Drive -eq 'D:'} |
        #   Select-Object Drive,Name,MediaType |
        #   ConvertTo-Json -Compress
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "Get-CimInstance -ClassName Win32_CDROMDrive "
                f"| Where-Object {{ $_.Drive -eq '{drive}' }} "
                "| Select-Object Drive,Name,MediaType "
                "| ConvertTo-Json -Compress"
            ),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )

        out = result.stdout.strip()
        if not out:
            return None

        data = json.loads(out)
        # ConvertTo-Json returns either a single object or an array
        if isinstance(data, list):
            if not data:
                return None
            return data[0]

        return data

    except Exception:
        # If PowerShell or CIM is unavailable, just return None
        return None


def _get_drive_model(drive: str) -> str:
    """
    Get a human-readable model/name for the drive, using PowerShell + CIM.
    """
    info = _ps_query_cdrom(drive)
    if not info:
        return "Unknown"

    name = info.get("Name") or ""
    name = name.strip()
    return name or "Unknown"


def _get_drive_capability(drive: str) -> List[str]:
    """
    Heuristic capability detection using MediaType and Name reported by WMI/CIM.
    Maps to the same labels as the Linux version:
      - 'CD'
      - 'DVD'
      - 'BLURAY'
    """
    info = _ps_query_cdrom(drive)
    if not info:
        return []

    media_type = (info.get("MediaType") or "").upper()
    name = (info.get("Name") or "").upper()
    text = f"{media_type} {name}"

    caps = set()

    if "CD" in text:
        caps.add("CD")
    if "DVD" in text:
        caps.add("DVD")
    # Blu-ray can show up as BD / BLURAY / BLU-RAY / BLU RAY
    if any(x in text for x in ("BD", "BLURAY", "BLU-RAY", "BLU RAY")):
        caps.add("BLURAY")

    return sorted(caps)


def poll_for_drives(interval: int = 5):
    """
    Poll optical drives on Windows and sync with DriveTracker.

    Linux version uses `/dev/sr*` paths; here we use drive letters like 'D:' as
    the .path when registering with drive_tracker.
    """
    while True:
        # Discover currently present optical drives
        current_devs = _iter_cdrom_drive_letters()

        # Add new drives
        for dev in current_devs:
            if not drive_tracker.get_drive(dev):
                model = _get_drive_model(dev)
                cap = _get_drive_capability(dev)
                drive_tracker.register_drive(path=dev, model=model, capability=cap)
                print(f"📦 Registered drive: {dev} ({model}) [{cap}]")

        # Remove stale drives
        tracked_devs = {d.path for d in drive_tracker.get_all_drives()}
        for dev in tracked_devs - current_devs:
            d = drive_tracker.get_drive(dev)
            if d:
                if d.job_id:
                    job = job_tracker.get_job(d.job_id)
                    if job and job.runner:
                        job.runner.cancel()
                        print(f"❌ Cancelled job {d.job_id} due to drive removal: {dev}")
                    else:
                        print(
                            f"⚠️ Could not find runner for job {d.job_id} "
                            f"during unplug of {dev}"
                        )
                drive_tracker.unregister_drive(dev)
                print(f"🗑️ Unregistered unplugged drive: {dev}")

        time.sleep(interval)
