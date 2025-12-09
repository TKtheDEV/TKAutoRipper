from typing import List
from pathlib import Path
import shlex
import logging


def _ps_quote(s: str) -> str:
    """
    PowerShell single-quoted string literal.
    Backslashes are fine; single quotes are doubled.
    """
    s = str(s)
    return "'" + s.replace("'", "''") + "'"


def _filtered_additional_opts(additional_options: str) -> List[str]:
    """
    Parse additional options while stripping abcde-specific flags (e.g. -x)
    that would make freaccmd bail out. Quotes/backslashes are preserved.
    """
    if not additional_options:
        return []

    try:
        tokens = shlex.split(additional_options, posix=False)
    except ValueError:
        tokens = additional_options.split()

    drop = {"-x"}  # abcde eject flag; freaccmd doesn't understand it
    return [t for t in tokens if t not in drop]


def run_freac(
    drive_path: str,
    output_format: str,
    config_path: str,
    additional_options: str,
    output_dir: Path | str,
) -> List[str]:
    """
    Builds a freaccmd command line equivalent to abcde's behavior.

    :param drive_path: Windows CD device (e.g. "D:")
    :param output_format: "flac", "mp3", etc.
    :param config_path: (ignored unless you want custom freac XML configs)
    :param additional_options: extra CLI flags
    :param output_dir: where to write the ripped tracks
    """

    encoder_map = {
        "flac": "flac",
        "mp3": "lame",
        "opus": "opus",
        "aac": "fdkaac",
    }

    encoder = encoder_map.get(output_format.lower(), output_format)

    additional_args = _filtered_additional_opts(additional_options)

    # Normalize drive and output paths
    drive_arg = drive_path.rstrip("\\") + "\\"
    out_dir = Path(output_dir)

    freac_bin = r"C:\Program Files\freac\freaccmd.exe"

    # Command shape:
    # freaccmd.exe -e flac --cddb -cd E: --eject -p "<artist>\<album>\<track>. <title>" -d C:\out E:\*
    cmd = [
        freac_bin,
        "-e",
        encoder,
        "--cddb",
        "-cd",
        drive_arg.rstrip("\\"),
        "--eject",
        "-p",
        r"<artist>\<album>\<track>. <title>",
        "-d",
        str(out_dir),
        drive_arg + "*",
        *additional_args,
    ]

    logging.info("freaccmd command: %s", " ".join(cmd))
    return cmd
