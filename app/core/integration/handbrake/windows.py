# app/core/integration/handbrake/windows.py
from pathlib import Path
from typing import List, Optional, Union

from .common import build_base_args, detect_hw_encoders

# Default HandBrakeCLI path on Windows.
# Change this if your HandBrakeCLI.exe lives somewhere else.
HANDBRAKE_CLI = r"C:\Program Files\HandBrake\HandBrakeCLI.exe"


def _hb_cli_prefix() -> List[str]:
    """Return the preferred HandBrakeCLI invocation."""
    try:
        if Path(HANDBRAKE_CLI).exists():
            return [HANDBRAKE_CLI]
    except Exception:
        pass
    return ["HandBrakeCLI"]


def get_available_hw_encoders():
    """
    Query HandBrakeCLI -h and try to detect available hardware encoders.

    This is a best-effort helper for the UI; if HandBrakeCLI is missing
    or errors, we just report all vendors as unavailable.
    """
    return detect_hw_encoders(_hb_cli_prefix())


def build_handbrake_cmd(
    mkv_file,
    output_path,
    preset_path: Optional[Union[Path, str]],
    preset_name: str,
) -> List[str]:
    """
    Build the HandBrakeCLI command for Windows.

    Parameters:
        mkv_file:    input MKV path; can be a Path or a string
                     (including the literal 'INPUT_PLACEHOLDER').
        output_path: output file path; Path or string
                     (including 'OUTPUT_PLACEHOLDER').
        preset_path: optional path to a preset file; may be None/empty.
        preset_name: name of the preset (e.g. 'Fast 1080p30').

    Returns:
        A list of command tokens, for example:
            [
              'C:\\Program Files\\HandBrake\\HandBrakeCLI.exe',
              '--preset-import-file', 'C:\\path\\preset.json',
              '-Z', 'Fast 1080p30',
              '-i', 'INPUT_PLACEHOLDER',
              '-o', 'OUTPUT_PLACEHOLDER',
            ]
    """
    return _hb_cli_prefix() + build_base_args(
        mkv_file=mkv_file,
        output_path=output_path,
        preset_path=preset_path,
        preset_name=preset_name,
    )
