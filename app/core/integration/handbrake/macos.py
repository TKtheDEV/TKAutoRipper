# app/core/integration/handbrake/macos.py
from pathlib import Path
from typing import List, Optional, Union

from .common import build_base_args, detect_hw_encoders


def get_available_hw_encoders():
    return detect_hw_encoders(["HandBrakeCLI"])


def build_handbrake_cmd(
    mkv_file: Path,
    output_path: Path,
    preset_path: Optional[Union[Path, str]],
    preset_name: str
) -> List[str]:
    return ["HandBrakeCLI", *build_base_args(
        mkv_file=mkv_file,
        output_path=output_path,
        preset_path=preset_path,
        preset_name=preset_name,
    )]
