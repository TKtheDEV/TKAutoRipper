from __future__ import annotations

from pathlib import Path
from typing import List, Tuple, Any
import logging

from app.core.configmanager import config
from app.core.job.job import Job, sanitize_folder

# Step can be (cmd, desc, release, [weight|dest|adapter] ...)
Step = Tuple[Any, ...]


def _unique_path(p: Path) -> Path:
    """
    Return a path that doesn't exist by adding ' (1)', ' (2)', ... before the full suffix.
    Works for multi-suffix like .iso.zst  ->  name (1).iso.zst
    """
    if not p.exists():
        return p
    suffixes = "".join(p.suffixes)
    base = p.name[: len(p.name) - len(suffixes)] if suffixes else p.stem
    n = 1
    while True:
        candidate = p.with_name(f"{base} ({n}){suffixes}")
        if not candidate.exists():
            return candidate
        n += 1


def _ps_quote(val: Path | str) -> str:
    """PowerShell single-quoted literal with embedded quotes doubled."""
    s = str(val)
    return "'" + s.replace("'", "''") + "'"


def _normalize_output_path(job: Job) -> tuple[Path, bool, str]:
    """
    Decide the final output path based on config and requested compression.

    Returns (final_path, use_compression, comp_alg).
    """
    configured = Path(job.output_path)
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", none)).lower()

    # Base ISO path (without compression suffix)
    if configured.is_dir():
        label = sanitize_folder(job.disc_label or "DISC") or "DISC"
        base_iso = configured / f"{label}.iso"
    else:
        base_iso = configured
        if base_iso.suffix.lower() in {".zst", ".bz2"}:
            base_iso = base_iso.with_suffix("")  # strip compression suffix
        if base_iso.suffix.lower() != ".iso":
            base_iso = base_iso.with_suffix(".iso")

    if use_comp and comp_alg == "zstd":
        final = Path(str(base_iso) + ".zst")
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        final = Path(str(base_iso) + ".bz2")
    else:
        final = base_iso
        use_comp = False  # unsupported alg => fall back to plain ISO

    final_path = _unique_path(final)
    job.output_path = final_path
    return final_path, use_comp, comp_alg


def rip_generic_disc(job: Job) -> List[Step]:
    """
    Windows generic/ROM ripper.

    Steps:
      1) PowerShell raw copy of the drive to an ISO in temp (releases drive)
      2) Move ISO to final destination (no compression on Windows path)
    """
    meta = job.metadata

    source_drive = meta.get("rom_source_drive") or job.drive
    if not source_drive:
        raise ValueError("No source drive available for generic rip")
    meta["rom_source_drive"] = source_drive

    if meta.get("rom_final_iso"):
        final_iso = Path(meta["rom_final_iso"])
        use_comp = bool(meta.get("rom_use_comp"))
        comp_alg = str(meta.get("rom_comp_alg") or "zstd").lower()
        temp_iso = Path(meta.get("rom_temp_iso") or job.temp_path / "temp.iso")
        # ensure job.output_path stays aligned
        job.output_path = final_iso
    else:
        temp_name = sanitize_folder(job.disc_label or "disc") or "disc"
        temp_iso = job.temp_path / f"{temp_name}.iso"
        final_iso, use_comp, comp_alg = _normalize_output_path(job)
        meta["rom_temp_iso"] = str(temp_iso)
        meta["rom_final_iso"] = str(final_iso)
        meta["rom_use_comp"] = use_comp
        meta["rom_comp_alg"] = comp_alg

    # PowerShell script to stream \\.\<drive> to temp_iso
    device_path = r"\\.\{}".format(source_drive.rstrip("\\"))
    ps_script = f"""
$ErrorActionPreference = 'Stop'
$src = {_ps_quote(device_path)}
$dst = {_ps_quote(temp_iso)}
$dir = Split-Path -Parent $dst
New-Item -ItemType Directory -Force -Path $dir | Out-Null
[byte[]]$buf = New-Object byte[] (4MB)
$in  = [System.IO.File]::Open($src, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
$out = [System.IO.File]::Open($dst, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
$last = Get-Date
while (($read = $in.Read($buf, 0, $buf.Length)) -gt 0) {{
    $out.Write($buf, 0, $read)
    if ((New-TimeSpan -Start $last).TotalSeconds -ge 5) {{
        Write-Host "[TKAR] Copied $([Math]::Round($in.Position/1MB,2)) MB"
        $last = Get-Date
    }}
}}
$out.Close()
$in.Close()
Write-Host "[TKAR] ISO creation complete: $dst"
""".strip()

    # Compression / copy step
    steps: List[Step] = [
        (["powershell", "-NoProfile", "-Command", ps_script], "Creating ISO image", True),
    ]

    if use_comp and comp_alg == "zstd":
        zstd_script = f"""
$ErrorActionPreference = 'Stop'
$src = {_ps_quote(temp_iso)}
$dst = {_ps_quote(final_iso)}
$dir = Split-Path -Parent $dst
New-Item -ItemType Directory -Force -Path $dir | Out-Null
zstd -T0 -q --force -o $dst $src
Write-Host "[TKAR] Compressed ISO to $dst"
""".strip()
        steps.append(
            (["powershell", "-NoProfile", "-Command", zstd_script], "Compressing ISO (zstd)", False, 0.5, final_iso)
        )
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        bzip_script = f"""
$ErrorActionPreference = 'Stop'
$src = {_ps_quote(temp_iso)}
$dst = {_ps_quote(final_iso)}
$dir = Split-Path -Parent $dst
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$bzipCmd = (Get-Command bzip2 -ErrorAction SilentlyContinue).Path
if (-not $bzipCmd) {{
    $fallback = 'C:\\Program Files (x86)\\GnuWin32\\bin\\bzip2.exe'
    if (Test-Path $fallback) {{ $bzipCmd = $fallback }}
}}
if (-not $bzipCmd) {{ throw 'bzip2 not found (add to PATH or install)' }}
& $bzipCmd -k -f $src
$compressed = "$src.bz2"
Move-Item -LiteralPath $compressed -Destination $dst -Force
Write-Host "[TKAR] Compressed ISO to $dst"
""".strip()
        steps.append(
            (["powershell", "-NoProfile", "-Command", bzip_script], "Compressing ISO (bzip2)", False, 0.5, final_iso)
        )
    else:
        copy_script = f"""
$ErrorActionPreference = 'Stop'
$src = {_ps_quote(temp_iso)}
$dst = {_ps_quote(final_iso)}
$dir = Split-Path -Parent $dst
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Move-Item -LiteralPath $src -Destination $dst -Force
Write-Host "[TKAR] Moved ISO to $dst"
""".strip()
        steps.append(
            (["powershell", "-NoProfile", "-Command", copy_script], "Copying ISO to final destination", False, 0.5, final_iso)
        )

    return steps
