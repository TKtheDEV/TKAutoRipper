# app/core/discdetection/linux.py
import subprocess
import os
import time
import logging
from pathlib import Path

from ..api_helpers import post_api
from ..configmanager import config


def monitor_cdrom():
    """Monitors for disc insertions and removals and interacts with backend API accordingly."""

    process = subprocess.Popen(["udevadm", "monitor", "--property"],
                               stdout=subprocess.PIPE, text=True)
    drive = None

    for line in iter(process.stdout.readline, ""):
        line = line.strip()

        if line == "":
            drive = None
            continue

        if line.startswith("DEVNAME="):
            drive = line.split("=")[1]

        if "DISK_EJECT_REQUEST=1" in line and drive:
            logging.info(f"Eject button pressed on {drive}")
            try:
                post_api("/api/drives/remove", {"drive": drive})
            except Exception as e:
                logging.warning(f"Could not notify backend of eject: {e}")

        # Disc removed / media no longer present
        elif "ID_CDROM_MEDIA=0" in line and drive:
            logging.info(f"Disc removed/ejected from {drive}")
            try:
                post_api("/api/drives/remove", {"drive": drive})
            except Exception as e:
                logging.warning(f"Could not notify backend of remove: {e}")

        # Handle disc insertion
        elif "ID_CDROM_MEDIA=1" in line and drive:
            logging.info(f"Disc inserted in {drive}")
            time.sleep(5)  # debounce
            udev_output = subprocess.check_output(
                ["udevadm", "info", "--query=property", f"--name={drive}"],
                text=True
            )
            if "ID_CDROM_MEDIA=1" in udev_output:

                try:
                    fs_type = subprocess.run(
                        ["blkid", "-o", "value", "-s", "TYPE", drive],
                        capture_output=True, text=True
                    ).stdout.strip().lower()

                    size_out = subprocess.run(
                        ["blockdev", "--getsize64", drive],
                        capture_output=True, text=True
                    ).stdout.strip()
                    disc_size = int(size_out) if size_out.isdigit() else 0

                    label_out = subprocess.run(
                        ["blkid", "-o", "value", "-s", "LABEL", drive],
                        capture_output=True, text=True
                    ).stdout.strip()
                    disc_label = label_out or "unknown"

                    # Try to find mount point using lsblk
                    mount_point = subprocess.run(
                        ["lsblk", "-no", "MOUNTPOINT", drive],
                        capture_output=True, text=True
                    ).stdout.strip()

                    def has_folder(folder: str) -> bool:
                        return Path(mount_point, folder).exists() if mount_point else False

                    if fs_type in ["udf", "iso9660"]:
                        if disc_size < 1 * 1024**3:
                            disc_type = "cd_rom"
                        elif 1 * 1024**3 <= disc_size <= 25 * 1024**3:
                            disc_type = "dvd_video" if has_folder("VIDEO_TS") else "dvd_rom"
                        elif disc_size > 25 * 1024**3:
                            disc_type = "bluray_video" if has_folder("BDMV") else "bluray_rom"
                        else:
                            disc_type = "unknown"
                    elif fs_type == "":
                        disc_type = "cd_audio"
                    else:
                        disc_type = "unknown"

                    logging.info(f"{disc_type.upper()} detected in {drive}")

                    post_api("/api/drives/insert", {
                        "drive": drive,
                        "disc_type": disc_type,
                        "disc_label": disc_label
                    })

                except Exception as e:
                    logging.error(f"Detection or job creation failed: {e}")
