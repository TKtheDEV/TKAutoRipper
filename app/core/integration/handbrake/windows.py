from app.core.configmanager import config
import subprocess
from pathlib import Path
from typing import List


def get_available_hw_encoders():
    try:
        cmd = ["HandBrakeCLI", "-h"]

        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        output = result.stdout.splitlines()

        all_encoders = [line.strip() for line in output if any(v in line for v in ["nvenc_", "qsv_", "vce_"])]

        def extract_codecs(enc_list, prefix):
            return sorted({e.replace(prefix, "") for e in enc_list if e.startswith(prefix)})

        encoders = {
            "nvenc": extract_codecs(all_encoders, "nvenc_"),
            "qsv": extract_codecs(all_encoders, "qsv_"),
            "vce": extract_codecs(all_encoders, "vce_")
        }

        return {
            "vendors": {
                "nvenc": {"label": "NVIDIA NVENC", "available": bool(encoders["nvenc"]), "codecs": encoders["nvenc"]},
                "qsv": {"label": "Intel QSV", "available": bool(encoders["qsv"]), "codecs": encoders["qsv"]},
                "vce": {"label": "AMD VCE", "available": bool(encoders["vce"]), "codecs": encoders["vce"]}
            }
        }

    except (subprocess.CalledProcessError, FileNotFoundError):
        return {
            "vendors": {
                "nvenc": {"label": "NVIDIA NVENC", "available": False, "codecs": []},
                "qsv": {"label": "Intel QSV", "available": False, "codecs": []},
                "vce": {"label": "AMD VCE", "available": False, "codecs": []}
            }
        }


def build_handbrake_cmd(
    mkv_file: Path,
    output_path: Path,
    preset_path: Path,
    preset_name: str,
    flatpak: bool = True
) -> List[str]:

    base_cmd = [
        "--preset-import-file", preset_path,
        "-Z", preset_name,
        "-i", str(mkv_file),
        "-o", str(output_path)
    ]

    return ["HandBrakeCLI", *base_cmd]
