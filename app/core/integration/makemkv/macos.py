# app/core/integration/makemkv/macos.py

from pathlib import Path
from shutil import which
from typing import List

# Common install locations on macOS
MAKEMKV_CANDIDATES = [
    Path("/Applications/MakeMKV.app/Contents/MacOS/makemkvcon"),
    Path("/usr/local/bin/makemkvcon"),
    Path("/opt/homebrew/bin/makemkvcon"),
]


def _resolve_makemkv() -> str:
    """
    Return a makemkvcon path, preferring the bundled app location if present.
    """
    for candidate in MAKEMKV_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return which("makemkvcon") or "makemkvcon"


def build_makemkv_cmd(drive_path: str, temp_dir: Path, progress_path: Path) -> List[str]:
    """
    Build the MakeMKV command for macOS.

    - drive_path: like "/dev/disk4" (we call MakeMKV with dev:/dev/disk4)
    - temp_dir:   Path where MakeMKV should write the MKV files
    - progress_path: file where MakeMKV writes progress info
    """
    return [
        _resolve_makemkv(),
        "--robot",
        "mkv",
        f"dev:{drive_path}",
        "all",
        str(temp_dir),
        "--noscan",
        "--decrypt",
        "--minlength=1",
        f"--progress={progress_path}",
    ]
