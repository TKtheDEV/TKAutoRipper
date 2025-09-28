from pathlib import Path
from typing import List
def build_zstd_cmd(input_path: Path, output_path: Path) -> List[str]:
    return [
        "zstd",
        str(input_path),
        "-o",
        str(output_path)
    ]
