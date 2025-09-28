from typing import List
from pathlib import Path
def build_makemkv_cmd(drive_path: str, temp_dir: Path, progress_path: Path) -> List[str]:
    return [
        "makemkvcon", "--robot", "mkv", f"dev:{drive_path}", "all",
        str(temp_dir), "--noscan", "--decrypt", "--minlength=1",
        f"--progress={progress_path}"
    ]
