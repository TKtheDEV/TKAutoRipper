# app/core/rippers/other/linux.py
from pathlib import Path
from typing import List, Tuple

from app.core.configmanager import config
from app.core.integration.dd.linux import build_iso_dump_cmd
from app.core.integration.zstd.linux import build_zstd_cmd
from app.core.job.job import Job

# Step can optionally include a 5th element: dest Path
Step = Tuple[List[str], str, bool] \
    | Tuple[List[str], str, bool, float] \
    | Tuple[List[str], str, bool, float, Path]

def rip_generic_disc(job: Job) -> List[Step]:
    """
    ISO dump (drive needed) then optional compression.
    Steps:
      1) dd → temp ISO (drive released afterwards)
      2) compress/copy → final destination (dest provided)
    """
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", "zstd")).lower()

    # temp ISO lives in the job's temp folder
    iso_path = job.temp_path / f"{job.disc_label}.iso"

    # final base path is a FILE path (if override_filename) or <dir>/<disc_label>.iso[.zst]
    out_dir: Path = job.output_path
    out_dir.mkdir(parents=True, exist_ok=True)

    if job.override_filename:
        # user supplied full file name for ROM: parent is output_dir, name is override
        target = out_dir / job.override_filename
    else:
        target = out_dir / f"{job.disc_label}.iso"

    steps: List[Step] = [
        (build_iso_dump_cmd(job.drive, iso_path), "Creating ISO image", True)
    ]

    if use_comp and comp_alg == "zstd":
        out_zst = target if str(target).endswith(".zst") else target.with_suffix(target.suffix + ".zst")
        steps.append(
            (build_zstd_cmd(iso_path, out_zst),
             "Compressing ISO (zstd)",
             False,
             0.5,
             out_zst)
        )
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        out_bz2 = target if str(target).endswith(".bz2") else target.with_suffix(target.suffix + ".bz2")
        steps.append(
            (["bzip2", "-v", "-k", "-f", str(iso_path)],
             "Compressing ISO (bzip2)",
             False,
             0.5,
             out_bz2)
        )
    else:
        steps.append(
            (["cp", "-f", str(iso_path), str(target)],
             "Copying ISO to final destination",
             False,
             0.5,
             target)
        )

    return steps
