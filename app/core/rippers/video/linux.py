# app/core/rippers/video/linux.py
"""
DVD / Blu-ray VIDEO ripper helper (Linux).

Steps:
  1. MakeMKV  →  creates *.mkv titles, releases drive   (weight ≈ 0.70)
  2. HandBrake loops over each MKV and transcodes       (weight ≈ 0.30)

All MKVs are processed so TV-series discs are handled correctly.
"""

from pathlib import Path
from typing import List, Tuple
import shlex

from app.core.configmanager import config
from app.core.integration.makemkv.linux import build_makemkv_cmd
from app.core.integration.handbrake.linux import build_handbrake_cmd
from app.core.job.job import Job


def rip_video_disc(job: Job, disc_type: str) -> List[Tuple[List[str], str, bool, float]]:
    """
    Returns step-tuples in the extended format:
        (command, description, release_drive, weight)
    """
    cfg = config.section(disc_type.upper())

    temp_dir: Path = job.temp_path
    progress_txt = temp_dir / "makemkv_progress.txt"

    # ── Step 1: MakeMKV ─────────────────────────────────────
    makemkv_cmd = build_makemkv_cmd(
        drive_path=job.drive,
        temp_dir=temp_dir,
        progress_path=progress_txt,
    )

    steps: List[Tuple[List[str], str, bool, float]] = [
        # release drive right after MakeMKV (weight ~70 %)
        (makemkv_cmd, f"Ripping {disc_type} with MakeMKV", True, 0.70)
    ]

    # ── Step 2: HandBrake for every MKV ─────────────────────
    if cfg.get("usehandbrake", True):
        preset_path = Path(cfg["handbrakepreset_path"]).expanduser()
        preset_name = cfg["handbrakepreset_name"]
        container   = cfg["handbrakeformat"]            # “mkv” by default
        use_flatpak = cfg.get("handbrakeflatpak", True)

        output_dir = job.output_path
        output_dir.mkdir(parents=True, exist_ok=True)

        # Build a template HandBrake CLI (as strings, not Path objects!)
        hb_template = build_handbrake_cmd(
            mkv_file="INPUT_PLACEHOLDER",
            output_path="OUTPUT_PLACEHOLDER",
            preset_path=preset_path,
            preset_name=preset_name,
            flatpak=use_flatpak,
        )

        # Path objects → str, then quote
        hb_template_str = " ".join(shlex.quote(str(tok)) for tok in hb_template)

        # Bash loop: transcode each *.mkv
        shell_script = (
            f'for SRC in *.mkv; do '
            f'OUT="{shlex.quote(str(output_dir))}/$(basename "${{SRC%.*}}").{container}"; '
            f'{hb_template_str.replace("INPUT_PLACEHOLDER", "$SRC").replace("OUTPUT_PLACEHOLDER", "$OUT")} ; '
            f'done'
        )

        steps.append( (["bash", "-c", shell_script],
                       f"Encoding {disc_type} titles with HandBrake",
                       False,
                       0.30) )

    return steps
