# app/core/integration/zstd/linux.py
from pathlib import Path
from typing import List

def build_zstd_cmd(input_path: Path, output_path: Path) -> List[str]:
    return [
        "zstd",
        "-v",        # verbose → progress %
        "-T0",       # all cores
        str(input_path),
        "-o", str(output_path),
    ]
