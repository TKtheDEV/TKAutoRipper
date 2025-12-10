# Shared macOS drive↔device mapping state so detector and disc monitor stay in sync.
from __future__ import annotations

from typing import Dict, Optional

_device_to_drive: Dict[str, str] = {}
_drive_to_device: Dict[str, str] = {}


def drive_id_for(index: int, dev_path: Optional[str]) -> str:
    """
    Return a logical DRIVE id for a given index/device.
    Prefer an existing mapping for the device; otherwise fall back to DRIVE<index>.
    """
    if dev_path and dev_path in _device_to_drive:
        return _device_to_drive[dev_path]
    return f"DRIVE{index}"


def update_mapping(drive_id: str, dev_path: Optional[str]) -> None:
    """Record that drive_id corresponds to dev_path (and evict conflicting entries)."""
    if not dev_path:
        return
    # Evict old device mapped to this drive_id
    old_dev = _drive_to_device.get(drive_id)
    if old_dev and old_dev != dev_path:
        _device_to_drive.pop(old_dev, None)
    # Evict any other drive that claimed this dev_path
    other = _device_to_drive.get(dev_path)
    if other and other != drive_id:
        _drive_to_device.pop(other, None)

    _drive_to_device[drive_id] = dev_path
    _device_to_drive[dev_path] = drive_id


def device_for_drive(drive_id: str) -> Optional[str]:
    """Return the last known device path for the given drive_id, if any."""
    return _drive_to_device.get(drive_id)


def forget_drive(drive_id: str) -> None:
    """Remove mappings for a drive that disappeared."""
    old_dev = _drive_to_device.pop(drive_id, None)
    if old_dev:
        _device_to_drive.pop(old_dev, None)


def all_mappings() -> Dict[str, str]:
    """Return a shallow copy of drive→device mappings (for debugging/tests)."""
    return dict(_drive_to_device)
