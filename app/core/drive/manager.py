# app/core/drive/manager.py

import threading
from typing import Dict, List, Optional
from app.core.drive.drive import Drive
import logging

class DriveTracker:
    def __init__(self):
        self.drives: Dict[str, Drive] = {}
        self.lock = threading.Lock()

    def _resolve_key(self, identifier: Optional[str]) -> Optional[str]:
        """
        Return the internal dict key for a given drive identifier.
        Accepts either a logical id (drive.id) or the OS path.
        Caller must hold self.lock.
        """
        if identifier is None:
            return None

        if identifier in self.drives:
            return identifier

        for key, drive in self.drives.items():
            if drive.id == identifier or drive.path == identifier:
                return key

        return None

    def register_drive(
        self,
        path: Optional[str],
        model: str,
        capability: List[str],
        disc_label: Optional[str] = None,
        drive_id: Optional[str] = None,
    ) -> Drive:
        with self.lock:
            # Prefer a provided drive_id (used on macOS), otherwise fall back to path
            key = (
                self._resolve_key(drive_id)
                or self._resolve_key(path)
                or drive_id
                or path
            )

            if key is None:
                raise ValueError("drive_id or path is required to register a drive")

            drive = self.drives.get(key)
            if drive:
                drive.id = drive_id or drive.id or key
                drive.path = path
                drive.model = model
                drive.capability = capability
                if disc_label is not None:
                    drive.disc_label = disc_label
            else:
                drive = Drive(
                    id=drive_id or key,
                    path=path,
                    model=model,
                    capability=capability,
                    disc_label=disc_label,
                )
                self.drives[key] = drive

            return drive

    def unregister_drive(self, path: str):
        """Completely removes a drive from tracking."""
        with self.lock:
            key = self._resolve_key(path)
            if key in self.drives:
                del self.drives[key]

    def get_drive(self, path: str) -> Optional[Drive]:
        with self.lock:
            key = self._resolve_key(path)
            return self.drives.get(key) if key else None

    def assign_job(self, path: str, job_id: str) -> bool:
        with self.lock:
            key = self._resolve_key(path)
            drive = self.drives.get(key) if key else None
            if drive and drive.is_available:
                drive.job_id = job_id
                return True
            return False

    def release_drive(self, path: str) -> bool:
        with self.lock:
            key = self._resolve_key(path)
            drive = self.drives.get(key) if key else None
            if drive:
                drive.job_id = None
                return True
            return False

    def blacklist_drive(self, path: str):
        with self.lock:
            key = self._resolve_key(path)
            if key in self.drives:
                self.drives[key].blacklisted = True

    def unblacklist_drive(self, path: str):
        with self.lock:
            key = self._resolve_key(path)
            if key in self.drives:
                self.drives[key].blacklisted = False

    def get_all_drives(self) -> List[Drive]:
        with self.lock:
            return list(self.drives.values())


drive_tracker = DriveTracker()
