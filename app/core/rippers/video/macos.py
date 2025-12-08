"""
DVD / Blu-ray VIDEO ripper helper (macOS).

Steps:
  1. MakeMKV  →  creates *.mkv titles in job.temp_path, releases drive   (weight ≈ 0.70)
  2a. HandBrake → encodes each MKV from temp into job.output_path          (weight ≈ 0.30)
  2b. Copy MKVs → copies MKVs from temp to job.output_path (if HB disabled)(weight ≈ 0.30)

All paths are absolute so it works no matter what cwd the runner uses.
"""

from pathlib import Path
from typing import List, Tuple
import shlex

from app.core.configmanager import config
from app.core.integration.makemkv.macos import build_makemkv_cmd
from app.core.integration.handbrake.macos import build_handbrake_cmd
from app.core.job.job import Job


def _cfg_get_bool(section, key: str, default: bool) -> bool:
    try:
        v = section.get(key, default)
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in {"1", "true", "yes", "on"}
        return bool(v)
    except Exception:
        return default


def rip_video_disc(job: Job, disc_type: str) -> List[Tuple[List[str], str, bool, float]]:
    """
    Return step tuples in the format:
        (command, description, release_drive, weight)
    """
    cfg = config.section((disc_type or "").upper())

    temp_dir: Path = job.temp_path
    output_dir: Path = job.output_path
    progress_txt = temp_dir / "makemkv_progress.txt"

    # ── Step 1: MakeMKV ──────────────────────────────────────
    # On macOS, job.drive will typically be "DRIVE0"/"DRIVE1" and
    # build_makemkv_cmd will map that to "disc:0"/"disc:1" internally.
    makemkv_cmd = build_makemkv_cmd(
        drive_path=job.drive,
        temp_dir=temp_dir,
        progress_path=progress_txt,
    )

    steps: List[Tuple[List[str], str, bool, float]] = [
        # release drive right after MakeMKV (weight ~70 %)
        (makemkv_cmd, f"Ripping {disc_type} with MakeMKV", True, 0.70)
    ]

    # ── Step 2: HandBrake or Copy ────────────────────────────
    use_hb = _cfg_get_bool(cfg, "usehandbrake", True)

    # Ensure output dir exists before the second step
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    if use_hb:
        # HandBrake encode each MKV
        preset_path = (
            Path(cfg.get("handbrakepreset_path", "")).expanduser()
            if cfg.get("handbrakepreset_path")
            else None
        )
        preset_name = cfg.get("handbrakepreset_name", "Fast 1080p30")
        container = cfg.get("handbrakeformat", "mkv").lstrip(".")

        hb_template = build_handbrake_cmd(
            mkv_file=Path("INPUT_PLACEHOLDER"),
            output_path=Path("OUTPUT_PLACEHOLDER"),
            preset_path=(preset_path if preset_path else None),
            preset_name=preset_name,
            flatpak=False,  # no Flatpak on macOS
        )
        hb_template_str = " ".join(shlex.quote(str(tok)) for tok in hb_template)

        tmp_abs = shlex.quote(str(temp_dir))
        out_abs = shlex.quote(str(output_dir))

        shell_script = f'''
            shopt -s nullglob
            mkdir -p {out_abs}
            for SRC in {tmp_abs}/*.mkv; do
              BASE="$(basename "${{SRC%.*}}")"
              OUT={out_abs}/"$BASE".{shlex.quote(container)}
              echo "[TKAR] HandBrake encoding: $SRC -> $OUT"
              {hb_template_str.replace("INPUT_PLACEHOLDER", '"$SRC"').replace("OUTPUT_PLACEHOLDER", '"$OUT"')}
            done
        '''.strip()

        steps.append(
            (["bash", "-lc", shell_script],
             f"Encoding {disc_type} titles with HandBrake",
             False,
             0.30)
        )
    else:
        # Copy MKVs to output dir with Linux-style " (1)" collision handling
        tmp_abs = shlex.quote(str(temp_dir))
        out_abs = shlex.quote(str(output_dir))

        copy_script_template = r'''
            shopt -s nullglob
            mkdir -p __OUTDIR__
            copy_with_suffix() {
              local src="$1"; local dir="$2"
              local base="$(basename "${src%.*}")"
              local ext="${src##*.}"
              local out="${dir}/${base}.${ext}"
              local n=1
              while [ -e "$out" ]; do
                out="${dir}/${base} (${n}).${ext}"
                n=$((n+1))
              done
              echo "[TKAR] Copying: $src -> $out"
              cp -f -- "$src" "$out"
            }
            for SRC in __TMPDIR__/*.mkv; do
              copy_with_suffix "$SRC" "__OUTDIR__"
            done
        '''.strip()

        shell_script = (
            copy_script_template
            .replace("__TMPDIR__", tmp_abs)
            .replace("__OUTDIR__", out_abs)
        )

        steps.append(
            (["bash", "-lc", shell_script],
             f"Copying {disc_type} titles to output",
             False,
             0.30)
        )

    return steps
