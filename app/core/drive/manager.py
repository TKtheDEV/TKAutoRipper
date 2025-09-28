# app/core/drive/manager.py

import threading
from typing import Dict, List, Optional
from app.core.drive.drive import Drive
import logging

class DriveTracker:
    def __init__(self):
        self.drives: Dict[str, Drive] = {}
        self.lock = threading.Lock()

    def register_drive(self, path: str, model: str, capability: List[str], disc_label: Optional[str] = None) -> Drive:
        with self.lock:
            drive = Drive(path=path, model=model, capability=capability or ["Unknown"], disc_label=disc_label)
            self.drives[path] = drive
            return drive

    def unregister_drive(self, path: str):
        """Completely removes a drive from tracking."""
        if path in self.drives:
            del self.drives[path]

    def get_drive(self, path: str) -> Optional[Drive]:
        return self.drives.get(path)

    def assign_job(self, path: str, job_id: str) -> bool:
        with self.lock:
            drive = self.drives.get(path)
            if drive and drive.is_available:
                drive.job_id = job_id
                return True
            return False

    def release_drive(self, path: str) -> bool:
        with self.lock:
            drive = self.drives.get(path)
            if drive:
                drive.job_id = None
                return True
            return False

    def blacklist_drive(self, path: str):
        with self.lock:
            if path in self.drives:
                self.drives[path].blacklisted = True

    def unblacklist_drive(self, path: str):
        with self.lock:
            if path in self.drives:
                self.drives[path].blacklisted = False

    def get_all_drives(self) -> List[Drive]:
        return list(self.drives.values())


drive_tracker = DriveTracker()
