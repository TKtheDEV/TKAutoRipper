# app/core/integration/abcde/macos.py
from typing import List
from shutil import which
from pathlib import Path


ABCDEFALLBACKS = [
    Path("/opt/homebrew/bin/abcde"),
    Path("/usr/local/bin/abcde"),
]


def _resolve_abcde() -> str:
    """Return an abcde executable path, falling back to common Homebrew locations."""
    for cand in ABCDEFALLBACKS:
        if cand.exists():
            return str(cand)
    return which("abcde") or "abcde"


def run_abcde(
    drive_path: str,
    output_format: str,
    config_path: str,
    additional_options: str
) -> List[str]:
    """
    Constructs the abcde command for ripping an audio CD on macOS.

    :param drive_path: The device path (e.g., /dev/disk4)
    :param output_format: Audio format like 'flac', 'mp3', etc.
    :param config_path: Path to abcde configuration file
    :param additional_options: Additional CLI options as a string
    :return: List of strings representing the command to run
    """
    additional_args = additional_options.split() if additional_options else []

    command = [
        _resolve_abcde(),
        "-d", drive_path,
        "-o", output_format,
        "-c", config_path,
        "-N",
        *additional_args
    ]
    return command
