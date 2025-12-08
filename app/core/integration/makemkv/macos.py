from pathlib import Path
from typing import List
import os
import shutil
import re


def _candidate_paths() -> List[str]:
    """
    Likely locations of makemkvcon on macOS.

    - Homebrew:   /usr/local/bin/makemkvcon, /opt/homebrew/bin/makemkvcon
    - App bundle: /Applications/MakeMKV.app/Contents/MacOS/makemkvcon
    - PATH name:  'makemkvcon'
    """
    return [
        "/usr/local/bin/makemkvcon",
        "/opt/homebrew/bin/makemkvcon",
        "/Applications/MakeMKV.app/Contents/MacOS/makemkvcon",
        "makemkvcon",
    ]


def _find_makemkv_binary() -> str:
    """
    Try to find makemkvcon; fall back to plain 'makemkvcon' if nothing obvious.
    """
    for p in _candidate_paths():
        # plain name -> let shutil.which decide
        if os.sep not in p and shutil.which(p):
            return p
        # absolute/relative path -> check executable bit
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return "makemkvcon"


def _normalise_drive_spec(drive_path: str) -> str:
    """
    Convert our internal drive identifier into something MakeMKV understands.

    On macOS we use logical IDs like 'DRIVE0', 'DRIVE1' from drutil.

    Rules:
      - 'DRIVEn'     -> 'disc:n'
      - already 'disc:...' or 'dev:...' -> passed through
      - '/dev/...'   -> 'dev:/dev/...' (if you ever use raw device)
      - anything else -> treated as device path 'dev:<drive_path>'
    """
    if not drive_path:
        return "disc:0"

    # Logical ID from mac drive detector: DRIVE0, DRIVE1, ...
    m = re.match(r"DRIVE(\d+)$", drive_path, re.IGNORECASE)
    if m:
        idx = int(m.group(1))
        return f"disc:{idx}"

    # Already in makemkvcon format
    if drive_path.startswith("disc:") or drive_path.startswith("dev:"):
        return drive_path

    # Raw device path
    if drive_path.startswith("/dev/"):
        return f"dev:{drive_path}"

    # Fallback: assume it's some device path makemkv understands
    return f"dev:{drive_path}"


def build_makemkv_cmd(drive_path: str, temp_dir: Path, progress_path: Path) -> List[str]:
    """
    Build the MakeMKV command line for macOS.

    drive_path will usually be 'DRIVE0' / 'DRIVE1' (logical IDs) on macOS,
    which we map to 'disc:0' / 'disc:1' for makemkvcon.
    """
    makemkv_bin = _find_makemkv_binary()
    source_spec = _normalise_drive_spec(drive_path)

    return [
        makemkv_bin,
        "--robot",
        "mkv",
        source_spec,
        "all",
        str(temp_dir),
        "--noscan",
        "--decrypt",
        "--minlength=1",
        f"--progress={progress_path}",
    ]
