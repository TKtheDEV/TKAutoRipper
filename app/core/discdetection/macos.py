# app/core/discdetection/macos.py

import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple
import re

from ..api_helpers import post_api
from ..job.job import sanitize_folder


def monitor_cdrom():
    return


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout


def _parse_size_bytes(size_str: str) -> int:
    """
    Parse something like '707.4 MB', '3.1 GB', '30.6 MB' into bytes.
    """
    size_str = size_str.strip()
    if not size_str:
        return 0

    parts = size_str.split()
    if len(parts) < 2:
        return 0

    try:
        value = float(parts[0])
    except ValueError:
        return 0

    unit = parts[1].upper()
    factor = 1
    if unit.startswith("KB"):
        factor = 1024
    elif unit.startswith("MB"):
        factor = 1024**2
    elif unit.startswith("GB"):
        factor = 1024**3
    elif unit.startswith("TB"):
        factor = 1024**4

    return int(value * factor)


def _get_diskutil_list_info(dev: str) -> Tuple[int, bool, bool, bool, Optional[str]]:
    """
    Inspect `diskutil list dev` to get:
      - total_size_bytes
      - has_audio (Audio CD or CD_DA present)
      - has_cd_rom (CD_ROM_Mode_1 present)
      - has_cd_da (explicit CD_DA track)
      - first_partition_name (NAME column from diskutil list)
    """
    out = _run(["diskutil", "list", dev])
    total_size_bytes = 0
    has_audio = False
    has_cd_rom = False
    has_cd_da = False
    first_partition_name: Optional[str] = None

    # Example partition line:
    #   1:              CD_ROM_Mode_1 CD323A1                 26.7 MB    disk4s0
    part_re = re.compile(r"^\s*\d+:\s+[^\s]+\s+(.*?)\s+\d")

    for line in out.splitlines():
        l = line.strip()

        # Size of whole disc: look for the line with '*XXX MB/GB'
        if "*" in l:
            # e.g. "... Audio CD               *707.4 MB   disk4"
            star_idx = l.find("*")
            after = l[star_idx + 1 :]
            # after ~ '707.4 MB   disk4'
            size_token = after.split("  ")[0]
            total_size_bytes = _parse_size_bytes(size_token)

        if "Audio CD" in l:
            has_audio = True
        if "CD_DA" in l:
            has_audio = True
            has_cd_da = True
        if "CD_ROM_Mode_1" in l:
            has_cd_rom = True

        if first_partition_name is None:
            m = part_re.match(line)
            if m:
                name_candidate = m.group(1).strip()
                if name_candidate:
                    first_partition_name = name_candidate

    return total_size_bytes, has_audio, has_cd_rom, has_cd_da, first_partition_name


def _parse_diskutil_info(dev: str) -> Tuple[Optional[str], str, Optional[str], Optional[str], Optional[str]]:
    """
    Use `diskutil info` to find mount point, volume name, optical media type and FS personality.
    """
    out = _run(["diskutil", "info", dev])
    mount_point: Optional[str] = None
    volume_name: Optional[str] = None
    optical_media_type: Optional[str] = None
    fs_personality: Optional[str] = None
    media_name: Optional[str] = None

    for raw in out.splitlines():
        line = raw.strip()
        if line.startswith("Mount Point:"):
            mp = line.split(":", 1)[1].strip()
            if mp and mp.lower() != "not mounted":
                mount_point = mp
        elif line.startswith("Volume Name:"):
            vn = line.split(":", 1)[1].strip()
            if vn:
                volume_name = vn
        elif line.startswith("Optical Media Type:"):
            om = line.split(":", 1)[1].strip()
            if om:
                optical_media_type = om
        elif line.startswith("File System Personality:"):
            fs = line.split(":", 1)[1].strip()
            if fs:
                fs_personality = fs
        elif line.startswith("Device / Media Name:"):
            mn = line.split(":", 1)[1].strip()
            if mn:
                media_name = mn

    disc_label = volume_name or "unknown"
    return mount_point, disc_label, optical_media_type, fs_personality, media_name


def _has_folder(mount_point: Optional[str], folder: str) -> bool:
    if not mount_point:
        return False
    return Path(mount_point, folder).exists()


def _select_disc_label(
    drive_id: str,
    dev: str,
    raw_label: Optional[str],
    media_name: Optional[str],
    partition_name: Optional[str],
    mount_point: Optional[str],
) -> str:
    """
    Choose a reasonable, filesystem-safe label.
    """
    def usable(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        v = val.strip()
        if not v:
            return None
        if v.lower().startswith("not applicable"):
            return None
        return v

    candidate = usable(raw_label)

    if not candidate:
        candidate = usable(partition_name)

    if not candidate and mount_point:
        mp_name = Path(mount_point).name
        candidate = usable(mp_name)

    if not candidate:
        candidate = usable(media_name)

    if not candidate:
        candidate = Path(dev).name or drive_id or "DISC"

    cleaned = sanitize_folder(candidate or "DISC") or "DISC"
    return cleaned


def classify_disc(drive_id: str, dev: str) -> Tuple[str, str]:
    """
    dev: e.g. '/dev/disk4'
    Returns (disc_type, disc_label) where disc_type is one of:
      - cd_audio
      - cd_rom
      - dvd_video / dvd_rom
      - bluray_video / bluray_rom
      - unknown
    """
    size_bytes, has_audio, has_cd_rom, _, part_name = _get_diskutil_list_info(dev)
    mount_point, raw_label, optical_type, _, media_name = _parse_diskutil_info(dev)
    disc_label = _select_disc_label(drive_id, dev, raw_label, media_name, part_name, mount_point)

    optical_upper = (optical_type or "").upper()
    disc_type = "unknown"

    # 1) Pure audio CD (no filesystem, audio tracks)
    if has_audio and not has_cd_rom:
        disc_type = "cd_audio"
    else:
        if any(tok in optical_upper for tok in ("BD", "BLU")):
            disc_type = "bluray_video" if _has_folder(mount_point, "BDMV") else "bluray_rom"
        elif "DVD" in optical_upper:
            disc_type = "dvd_video" if _has_folder(mount_point, "VIDEO_TS") else "dvd_rom"
        elif "CD" in optical_upper:
            disc_type = "cd_rom"
        else:
            # Fallback to size heuristics
            if size_bytes >= 25 * 1024**3:
                disc_type = "bluray_video" if _has_folder(mount_point, "BDMV") else "bluray_rom"
            elif size_bytes >= 1 * 1024**3:
                disc_type = "dvd_video" if _has_folder(mount_point, "VIDEO_TS") else "dvd_rom"
            elif size_bytes > 0:
                disc_type = "cd_rom"
            elif has_audio:
                disc_type = "cd_audio"

    logging.info(f"{disc_type.upper()} detected in {dev}, label={disc_label}")
    return disc_type, disc_label


def detect_and_notify(drive_id: str, dev: str):
    """
    Called when macOS drive polling sees media present in /dev/diskX.
    drive_id: logical id like "macos-0"
    dev: OS device path like "/dev/disk4"
    """
    try:
        disc_type, disc_label = classify_disc(drive_id, dev)
        post_api("/api/drives/insert", {
            "drive": dev,
            "disc_type": disc_type,
            "disc_label": disc_label,
        })
    except Exception as e:
        logging.error(f"macOS detection or job creation failed for {drive_id} ({dev}): {e}")
