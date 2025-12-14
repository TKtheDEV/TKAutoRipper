# app/core/integration/dd/linux.py
from pathlib import Path
from typing import List
import shlex

def build_iso_dump_cmd(device: str, output_path: Path) -> List[str]:
    """
    Use plain dd, stream progress to STDOUT (so the runner can parse it),
    and fsync writes so partial files are durable on cancel.
    """
    # We force progress on stdout by redirecting 2>&1; runner watches stdout.
    dev_q = shlex.quote(device)
    out_q = shlex.quote(str(output_path))
    sh = f"dd if={dev_q} of={out_q} bs=2048 status=progress conv=fsync 2>&1"
    return ["bash", "-lc", sh]
