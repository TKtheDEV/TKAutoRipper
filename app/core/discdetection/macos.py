# app/core/discdetection/macos.py

import subprocess
import time
import logging
import re

from ..api_helpers import post_api
from ..configmanager import config  # not used yet, kept for structure
from app.core.drive.manager import drive_tracker
from app.core.drive.mac_state import (
    drive_id_for,
    update_mapping,
    device_for_drive,
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
        t, d = _drutil_status(idx)
        if t or d:
            indices.append(idx)
    return sorted(set(indices))


def _drutil_status(index: int) -> tuple[str | None, str | None]:
    """
    Run `drutil status -drive <index>` (or fallback `drutil status`)
    and return (type, device_path) where type is e.g.:

        "No Media Inserted"
        "DVD-ROM"
        "CD-DA"
        "BD-RE"
    """
    if index == 0:
        cmd = ["drutil", "status"]
        out = _safe_run(cmd)
        if not out.strip():
            out = _safe_run(cmd + ["-drive", "0"])
    else:
        cmd = ["drutil", "status", "-drive", str(index)]
        out = _safe_run(cmd)

    if not out:
        return (None, None)

    type_str: str | None = None
    dev_path: str | None = None

    for raw_line in out.splitlines():
        line = raw_line.strip()
        if line.startswith("Type:"):
            type_str = line.split(":", 1)[1].strip()
        m = re.search(r"Name:\s+(/dev/disk\S+)", line)
        if m:
            dev_path = m.group(1)
    return (type_str, dev_path)


def _diskutil_content(dev_path: str) -> str:
    """
    Return the Content/IOContent line from `diskutil info`, lowercased.
    """
    try:
        res = subprocess.run(
            ["diskutil", "info", dev_path],
            capture_output=True,
            text=True,
            check=False,
        )
        out = res.stdout or ""
        for line in out.splitlines():
            m = re.search(r"Content.*:\s*(.+)", line)
            if m:
                return m.group(1).strip().lower()
    except Exception:
        pass
    return ""


def _classify_disc_from_type(type_str: str, dev_path: str | None) -> str:
    """
    Classification from `drutil status` Type line with a diskutil content hint.
    """
    t = (type_str or "").lower()

    if "no media" in t:
        return "unknown"

    if "cd-da" in t or "audio" in t:
        return "cd_audio"
    if "bd" in t or "blu-ray" in t or "bluray" in t:
        return "bluray_video"
    if "dvd" in t:
        return "dvd_video"
    if "cd" in t:
        # If diskutil says audio/cdda treat as audio, otherwise CD-ROM
        content = _diskutil_content(dev_path) if dev_path else ""
        if any(x in content for x in ["audio", "cdda", "cd-da"]):
            return "cd_audio"
        return "cd_rom"

    # Fallback: look at diskutil content hint
    content = _diskutil_content(dev_path) if dev_path else ""
    if any(x in content for x in ["audio", "cdda", "cd-da"]):
        return "cd_audio"
    if "udf" in content or "iso" in content:
        return "dvd_video"

    return "other_disc"


def monitor_cdrom():
    """
    macOS implementation of disc monitoring.

    API-level behavior mirrors Linux:

      - On disc insertion in DRIVE<N>:
          POST /api/drives/insert
              { "drive": "DRIVE<N>", "disc_type": ..., "disc_label": ... }

      - On disc removal/eject from DRIVE<N>:
          POST /api/drives/remove
              { "drive": "DRIVE<N>" }

    We don't have a reliable label here, so we use "unknown".
    """
    logging.info("Starting macOS CDROM monitor")

    # known_media[drive_id] = bool (True if disc present)
    known_media: dict[str, bool] = {}
    # drive_devices[drive_id] = last seen /dev/diskN mapping (if any)
    # consecutive polls where a drive was missing from drutil list
    miss_counts: dict[str, int] = {}
    poll_interval = 3

    while True:
        indices = _list_optical_drives()
        current_ids: set[str] = set()
        for idx in indices:
            type_str, dev_path = _drutil_status(idx)
            if type_str is None:
                # drutil failed for this drive; keep previous state
                continue

            drive_id = drive_id_for(idx, dev_path)

            # If drutil didn't give a device, use the last known one for this drive
            dev_path = dev_path or device_for_drive(drive_id)

            has_media = bool(type_str and "no media" not in type_str.lower())
            prev = known_media.get(drive_id, False)
            current_ids.add(drive_id)

            if has_media and dev_path:
                update_mapping(drive_id, dev_path)
                drv = drive_tracker.get_drive(drive_id)
                if not drv:
                    drive_tracker.register_drive(
                        path=drive_id,
                        model="Unknown",
                        capability=["Unknown"],
                        device=dev_path,
                    )
                else:
                    drive_tracker.set_device(drive_id, dev_path)

            # Remove event
            if prev and not has_media:
                logging.info(f"Disc removed/ejected from {drive_id}")
                try:
                    post_api("/api/drives/remove", {"drive": drive_id})
                except Exception as e:
                    logging.warning(f"Could not notify backend of remove: {e}")

            # Insert event
            if not prev and has_media:
                logging.info(f"Disc inserted in {drive_id}")
                time.sleep(2)  # debounce

                disc_type = _classify_disc_from_type(type_str or "", dev_path)
                disc_label = "unknown"

                logging.info(f"{disc_type.upper()} detected in {drive_id}")
                if dev_path:
                    logging.info(f"Mapping {drive_id} → {dev_path}")

                try:
                    post_api(
                        "/api/drives/insert",
                        {
                            "drive": drive_id,
                            "disc_type": disc_type,
                            "disc_label": disc_label,
                        },
                    )
                except Exception as e:
                    logging.error(
                        f"Detection or job creation failed for {drive_id}: {e}"
                    )

            known_media[drive_id] = has_media

        # Handle disappearing drives after processing current indices
        for drive_id in list(known_media.keys()):
            if drive_id not in current_ids:
                miss_counts[drive_id] = miss_counts.get(drive_id, 0) + 1
                if miss_counts[drive_id] < 3:
                    continue
                if known_media.get(drive_id, False):
                    logging.info(
                        f"Drive disappeared after {miss_counts[drive_id]} polls, assuming disc removed: {drive_id}"
                    )
                    try:
                        post_api("/api/drives/remove", {"drive": drive_id})
                    except Exception as e:
                        logging.warning(
                            f"Could not notify backend of remove for {drive_id}: {e}"
                        )
                known_media.pop(drive_id, None)
                forget_drive(drive_id)
                miss_counts.pop(drive_id, None)
            else:
                miss_counts.pop(drive_id, None)

        time.sleep(poll_interval)
