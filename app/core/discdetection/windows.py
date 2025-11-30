# app/core/discdetection/windows.py

import os
import time
import logging
from pathlib import Path
from ctypes import (
    windll,
    wintypes,
    byref,
    create_unicode_buffer,
    c_ulonglong,
)

from ..api_helpers import post_api
from ..configmanager import config  # kept for parity, even if unused


# WinAPI constants
DRIVE_CDROM = 5
ERROR_NOT_READY = 21  # "Device not ready" – usually means no disc present


# --- Helper: enumerate optical drives --------------------------------------


def _iter_cdrom_drive_letters():
    """
    Return a set of drive letters (like 'D:') that are CD/DVD/BD drives
    according to GetDriveTypeW.
    """
    drive_bits = windll.kernel32.GetLogicalDrives()
    letters = set()

    for i in range(26):
        if drive_bits & (1 << i):
            letter = chr(ord("A") + i)
            root_path = f"{letter}:\\"

            drive_type = windll.kernel32.GetDriveTypeW(
                wintypes.LPCWSTR(root_path)
            )
            if drive_type == DRIVE_CDROM:
                letters.add(f"{letter}:")

    return letters


# --- Helper: get disc info for a drive -------------------------------------


def _get_disc_info(drive: str):
    """
    Try to read information about a disc in the given optical drive.

    drive: 'D:' (no trailing backslash).

    Returns:
        dict with keys:
            - fs_type (str, lowercase)
            - disc_size (int, bytes)
            - disc_label (str)
            - mount_point (str, e.g. 'D:\\')
        or None if no disc is present / not ready.
    """
    root = drive.rstrip("\\/") + "\\"

    kernel32 = windll.kernel32

    # Get volume information (label + filesystem type)
    volume_name_buf = create_unicode_buffer(261)
    fs_name_buf = create_unicode_buffer(261)
    serial_num = wintypes.DWORD()
    max_comp_len = wintypes.DWORD()
    fs_flags = wintypes.DWORD()

    res = kernel32.GetVolumeInformationW(
        wintypes.LPCWSTR(root),
        volume_name_buf,
        len(volume_name_buf),
        byref(serial_num),
        byref(max_comp_len),
        byref(fs_flags),
        fs_name_buf,
        len(fs_name_buf),
    )

    if not res:
        # If drive is not ready, treat as "no disc present"
        err = kernel32.GetLastError()
        if err == ERROR_NOT_READY:
            return None
        # Other errors – also treat as no disc, but log if needed
        logging.debug(f"GetVolumeInformationW failed for {drive}, error {err}")
        return None

    disc_label = volume_name_buf.value or "unknown"
    fs_type = fs_name_buf.value.lower()  # e.g. "udf", "cdfs", "iso9660"

    # Get disc size (total number of bytes)
    total_bytes = c_ulonglong(0)
    free_bytes = c_ulonglong(0)
    avail_bytes = c_ulonglong(0)

    res = kernel32.GetDiskFreeSpaceExW(
        wintypes.LPCWSTR(root),
        byref(avail_bytes),
        byref(total_bytes),
        byref(free_bytes),
    )
    if not res:
        logging.debug(f"GetDiskFreeSpaceExW failed for {drive}")
        disc_size = 0
    else:
        disc_size = int(total_bytes.value)

    return {
        "fs_type": fs_type,
        "disc_size": disc_size,
        "disc_label": disc_label,
        "mount_point": root,
    }


def _classify_disc(fs_type: str, disc_size: int, mount_point: str) -> str:
    """
    Classify disc type, mirroring the Linux logic as closely as possible.
    """
    def has_folder(folder: str) -> bool:
        return Path(mount_point, folder).exists() if mount_point else False

    # Windows optical filesystems are typically "udf" or "cdfs" (for ISO9660),
    # so treat "cdfs" like "iso9660".
    if fs_type in ["udf", "iso9660", "cdfs"]:
        # Sizes use same thresholds as Linux version
        one_gib = 1 * 1024**3
        twentyfive_gib = 25 * 1024**3

        if disc_size < one_gib:
            disc_type = "cd_rom"
        elif one_gib <= disc_size <= twentyfive_gib:
            disc_type = "dvd_video" if has_folder("VIDEO_TS") else "dvd_rom"
        elif disc_size > twentyfive_gib:
            disc_type = "bluray_video" if has_folder("BDMV") else "bluray_rom"
        else:
            disc_type = "unknown"

    elif fs_type == "":
        # No filesystem reported – likely an audio CD
        disc_type = "cd_audio"
    else:
        disc_type = "unknown"

    return disc_type


# --- Main monitor loop ------------------------------------------------------


def monitor_cdrom(poll_interval: int = 2):
    """
    Monitors for disc insertions and removals on Windows and interacts with
    backend API accordingly.

    This is a polling-based approximation of the Linux udev-based implementation.
    """
    logging.info("Starting Windows CDROM monitor")

    # Track whether each drive currently has a disc present
    disc_present = {}  # drive -> bool

    while True:
        try:
            current_drives = _iter_cdrom_drive_letters()

            # Check for drives that disappeared (USB unplugged, etc.)
            for drive in list(disc_present.keys()):
                if drive not in current_drives:
                    # If a disc was in it, treat as removal/eject
                    if disc_present[drive]:
                        logging.info(f"📤 Drive {drive} disappeared, treating as eject")
                        try:
                            post_api("/api/drives/remove", {"drive": drive})
                        except Exception as e:
                            logging.warning(
                                f"⚠️ Could not notify backend of drive removal {drive}: {e}"
                            )
                    disc_present.pop(drive, None)

            # Check each current drive for disc state
            for drive in current_drives:
                info = _get_disc_info(drive)
                present = info is not None
                was_present = disc_present.get(drive, False)

                # Disc inserted
                if present and not was_present:
                    fs_type = info["fs_type"]
                    disc_size = info["disc_size"]
                    disc_label = info["disc_label"]
                    mount_point = info["mount_point"]

                    disc_type = _classify_disc(fs_type, disc_size, mount_point)

                    logging.info(f"📥 Disc inserted in {drive}")
                    logging.info(f"📀 {disc_type.upper()} detected in {drive}")

                    try:
                        post_api(
                            "/api/drives/insert",
                            {
                                "drive": drive,
                                "disc_type": disc_type,
                                "disc_label": disc_label,
                            },
                        )
                    except Exception as e:
                        logging.error(
                            f"❌ Could not notify backend of disc insert in {drive}: {e}"
                        )

                # Disc removed / ejected
                elif not present and was_present:
                    logging.info(f"📤 Disc removed/ejected from {drive}")
                    try:
                        post_api("/api/drives/remove", {"drive": drive})
                    except Exception as e:
                        logging.warning(
                            f"⚠️ Could not notify backend of eject from {drive}: {e}"
                        )

                disc_present[drive] = present

        except Exception as loop_err:
            logging.error(f"❌ Error in Windows CDROM monitor loop: {loop_err}")

        time.sleep(poll_interval)
