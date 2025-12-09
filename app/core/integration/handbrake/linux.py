# app/core/integration/handbrake/linux.py
import subprocess
from pathlib import Path
from typing import List, Optional, Union

from .common import build_base_args, detect_hw_encoders

HB_FLATPAK_CMD = ["flatpak", "run", "--command=HandBrakeCLI", "fr.handbrake.ghb"]
HB_NATIVE_CMD = ["HandBrakeCLI"]


def _flatpak_available() -> bool:
    try:
        subprocess.run(
            ["flatpak", "info", "fr.handbrake.ghb"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


def _hb_cli_prefix() -> List[str]:
    """Prefer Flatpak if installed; otherwise use native CLI."""
    return HB_FLATPAK_CMD if _flatpak_available() else HB_NATIVE_CMD


def get_available_hw_encoders():
    return detect_hw_encoders(_hb_cli_prefix())


def build_handbrake_cmd(
    mkv_file: Path,
    output_path: Path,
    preset_path: Optional[Union[Path, str]],
    preset_name: str,
) -> List[str]:
    """Build a HandBrakeCLI command, using Flatpak if available."""
    return _hb_cli_prefix() + build_base_args(
        mkv_file=mkv_file,
        output_path=output_path,
        preset_path=preset_path,
        preset_name=preset_name,
    )
