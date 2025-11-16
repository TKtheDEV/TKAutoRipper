# app/core/rippers/other/linux.py
from pathlib import Path
from typing import List, Tuple, Any
import re
import subprocess

from app.core.configmanager import config
from app.core.integration.dd.linux import build_iso_dump_cmd
from app.core.integration.zstd.linux import build_zstd_cmd
from app.core.job.job import Job

# Step can be (cmd, desc, release, [weight|dest|adapter] ...)
Step = Tuple[Any, ...]


class DdProgressAdapter:
    """
    Linux-specific progress adapter for dd status=progress output.

    Parses lines like:
      "26656768 bytes (27 MB, 25 MiB) copied, 24.1295 s, 1.1 MB/s"
    and computes done_bytes / expected_bytes.
    """

    _bytes_re = re.compile(r"(\d+)\s+bytes")

    def __init__(self, device: str) -> None:
        self.device = device

    def on_start(self, job: Job, cmd: List[str], state: dict) -> None:
        try:
            res = subprocess.run(
                ["blockdev", "--getsize64", self.device],
                capture_output=True,
                text=True,
                check=False,
            )
            val = res.stdout.strip()
            if val.isdigit():
                state["expected_bytes"] = int(val)
            else:
                state["expected_bytes"] = None
        except Exception:
            state["expected_bytes"] = None

    def on_line(self, line: str, state: dict, job: Job):
        expected = state.get("expected_bytes")
        if not expected:
            return (None, None)
        m = self._bytes_re.search(line)
        if not m:
            return (None, None)
        done = float(m.group(1))
        pct = max(0.0, min(100.0, (done / expected) * 100.0))
        return (pct, None)


def _unique_path(p: Path) -> Path:
    """
    Return a path that doesn't exist by adding ' (1)', ' (2)', ... before the full suffix.
    Works for multi-suffix like .iso.zst  ->  name (1).iso.zst
    """
    if not p.exists():
        return p
    stem = p.name
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
      1) dd → temp ISO (drive released afterwards)       [DdProgressAdapter]
      2) compress/copy → final destination (dest provided)
    """
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", "zstd")).lower()

    # temp ISO lives in the job's temp folder
    iso_path = job.temp_path / f"{job.disc_label}.iso"

    # final base path is a FILE path (<dir>/<disc_label>.iso[.zst])
    out_dir: Path = job.output_path
    out_dir.mkdir(parents=True, exist_ok=True)

    target_iso = out_dir / f"{job.disc_label}.iso"
    target_iso = _unique_path(target_iso)

    steps: List[Step] = [
        # attach Linux-specific dd progress adapter as 4th element
        (build_iso_dump_cmd(job.drive, iso_path), "Creating ISO image", True, DdProgressAdapter(job.drive))
    ]

    if use_comp and comp_alg == "zstd":
        out_zst = (
            target_iso
            if str(target_iso).endswith(".zst")
            else target_iso.with_suffix(target_iso.suffix + ".zst")
        )
        out_zst = _unique_path(out_zst)
        steps.append(
            (
                build_zstd_cmd(iso_path, out_zst),
                "Compressing ISO (zstd)",
                False,
                0.5,
                out_zst,
            )
        )
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        out_bz2 = (
            target_iso
            if str(target_iso).endswith(".bz2")
            else target_iso.with_suffix(target_iso.suffix + ".bz2")
        )
        out_bz2 = _unique_path(out_bz2)
        steps.append(
            (
                ["bzip2", "-v", "-k", "-f", str(iso_path)],
                "Compressing ISO (bzip2)",
                False,
                0.5,
                out_bz2,
            )
        )
    else:
        final = _unique_path(target_iso)
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
