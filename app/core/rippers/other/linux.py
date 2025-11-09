# app/core/rippers/other/linux.py
from pathlib import Path
from typing import List, Tuple

from app.core.configmanager import config
from app.core.integration.dd.linux import build_iso_dump_cmd  # 
from app.core.integration.zstd.linux import build_zstd_cmd     # 
from app.core.job.job import Job

# Step can optionally include a 5th element: dest Path
Step = Tuple[List[str], str, bool] \
    | Tuple[List[str], str, bool, float] \
    | Tuple[List[str], str, bool, float, Path]

def _unique_path(p: Path) -> Path:
    """
    Return a path that doesn't exist by adding ' (1)', ' (2)', ... before the full suffix.
    Works for multi-suffix like .iso.zst  ->  name (1).iso.zst
    """
    if not p.exists():
        return p
    stem = p.name
    # Split into base and full suffix chain
    suffixes = "".join(p.suffixes)
    base = p.name[: len(p.name) - len(suffixes)] if suffixes else p.stem
    n = 1
    while True:
        candidate = p.with_name(f"{base} ({n}){suffixes}")
        if not candidate.exists():
            return candidate
        n += 1

def rip_generic_disc(job: Job) -> List[Step]:
    """
    ISO dump (drive needed) then optional compression.
    Steps:
      1) dd → temp ISO (drive released afterwards)
      2) compress/copy → final destination (dest provided)
         - If user provided override_filename, use it exactly (no auto-rename).
         - Otherwise auto-rename to ' (1)', ' (2)', ... if a collision exists.
    """
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", "zstd")).lower()

    # temp ISO lives in the job's temp folder
    iso_path = job.temp_path / f"{job.disc_label}.iso"

    # final base path is a FILE path (if override_filename) or <dir>/<disc_label>.iso[.zst]
    out_dir: Path = job.output_path
    out_dir.mkdir(parents=True, exist_ok=True)

    target_iso = out_dir / f"{job.disc_label}.iso"
    # auto-rename if exists
    target_iso = _unique_path(target_iso)

    steps: List[Step] = [
        (build_iso_dump_cmd(job.drive, iso_path), "Creating ISO image", True)
    ]

    if use_comp and comp_alg == "zstd":
        out_zst = target_iso if str(target_iso).endswith(".zst") else target_iso.with_suffix(target_iso.suffix + ".zst")
        # If auto-rename mode, ensure compressed name is also unique
        if auto_rename:
            out_zst = _unique_path(out_zst)
        steps.append(
            (build_zstd_cmd(iso_path, out_zst),
             "Compressing ISO (zstd)",
             False,
             0.5,
             out_zst)
        )
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        out_bz2 = target_iso if str(target_iso).endswith(".bz2") else target_iso.with_suffix(target_iso.suffix + ".bz2")
        if auto_rename:
            out_bz2 = _unique_path(out_bz2)
        steps.append(
            (["bzip2", "-v", "-k", "-f", str(iso_path)],
             "Compressing ISO (bzip2)",
             False,
             0.5,
             out_bz2)
        )
    else:
        final = target_iso if auto_rename else target_iso
        if auto_rename:
            final = _unique_path(final)
        steps.append(
            (["cp", "-f", str(iso_path), str(final)],
             "Copying ISO to final destination",
             False,
             0.5,
             final)
        )

    return steps
