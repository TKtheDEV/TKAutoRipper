# app/core/integration/dd/macos.py
from pathlib import Path
from typing import List


def build_iso_dump_cmd(device: str, output_path: Path) -> List[str]:
    """
    Use plain dd, stream progress to STDOUT (so the runner can parse it),
    and fsync writes so partial files are durable on cancel.

    `device` should be a real block device path, e.g. '/dev/rdisk2'.
    """
    # Quote both if+of; we force progress on stdout by redirecting 2>&1.
    sh = f'dd if="{device}" of="{output_path}" bs=2048 status=progress conv=fsync 2>&1'
    return ["bash", "-lc", sh]
