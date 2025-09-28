# app/core/rippers/other/linux.py
from pathlib import Path
from typing import List, Tuple

from app.core.configmanager import config
from app.core.integration.dd.linux import build_iso_dump_cmd
from app.core.integration.zstd.linux import build_zstd_cmd
from app.core.job.job import Job


def rip_generic_disc(job: Job) -> List[Tuple[List[str], str, bool]]:
    """
    ISO dump (drive needed) then optional compression.
    """
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = cfg.get("compression", "zstd").lower()

    iso_path = job.temp_path / f"{job.disc_label}.iso"
    steps: List[Tuple[List[str], str, bool]] = [
        (build_iso_dump_cmd(job.drive, iso_path), "Creating ISO image", True)
    ]

    if use_comp and comp_alg == "zstd":
        steps.append(
            (build_zstd_cmd(iso_path, job.output_path.with_suffix(".iso.zst")),
             "Compressing ISO (zstd)",
             False)
        )
    elif use_comp and comp_alg == "bz2":
        steps.append(
            (["bzip2", str(iso_path)],
             "Compressing ISO (bzip2)",
             False)
        )
    else:
        steps.append(
            (["cp", str(iso_path), str(job.output_path.with_suffix('.iso'))],
             "Copying ISO to final destination",
             False)
        )

    return steps
