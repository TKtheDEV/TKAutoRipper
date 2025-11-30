# app/core/rippers/video/windows.py
"""
DVD / Blu-ray VIDEO ripper helper (Windows).

Steps:
  1. MakeMKV  →  creates *.mkv titles in job.temp_path, releases drive   (weight ≈ 0.70)
  2a. HandBrake → encodes each MKV from temp into job.output_path          (weight ≈ 0.30)
  2b. Copy MKVs → copies MKVs from temp to job.output_path (if HB disabled)(weight ≈ 0.30)

All paths are absolute so it works no matter what cwd the runner uses.
"""

from pathlib import Path
from typing import List, Tuple

from app.core.configmanager import config
from app.core.integration.makemkv.windows import build_makemkv_cmd
from app.core.integration.handbrake.windows import build_handbrake_cmd
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


def _ps_quote(s: str) -> str:
    """
    PowerShell single-quoted string literal.
    Backslashes are fine; single quotes are doubled.
    """
    s = str(s)
    return "'" + s.replace("'", "''") + "'"


def _build_hb_ps_invocation(hb_template: List[str]) -> str:
    """
    Convert a HandBrake command template (with INPUT/OUTPUT placeholders)
    into a PowerShell invocation line like:

        & 'C:\\Path\\HandBrakeCLI.exe' -i $src -o $out ...

    where:
      - INPUT_PLACEHOLDER  → $src
      - OUTPUT_PLACEHOLDER → $out
    """
    ps_tokens: List[str] = []

    for tok in hb_template:
        if tok == "INPUT_PLACEHOLDER":
            ps_tokens.append("$src")
        elif tok == "OUTPUT_PLACEHOLDER":
            ps_tokens.append("$out")
        else:
            ps_tokens.append(_ps_quote(tok))

    # Prepend '&' to actually invoke the command
    ps_tokens.insert(0, "&")
    return " ".join(ps_tokens)


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
            mkv_file="INPUT_PLACEHOLDER",
            output_path="OUTPUT_PLACEHOLDER",
            preset_path=(str(preset_path) if preset_path else None),
            preset_name=preset_name,
        )
        hb_ps_invocation = _build_hb_ps_invocation(hb_template)

        tmp_ps = _ps_quote(temp_dir)
        out_ps = _ps_quote(output_dir)

        # NOTE: __TEMP_DIR__, __OUT_DIR__, __CONTAINER__, __HB_CMD__ are placeholders
        hb_script_template = r'''
$ErrorActionPreference = 'Stop'
$TempDir = __TEMP_DIR__
$OutDir  = __OUT_DIR__
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Get-ChildItem -LiteralPath $TempDir -Filter '*.mkv' | ForEach-Object {
    $src  = $_.FullName
    $base = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
    $out  = Join-Path $OutDir ("{0}.__CONTAINER__" -f $base)
    Write-Host "[TKAR] HandBrake encoding: $src -> $out"
    __HB_CMD__
}
'''.strip()

        shell_script = (
            hb_script_template
            .replace("__TEMP_DIR__", tmp_ps)
            .replace("__OUT_DIR__", out_ps)
            .replace("__CONTAINER__", container)
            .replace("__HB_CMD__", hb_ps_invocation)
        )

        steps.append(
            (["powershell", "-NoProfile", "-Command", shell_script],
             f"Encoding {disc_type} titles with HandBrake",
             False,
             0.30)
        )

    else:
        # Copy MKVs to output dir with Windows-style " (1)" collision handling
        tmp_ps = _ps_quote(temp_dir)
        out_ps = _ps_quote(output_dir)

        copy_script_template = r'''
$ErrorActionPreference = 'Stop'
$TempDir = __TEMP_DIR__
$OutDir  = __OUT_DIR__
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

Get-ChildItem -LiteralPath $TempDir -Filter '*.mkv' | ForEach-Object {
    $src  = $_.FullName
    $base = [System.IO.Path]::GetFileNameWithoutExtension($_.Name)
    $ext  = $_.Extension
    $n    = 1
    $dest = Join-Path $OutDir ("{0}{1}" -f $base, $ext)

    while (Test-Path $dest) {
        $dest = Join-Path $OutDir ("{0} ({1}){2}" -f $base, $n, $ext)
        $n++
    }

    Write-Host "[TKAR] Copying: $src -> $dest"
    Copy-Item -LiteralPath $src -Destination $dest -Force
}
'''.strip()

        shell_script = (
            copy_script_template
            .replace("__TEMP_DIR__", tmp_ps)
            .replace("__OUT_DIR__", out_ps)
        )

        steps.append(
            (["powershell", "-NoProfile", "-Command", shell_script],
             f"Copying {disc_type} titles to output",
             False,
             0.30)
        )

    return steps
