# app/core/drive/drive.py

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class Drive:
    path: str
    model: str
    capability: List[str]
    job_id: Optional[str] = None
    disc_label: Optional[str] = None
    blacklisted: bool = False

    @property
    def is_available(self):
        return self.job_id is None and not self.blacklisted
