from pathlib import Path
from typing import List
def build_iso_dump_cmd(device: str, output_path: Path) -> List[str]:
    return [
        "sh",
        "-c",
        f"pv -pter {device} | dd bs=2048 of={output_path} status=progress"
    ]
