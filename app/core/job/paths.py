# app/core/job/paths.py
from pathlib import Path

from app.core.configmanager import config
from app.core.job.job import sanitize_folder


def default_rom_output_path(disc_type: str, disc_label: str | None) -> Path:
    """
    Default final file path for ROM/OTHER discs based on config and disc label.

    Example:
        ~/TKAutoRipper/output/ISO/My Disc/My Disc.iso.zst
    """
    name = sanitize_folder(disc_label or "DISC")
    other_cfg = config.section("OTHER")

    base = (
        other_cfg.get("outputdirectory")
        or config.section("General").get("outputdirectory")
        or "~/TKAutoRipper/output/ISO"
    )
    base_dir = Path(str(base)).expanduser() / name

    use_comp = other_cfg.get("usecompression", True)
    comp_alg = str(other_cfg.get("compression", "zstd")).lower()

    if use_comp and comp_alg == "zstd":
        return base_dir / f"{name}.iso.zst"
    if use_comp and comp_alg in {"bz2", "bzip2"}:
        return base_dir / f"{name}.iso.bz2"
    return base_dir / f"{name}.iso"
