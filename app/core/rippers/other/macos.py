# app/core/rippers/other/macos.py
from pathlib import Path
from typing import List, Tuple, Any
import re
import shlex

from app.core.configmanager import config
from app.core.integration.zstd.macos import build_zstd_cmd
from app.core.job.job import Job, sanitize_folder

# Step can be (cmd, desc, release, [weight|dest|adapter] ...)
Step = Tuple[Any, ...]


class HdiutilProgressAdapter:
    """
    Lightweight progress adapter for hdiutil makehybrid output.
    Looks for lines containing a percentage and passes that through.
    """

    _pct_re = re.compile(r"(\d+(?:\.\d+)?)%")

    def on_start(self, job: Job, cmd: List[str], state: dict) -> None:
        state.clear()

    def on_line(self, line: str, state: dict, job: Job):
        m = self._pct_re.search(line)
        if m:
            try:
                pct = float(m.group(1))
                pct = max(0.0, min(100.0, pct))
                return (pct, None)
            except ValueError:
                return (None, None)
        return (None, None)


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


def _raw_device(dev: str) -> str:
    """
    Convert /dev/diskX → /dev/rdiskX for faster raw access.
    """
    if dev.startswith("/dev/disk"):
        return "/dev/r" + dev[len("/dev/") :]
    return dev


def _normalize_output_path(job: Job, label: str) -> tuple[Path, bool, str]:
    """
    Decide the final output path based on config and requested compression.

    Returns (final_path, use_compression, comp_alg).
    """
    configured = Path(job.output_path)
    cfg = config.section("OTHER")
    use_comp = cfg.get("usecompression", True)
    comp_alg = str(cfg.get("compression", "zstd")).lower()

    # Base ISO path (without compression suffix)
    if configured.is_dir():
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


def _build_makehybrid_script(dev: str, iso_path: Path) -> str:
    dev_q = shlex.quote(dev)
    raw_dev = _raw_device(dev)
    raw_q = shlex.quote(raw_dev)
    iso_q = shlex.quote(str(iso_path))
    # Unmount any mounted partitions to avoid busy device errors, then create the ISO.
    return f"""
set -e
DEV={dev_q}
RAW={raw_q}
ISO={iso_q}
hdiutil unmount "${{DEV}}s"* >/dev/null 2>&1 || true
hdiutil makehybrid -o "$ISO" "$RAW" -verbose
""".strip()


def rip_generic_disc(job: Job) -> List[Step]:
    """
    macOS generic/ROM ripper using hdiutil makehybrid.

    Steps:
      1) hdiutil makehybrid → temp ISO (drive released afterwards)
      2) optional compression or copy to final destination
    """
    cfg = config.section("OTHER")
    meta = job.metadata

    label = sanitize_folder(job.disc_label or "DISC") or "DISC"

    # Persist source drive and paths so retries don't require the drive if ISO exists
    source_drive = meta.get("rom_source_drive") or job.drive
    temp_iso = Path(meta.get("rom_temp_iso") or (job.temp_path / f"{label}.iso"))
    if meta.get("rom_final_iso"):
        final_path = Path(meta["rom_final_iso"])
        use_comp = bool(meta.get("rom_use_comp", cfg.get("usecompression", True)))
        comp_alg = str(meta.get("rom_comp_alg") or cfg.get("compression", "zstd")).lower()
    else:
        final_path, use_comp, comp_alg = _normalize_output_path(job, label)
        meta["rom_final_iso"] = str(final_path)
        meta["rom_use_comp"] = use_comp
        meta["rom_comp_alg"] = comp_alg
    meta["rom_temp_iso"] = str(temp_iso)
    if source_drive:
        meta["rom_source_drive"] = source_drive

    iso_exists = temp_iso.exists()

    if not source_drive and not iso_exists:
        raise ValueError("No source drive available for generic rip")

    # Ensure destination folders exist before running hdiutil/compression
    temp_iso.parent.mkdir(parents=True, exist_ok=True)
    final_path.parent.mkdir(parents=True, exist_ok=True)

    steps: List[Step] = []

    if not iso_exists:
        steps.append(
            (
                ["bash", "-lc", _build_makehybrid_script(source_drive, temp_iso)],
                "Creating ISO image",
                True,
                HdiutilProgressAdapter(),
            )
        )

    if use_comp and comp_alg == "zstd":
        steps.append(
            (
                build_zstd_cmd(temp_iso, final_path),
                "Compressing ISO (zstd)",
                False,
                0.5,
                final_path,
            )
        )
    elif use_comp and comp_alg in {"bz2", "bzip2"}:
        bzip_cmd = [
            "bash",
            "-lc",
            f'bzip2 -v -k -f "{temp_iso}" && mv "{temp_iso}.bz2" "{final_path}"',
        ]
        steps.append(
            (
                bzip_cmd,
                "Compressing ISO (bzip2)",
                False,
                0.5,
                final_path,
            )
        )
    else:
        steps.append(
            (
                ["cp", "-f", str(temp_iso), str(final_path)],
                "Copying ISO to final destination",
                False,
                0.5,
                final_path,
            )
        )

    return steps
