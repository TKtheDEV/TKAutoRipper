# app/core/rippers/other/linux.py
from pathlib import Path
from typing import List, Tuple, Any
import re
import subprocess
import shlex

from app.core.configmanager import config
from app.core.integration.dd.linux import build_iso_dump_cmd
from app.core.integration.zstd.linux import build_zstd_cmd
from app.core.job.job import Job, sanitize_folder

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
    meta = job.metadata
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", "zstd")).lower()

    # temp ISO lives in the job's temp folder
    label = sanitize_folder(job.disc_label or "DISC") or "DISC"
    temp_iso = Path(meta.get("rom_temp_iso") or (job.temp_path / f"{label}.iso"))
    source_drive = meta.get("rom_source_drive") or job.drive

    # Decide final output path and compression settings (persisted for retries).
    if meta.get("rom_final_iso"):
        final_path = Path(meta["rom_final_iso"])
        use_comp = bool(meta.get("rom_use_comp", use_comp))
        comp_alg = str(meta.get("rom_comp_alg") or comp_alg).lower()
    else:
        # Treat job.output_path as the desired final FILE path; if it lacks a suffix,
        # build one based on compression settings.
        configured = Path(job.output_path)
        if configured.suffix:
            base_dir = configured.parent
            filename = configured.name
        else:
            base_dir = configured
            filename = ""

        if not filename:
            if use_comp and comp_alg == "zstd":
                filename = f"{label}.iso.zst"
            elif use_comp and comp_alg in {"bz2", "bzip2"}:
                filename = f"{label}.iso.bz2"
            else:
                filename = f"{label}.iso"
        else:
            if use_comp and comp_alg == "zstd" and not filename.endswith(".zst"):
                filename = filename + ".zst"
            elif use_comp and comp_alg in {"bz2", "bzip2"} and not filename.endswith(".bz2"):
                filename = filename + ".bz2"
            elif not use_comp and filename.endswith((".zst", ".bz2")):
                # Strip compression suffix when compression is disabled.
                if filename.endswith(".zst"):
                    filename = filename[:-4]
                elif filename.endswith(".bz2"):
                    filename = filename[:-4]

        final_path = _unique_path(base_dir / filename)
        meta["rom_final_iso"] = str(final_path)
        meta["rom_use_comp"] = use_comp
        meta["rom_comp_alg"] = comp_alg

    meta["rom_temp_iso"] = str(temp_iso)
    if source_drive:
        meta["rom_source_drive"] = source_drive
        # keep job.drive in sync so release/eject logic can work on retries
        job.drive = source_drive

    job.output_path = final_path

    iso_exists = temp_iso.exists()
    if not source_drive and not iso_exists:
        raise ValueError("No source drive available for generic rip")

    steps: List[Step] = []
    if iso_exists:
        steps.append(
            (
                [
                    "bash",
                    "-lc",
                    f'echo "[TKAR] Reusing existing ISO: {shlex.quote(str(temp_iso))}"',
                ],
                "Reusing existing ISO image",
                False,
            )
        )
    else:
        # attach Linux-specific dd progress adapter as 4th element
        steps.append(
            (
                build_iso_dump_cmd(source_drive, temp_iso),
                "Creating ISO image",
                True,
                DdProgressAdapter(source_drive),
            )
        )

    if use_comp and comp_alg == "zstd":
        steps.append(
            (
                build_zstd_cmd(temp_iso, final_path),
                "Compressing ISO (zstd)",
                False,
                final_path,
            )
        )
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        steps.append(
            (
                [
                    "bash",
                    "-lc",
                    f"bzip2 -v -k -f {shlex.quote(str(temp_iso))} && mv {shlex.quote(str(temp_iso))}.bz2 {shlex.quote(str(final_path))}",
                ],
                "Compressing ISO (bzip2)",
                False,
                final_path,
            )
        )
    else:
        steps.append(
            (
                ["cp", "-f", str(temp_iso), str(final_path)],
                "Copying ISO to final destination",
                False,
                final_path,
            )
        )

    return steps
