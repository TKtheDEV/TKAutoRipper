# app/core/drive/detector/macos.py

import subprocess
import time
import logging
from typing import List, Dict, Optional, Set

from app.core.api_helpers import post_api
from app.core.drive.manager import drive_tracker
from app.core.job.tracker import job_tracker
from app.core.discdetection.macos import detect_and_notify


logger = logging.getLogger(__name__)

# Keep track of whether a given logical drive currently has media
_last_media_state: Dict[str, bool] = {}


def _run_drutil_status() -> str:
    try:
        result = subprocess.run(
            ["drutil", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except Exception as e:
        logger.warning(f"drutil status failed: {e}")
        return ""


def _infer_capabilities(model: str, type_str: Optional[str]) -> List[str]:
    """
    Infer capabilities (CD / DVD / BLURAY) from model + 'Type:' string.
    """
    caps = set()
    text = (model or "") + " " + (type_str or "")

    upper = text.upper()
    if "BD" in upper or "BLU-RAY" in upper:
        caps.add("BLURAY")
    if "DVD" in upper:
        caps.add("DVD")
    if "CD" in upper:
        caps.add("CD")

    return sorted(caps)


def _parse_drutil_status(output: str) -> List[Dict]:
    """
    Parse drutil status into a list of drive infos.

    Returns a list of dicts:
    {
        "id": "macos-0",
        "model": "HL-DT-ST BD-RE  BH16NS55",
        "path": "/dev/disk4" or None,
        "type": "CD-ROM" / "No Media Inserted" / ...
    }
    """
    lines = [l.rstrip("\n") for l in output.splitlines()]
    drives: List[Dict] = []

    i = 0
    drive_index = 0

    while i < len(lines):
        line = lines[i].strip()

        # Find header line:
        #   Vendor   Product           Rev
        if line.startswith("Vendor") and "Product" in line and "Rev" in line:
            # Next non-empty line should contain the Vendor/Product/Rev values
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines):
                break

            vp_line = lines[i].strip()
            # Example: "HL-DT-ST DVDRAM GSA-E50L   NE02"
            parts = vp_line.split()
            if len(parts) >= 2:
                rev = parts[-1]
                vendor_product = " ".join(parts[:-1])
            else:
                rev = ""
                vendor_product = vp_line

            model = vendor_product
            drive_id = f"macos-{drive_index}"

            drive_info: Dict[str, Optional[str]] = {
                "id": drive_id,
                "model": model,
                "path": None,
                "type": None,
                "rev": rev,
            }

            # Look ahead for the "Type:" line for this drive
            j = i + 1
            while j < len(lines):
                tline = lines[j].strip()
                if not tline:
                    j += 1
                    continue

                # Another header => next drive
                if tline.startswith("Vendor") and "Product" in tline and "Rev" in tline:
                    break

                if tline.startswith("Type:"):
                    # Examples:
                    # "Type: No Media Inserted"
                    # "Type: CD-ROM               Name: /dev/disk4"
                    seg = tline[len("Type:") :].strip()
                    type_part = seg
                    name_part = None

                    if "Name:" in seg:
                        before, after = seg.split("Name:", 1)
                        type_part = before.strip()
                        name_part = after.strip()

                    drive_info["type"] = type_part or None
                    if name_part:
                        drive_info["path"] = name_part

                j += 1

            drives.append(drive_info)
            drive_index += 1
            i = j
        else:
            i += 1

    return drives


def poll_for_drives(interval: int = 5):
    """
    Poll macOS optical drives via `drutil status` and sync with DriveTracker.

    Behaviors:
      - Track logical drives with stable ids: "macos-0", "macos-1", ...
      - Update each drive's current OS path (/dev/diskX) if present.
      - Detect media insertion/removal and call disc detection on insert.
      - Cancel any running job if a drive disappears physically.
    """
    global _last_media_state

    logger.info("Starting macOS drive polling loop")

    while True:
        status = _run_drutil_status()
        if not status:
            time.sleep(interval)
            continue

        parsed = _parse_drutil_status(status)

        # Logical drive ids that currently exist according to drutil
        current_ids: Set[str] = {d["id"] for d in parsed}

        # Drives we already track that belong to macOS
        tracked_ids: Set[str] = {
            d.id for d in drive_tracker.get_all_drives()
            if str(d.id).startswith("macos-")
        }

        # Add / update drives
        for info in parsed:
            drive_id = info["id"]
            model = info.get("model") or "Unknown"
            path = info.get("path")      # may be None when no media is inserted
            type_str = info.get("type")

            caps = _infer_capabilities(model, type_str)

            drive = drive_tracker.register_drive(
                drive_id=drive_id,
                path=path,
                model=model,
                capability=caps,
            )

            has_media = path is not None
            before = _last_media_state.get(drive_id, False)
            _last_media_state[drive_id] = has_media

            if path:
                logger.debug(
                    f"macOS drive {drive_id}: path={path}, model={model}, "
                    f"type={type_str}, caps={caps}"
                )
            else:
                logger.debug(
                    f"macOS drive {drive_id}: no media, model={model}, caps={caps}"
                )

            # Media inserted
            if has_media and not before:
                logger.info(f"Disc inserted in {drive_id} ({path})")
                # kick off disc classification + backend notification
                detect_and_notify(drive_id, path)

            # Media removed (drive still present, but no Name: /dev/diskX)
            if not has_media and before:
                logger.info(f"Disc removed/ejected from {drive_id}")
                try:
                    # Use drive_id or last known path; using drive_id is more stable
                    post_api("/api/drives/remove", {"drive": drive_id})
                except Exception as e:
                    logger.warning(f"Could not notify backend of macOS remove: {e}")

        # Handle physically unplugged drives (USB enclosure etc.)
        for missing_id in tracked_ids - current_ids:
            d = drive_tracker.get_drive(missing_id)
            if not d:
                continue

            logger.info(f"Physical macOS drive removed: {missing_id}")

            if d.job_id:
                job = job_tracker.get_job(d.job_id)
                if job and getattr(job, "runner", None):
                    job.runner.cancel()
                    logger.info(
                        f"Cancelled job {d.job_id} due to unplug of drive {missing_id}"
                    )
                else:
                    logger.warning(
                        f"Could not find runner for job {d.job_id} during unplug of {missing_id}"
                    )

            drive_tracker.unregister_drive(missing_id)
            _last_media_state.pop(missing_id, None)

        time.sleep(interval)
