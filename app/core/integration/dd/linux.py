# app/core/integration/dd/linux.py
from pathlib import Path
from typing import List

def build_iso_dump_cmd(device: str, output_path: Path) -> List[str]:
    """
    Use plain dd, stream progress to STDOUT (so the runner can parse it),
    and fsync writes so partial files are durable on cancel.
    """
    # We force progress on stdout by redirecting 2>&1; runner watches stdout.
    sh = f'dd if={device} of="{output_path}" bs=2048 status=progress conv=fsync 2>&1'
    return ["bash", "-lc", sh]
