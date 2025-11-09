# app/core/drive/detector/linux.py
import os
import time
import subprocess
from typing import List, Optional
from app.core.drive.manager import drive_tracker
from app.core.job.tracker import job_tracker

def _get_drive_model(dev: str) -> str:
    try:
        result = subprocess.run(["udevadm", "info", "--query=all", "--name", dev],
                                capture_output=True, text=True, check=True)
        for line in result.stdout.splitlines():
            if "ID_MODEL=" in line:
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return "Unknown"

def _get_drive_capability(dev: str) -> List[str]:
    try:
        result = subprocess.run(["udevadm", "info", "--query=all", "--name", dev],
                                capture_output=True, text=True, check=True)
        caps = set()
        for line in result.stdout.splitlines():
            if "ID_CDROM_DVD" in line:
                caps.add("DVD")
            if "ID_CDROM_CD" in line:
                caps.add("CD")
            if "ID_CDROM_BD" in line:
                caps.add("BLURAY")
        return sorted(caps)
    except Exception:
        return []

def poll_for_drives(interval: int = 5):
    """Poll /dev/sr* and sync with DriveTracker."""
    while True:
        current_devs = {f"/dev/{dev}" for dev in os.listdir("/dev") if dev.startswith("sr")}

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
                        print(f"⚠️ Could not find runner for job {d.job_id} during unplug of {dev}")
                drive_tracker.unregister_drive(dev)
                print(f"🗑️ Unregistered unplugged drive: {dev}")


        time.sleep(interval)
