# app/core/integration/makemkv/windows.py
from typing import List
from pathlib import Path

# Default MakeMKV console path on Windows
# Adjust this if you installed MakeMKV somewhere else.
MAKEMKV_EXE = r"C:\Program Files (x86)\MakeMKV\makemkvcon64.exe"


def build_makemkv_cmd(drive_path: str, temp_dir: Path, progress_path: Path) -> List[str]:
    """
    Build the MakeMKV command for Windows.

    - drive_path: like "E:" (we call MakeMKV with dev:E:)
    - temp_dir:   Path where MakeMKV should write the MKV files
    - progress_path: file where MakeMKV writes progress info
    """
    return [
        MAKEMKV_EXE,
        "--robot",
        "mkv",
        f"dev:{drive_path}",   # e.g. dev:E:
        "all",
        str(temp_dir),
        "--noscan",
        "--decrypt",
        "--minlength=1",
        f"--progress={progress_path}",
    ]
