# app/core/integration/handbrake/common.py
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Union


_VENDOR_LABELS = {
    "nvenc": "NVIDIA NVENC",
    "qsv": "Intel QSV",
    "vce": "AMD VCE",
    "vt": "Apple VT",
}


def empty_vendor_map() -> Dict:
    """Return a fresh vendor availability map."""
    return {
        "vendors": {
            key: {"label": label, "available": False, "codecs": []}
            for key, label in _VENDOR_LABELS.items()
        }
    }


def parse_hw_encoders_from_help(lines: List[str]) -> Dict:
    """
    Given HandBrakeCLI -h output lines, build the vendor availability map.
    """
    vendors = empty_vendor_map()
    for prefix in _VENDOR_LABELS.keys():
        target = f"{prefix}_"
        # Match tokens that start with e.g. "vt_" to avoid catching "svt_*" etc.
        codecs = sorted(
            {
                token[len(target) :]
                for line in lines
                for token in line.strip().split()
                if token.startswith(target)
            }
        )
        vendors["vendors"][prefix]["available"] = bool(codecs)
        vendors["vendors"][prefix]["codecs"] = codecs
    return vendors


def detect_hw_encoders(cli_prefix: List[str]) -> Dict:
    """
    Run HandBrakeCLI -h with the given prefix (e.g., ['HandBrakeCLI'] or flatpak)
    and return the parsed vendor map. Falls back to empty map on any error.
    """
    try:
        result = subprocess.run(
            cli_prefix + ["-h"], capture_output=True, text=True, check=True
        )
        return parse_hw_encoders_from_help(result.stdout.splitlines())
    except Exception:
        return empty_vendor_map()


def build_base_args(
    mkv_file: Union[Path, str],
    output_path: Union[Path, str],
    preset_path: Optional[Union[Path, str]],
    preset_name: str,
) -> List[str]:
    """
    Construct the common HandBrakeCLI arguments (without the binary prefix).
    """
    args: List[str] = []
    if preset_path:
        args.extend(["--preset-import-file", str(preset_path)])
    args.extend(
        [
            "-Z",
            preset_name,
            "-i",
            str(mkv_file),
            "-o",
            str(output_path),
        ]
    )
    return args
