# app/core/rippers/other/macos.py

from pathlib import Path
from typing import List, Tuple, Any
import re
import subprocess

from app.core.configmanager import config
from app.core.integration.dd.macos import build_iso_dump_cmd
from app.core.integration.zstd.macos import build_zstd_cmd
from app.core.job.job import Job

# Step can be (cmd, desc, release, [weight|dest|adapter] ...)
Step = Tuple[Any, ...]


class DdProgressAdapter:
    """
    macOS-specific progress adapter for dd status=progress output.

    Parses lines like:
      "26656768 bytes transferred ..."
    and computes done_bytes / expected_bytes.

    expected_bytes is obtained from `diskutil info <device>`:
      Total Size: ... (NNN Bytes)
    """

    _bytes_re = re.compile(r"(\d+)\s+bytes")

    def __init__(self, device: str) -> None:
        # device should be a real device path, e.g. /dev/rdisk2
        self.device = device

    def on_start(self, job: Job, cmd: List[str], state: dict) -> None:
        try:
            dev = self.device
            # diskutil prefers /dev/diskN rather than /dev/rdiskN
            if dev.startswith("/dev/rdisk"):
                info_dev = dev.replace("/dev/rdisk", "/dev/disk")
            else:
                info_dev = dev

            res = subprocess.run(
                ["diskutil", "info", info_dev],
                capture_output=True,
                text=True,
                check=False,
            )
            out = res.stdout or ""
            # Look for "(NNN Bytes)" pattern
            m = re.search(r"\((\d+)\s+Bytes\)", out)
            if m:
                state["expected_bytes"] = int(m.group(1))
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


def _resolve_raw_device(drive: str) -> str:
    """
    Map our internal macOS drive IDs (e.g. 'DRIVE0') to a block device path.

    Strategy:
      - DRIVE<N> → parse index N → `drutil status -drive N`
        → look for 'Name: /dev/diskM' → return '/dev/rdiskM'
      - '/dev/rdisk*' or '/dev/disk*' → pass through
      - anything else → return as-is (dd may fail, but we won't crash here)
    """
    # Logical ID from mac drive detector
    m = re.match(r"DRIVE(\d+)$", drive)
    if m:
        idx = int(m.group(1))
        try:
            result = subprocess.run(
                ["drutil", "status", "-drive", str(idx)],
                capture_output=True,
                text=True,
                check=False,
            )
            out = result.stdout or ""
            m2 = re.search(r"Name:\s+(/dev/disk[0-9]+)", out)
            if m2:
                disk = m2.group(1)
                # Prefer raw device for speed: /dev/rdiskN
                if disk.startswith("/dev/disk"):
                    return disk.replace("/dev/disk", "/dev/rdisk")
                return disk
        except Exception:
            pass

    # Already a device path
    if drive.startswith("/dev/rdisk") or drive.startswith("/dev/disk"):
        return drive

    # Fallback: just return what we got; dd may not like it, but we don't crash here
    return drive


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

    # Resolve DRIVE<N> → /dev/rdiskN
    raw_device = _resolve_raw_device(job.drive)

    # temp ISO lives in the job's temp folder
    iso_path = job.temp_path / f"{job.disc_label}.iso"

    # final base path is a FILE path (<dir>/<disc_label>.iso[.zst])
    out_dir: Path = job.output_path
    out_dir.mkdir(parents=True, exist_ok=True)

    target_iso = out_dir / f"{job.disc_label}.iso"
    target_iso = _unique_path(target_iso)

    steps: List[Step] = [
        # attach mac-specific dd progress adapter as 4th element
        (
            build_iso_dump_cmd(raw_device, iso_path),
            "Creating ISO image",
            True,
            DdProgressAdapter(raw_device),
        )
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
