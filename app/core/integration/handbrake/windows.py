# app/core/integration/handbrake/windows.py

import subprocess
from pathlib import Path
from typing import List, Optional

# Default HandBrakeCLI path on Windows.
# Change this if your HandBrakeCLI.exe lives somewhere else.
HANDBRAKE_CLI = r"C:\Program Files\HandBrake\HandBrakeCLI.exe"


def _hb_binary() -> str:
    """Return the path/binary name for HandBrakeCLI."""
    return HANDBRAKE_CLI


def get_available_hw_encoders():
    """
    Query HandBrakeCLI -h and try to detect available hardware encoders.

    This is a best-effort helper for the UI; if HandBrakeCLI is missing
    or errors, we just report all vendors as unavailable.
    """
    try:
        cmd = ["HandBrakeCLI", "-h"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.splitlines()

        # Look for encoder names like nvenc_h265, qsv_h264, vce_h264, vt_h265, etc.
        all_encoders = [
            line.strip()
            for line in output
            if any(v in line for v in ["nvenc_", "qsv_", "vce_", "vt_"])
        ]

        def extract_codecs(enc_list, prefix: str):
            return sorted({e.replace(prefix, "") for e in enc_list if e.startswith(prefix)})

        encoders = {
            "nvenc": extract_codecs(all_encoders, "nvenc_"),
            "qsv": extract_codecs(all_encoders, "qsv_"),
            "vce": extract_codecs(all_encoders, "vce_"),
            "vt": extract_codecs(all_encoders, "vt_"),
        }

        return {
            "vendors": {
                "nvenc": {
                    "label": "NVIDIA NVENC",
                    "available": bool(encoders["nvenc"]),
                    "codecs": encoders["nvenc"],
                },
                "qsv": {
                    "label": "Intel QSV",
                    "available": bool(encoders["qsv"]),
                    "codecs": encoders["qsv"],
                },
                "vce": {
                    "label": "AMD VCE",
                    "available": bool(encoders["vce"]),
                    "codecs": encoders["vce"],
                },
                "vt": {
                    "label": "Apple VT",
                    "available": bool(encoders["vt"]),
                    "codecs": encoders["vt"],
                },
            }
        }

    except (subprocess.CalledProcessError, FileNotFoundError):
        # HandBrakeCLI not found or failed – report everything as unavailable
        return {
            "vendors": {
                "nvenc": {"label": "NVIDIA NVENC", "available": False, "codecs": []},
                "qsv": {"label": "Intel QSV", "available": False, "codecs": []},
                "vce": {"label": "AMD VCE", "available": False, "codecs": []},
                "vt": {"label": "Apple VT", "available": False, "codecs": []},
            }
        }


def build_handbrake_cmd(
    mkv_file,
    output_path,
    preset_path: Optional[str],
    preset_name: str,
    flatpak: bool = True,  # kept for signature compatibility; ignored on Windows
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
        flatpak:     ignored on Windows; present only to match Linux signature.

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
    cmd: List[str] = ["HandBrakeCLI"]   

    # Optional preset file
    if preset_path:
        cmd.extend(["--preset-import-file", str(preset_path)])

    # Choose preset
    cmd.extend(["-Z", preset_name])

    # Input / output
    cmd.extend([
        "-i", str(mkv_file),
        "-o", str(output_path),
    ])

    return cmd
