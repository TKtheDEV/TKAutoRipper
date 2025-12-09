# app/core/discdetection/macos.py

import subprocess
import time
import logging
import re

from ..api_helpers import post_api
from ..configmanager import config  # not used yet, kept for structure


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
    Return a list of optical drive indices using `drutil list`,
    with a fallback to [0] if list is empty but `drutil info` works.
    """
    out = _safe_run(["drutil", "list"])
    indices: list[int] = []

    for line in out.splitlines():
        m = re.match(r"\s*(\d+):\s+(.*)$", line.strip())
        if not m:
            continue
        idx = int(m.group(1))
        indices.append(idx)

    if not indices:
        info_out = _safe_run(["drutil", "info"])
        if info_out.strip():
            indices = [0]

    return indices


def _drutil_status_type(index: int) -> str | None:
    """
    Run `drutil status -drive <index>` (or fallback `drutil status`)
    and return the 'Type:' string, e.g.:

        "No Media Inserted"
        "DVD-ROM"
        "CD-DA"
        "BD-RE"
    """
    if index == 0:
        out = _safe_run(["drutil", "status"])
        if not out.strip():
            out = _safe_run(["drutil", "status", "-drive", "0"])
    else:
        out = _safe_run(["drutil", "status", "-drive", str(index)])

    if not out:
        return None

    for raw_line in out.splitlines():
        line = raw_line.strip()
        if line.startswith("Type:"):
            return line.split(":", 1)[1].strip()
    return None


def _classify_disc_from_type(type_str: str) -> str:
    """
    Rough classification from `drutil status` Type line.

    This is not as detailed as the Linux fs/size logic, but it's enough to
    pick the right ripper:

      - contains 'cd-da' or 'audio'     -> cd_audio
      - contains 'bd' or 'blu-ray'      -> bluray_video
      - contains 'dvd'                  -> dvd_video
      - contains 'cd'                   -> cd_rom
      - else                            -> other_disc
    """
    t = type_str.lower()

    if "no media" in t:
        return "unknown"

    if "cd-da" in t or "audio" in t:
        return "cd_audio"
    if "bd" in t or "blu-ray" in t or "bluray" in t:
        return "bluray_video"
    if "dvd" in t:
        return "dvd_video"
    if "cd" in t:
        return "cd_rom"

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
    poll_interval = 3

    while True:
        indices = _list_optical_drives()
        current_ids = {f"DRIVE{idx}" for idx in indices}

        # If a drive disappeared, treat it like the disc was removed
        for drive_id in list(known_media.keys()):
            if drive_id not in current_ids:
                if known_media.get(drive_id, False):
                    logging.info(f"Drive disappeared, assuming disc removed: {drive_id}")
                    try:
                        post_api("/api/drives/remove", {"drive": drive_id})
                    except Exception as e:
                        logging.warning(
                            f"Could not notify backend of remove for {drive_id}: {e}"
                        )
                known_media.pop(drive_id, None)

        for idx in indices:
            drive_id = f"DRIVE{idx}"
            type_str = _drutil_status_type(idx)
            has_media = bool(type_str and "no media" not in type_str.lower())
            prev = known_media.get(drive_id, False)

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

                disc_type = _classify_disc_from_type(type_str or "")
                disc_label = "unknown"

                logging.info(f"{disc_type.upper()} detected in {drive_id}")

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

        time.sleep(poll_interval)
