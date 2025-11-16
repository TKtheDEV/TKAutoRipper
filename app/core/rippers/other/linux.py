# app/core/rippers/other/linux.py
from pathlib import Path
from typing import List, Tuple

from app.core.configmanager import config
from app.core.integration.dd.linux import build_iso_dump_cmd
from app.core.integration.zstd.linux import build_zstd_cmd
from app.core.job.job import Job

# Step can optionally include a 5th element: dest Path
Step = (
    Tuple[List[str], str, bool]
    | Tuple[List[str], str, bool, float]
    | Tuple[List[str], str, bool, float, Path]
)


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


def rip_generic_disc(job: Job) -> List[Step]:
    """
    ISO dump (drive needed) then optional compression.

    Steps:
      1) dd → temp ISO (drive released afterwards)
      2) compress/copy → final destination (dest provided)

    For ROM discs, job.output_path is treated as the *final file path*
    (e.g., /media/ISO/My Disc/My Disc.iso.zst). The UI can change this path
    any time before output is locked; directories are created when locked.
    """
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", "zstd")).lower()

    # Temp ISO lives in the job's temp folder
    iso_path = job.temp_path / f"{job.disc_label}.iso"

    # Final requested path from the job (may or may not match compression config)
    dest = Path(str(job.output_path)).expanduser()

    # If user somehow gave us a directory or no suffix, normalize to <dir>/<label>.iso
    if dest.is_dir() or not dest.suffix:
        dest = dest / f"{job.disc_label}.iso"

    steps: List[Step] = [
        (build_iso_dump_cmd(job.drive, iso_path), "Creating ISO image", True)
    ]

    if use_comp and comp_alg == "zstd":
        # Ensure final has a zstd-ish suffix
        if not any(str(dest).lower().endswith(ext) for ext in (".iso.zst", ".zst")):
            dest = dest.with_suffix(dest.suffix + ".zst")
        final = _unique_path(dest)
        steps.append(
            (
                build_zstd_cmd(iso_path, final),
                "Compressing ISO (zstd)",
                False,
                0.5,
                final,
            )
        )

    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        if not any(str(dest).lower().endswith(ext) for ext in (".iso.bz2", ".bz2")):
            dest = dest.with_suffix(dest.suffix + ".bz2")
        final = _unique_path(dest)
        # bzip2 writes <iso>.bz2; we keep command simple and rely on naming
        steps.append(
            (
                ["bzip2", "-v", "-k", "-f", str(iso_path)],
                "Compressing ISO (bzip2)",
                False,
                0.5,
                final,
            )
        )

    else:
        # No compression → just copy ISO to requested .iso path
        if not dest.suffix.lower().endswith(".iso"):
            dest = dest.with_suffix(".iso")
        final = _unique_path(dest)
        steps.append(
            (
                ["cp", "-f", str(iso_path), str(final)],
                "Copying ISO to final destination",
                False,
                0.5,
                final,
            )
        )

    return steps
