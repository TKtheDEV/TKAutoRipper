# app/core/job/job.py

from dataclasses import dataclass, field
from collections import deque
from typing import Optional, Deque, Dict, Any
from pathlib import Path
import time
import re
import xml.etree.ElementTree as ET


@dataclass
class Job:
    job_id: str
    disc_type: str
    drive: str
    disc_label: str
    temp_path: Path
    output_path: Path              # usually a directory; for ROM jobs we also use override_filename
    steps_total: int = 1

    # runtime status
    start_time: float = field(default_factory=time.time)
    step: int = 1
    step_description: str = "Initializing"
    step_progress: int = 0         # 0..100 for current step
    title_progress: int = 0        # 0..100 for per-title tools (MakeMKV/HandBrake)
    status: str = "Queued"         # Queued | Running | Finished | Failed | Cancelled
    progress: int = 0              # weighted total 0..100

    # output control
    output_locked: bool = False            # set True right before final write step starts
    override_filename: Optional[str] = None  # used by ROM jobs when user supplied final file name

    # rename flow flags (used by UI/WS)
    waiting_for_rename: bool = False
    proposed_output: Optional[str] = None

    # metadata (only imdb_id strictly required per your request)
    imdb_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)  # OMDb payload (optional)
    season: Optional[int] = None                             # Only valid for series

    # logs / runner
    stdout_log: Deque[str] = field(default_factory=lambda: deque(maxlen=200))
    runner: Optional["JobRunner"] = None  # forward reference

    # ---- helpers ----
    def update_step(self, description: str, step: Optional[int] = None):
        if step is not None:
            self.step = step
        self.step_description = description
        self.step_progress = 0
        self.title_progress = 0

    def update_progress(self, progress: int):
        self.progress = max(0, min(100, progress))

    def append_stdout(self, line: str):
        self.stdout_log.append(line)

    def mark_failed(self):
        self.status = "Failed"

    def mark_finished(self):
        self.status = "Finished"

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "disc_type": self.disc_type,
            "drive": self.drive,
            "disc_label": self.disc_label,
            "temp_path": str(self.temp_path),
            "output_path": str(self.output_path),
            "override_filename": self.override_filename,
            "output_locked": self.output_locked,
            "waiting_for_rename": self.waiting_for_rename,
            "proposed_output": self.proposed_output,
            "start_time": self.start_time,
            "steps_total": self.steps_total,
            "step": self.step,
            "step_description": self.step_description,
            "step_progress": self.step_progress,
            "title_progress": self.title_progress,
            "status": self.status,
            "progress": self.progress,
            "stdout_log": list(self.stdout_log),
            "imdb_id": self.imdb_id,
            "metadata": self.metadata,
            "season": self.season,
        }

    # --- Jellyfin/Kodi NFO writer ---
    def write_jellyfin_nfo(self, target_dir: Path) -> None:
        """
        Write a minimal NFO compatible with Jellyfin/Kodi.

        For series: write <series-root>/tvshow.nfo (parent of "Season X")
        For movie:  write <movie-dir>/movie.nfo
        Uses self.metadata and/or self.imdb_id.
        """
        meta = self.metadata or {}
        title = str(meta.get("Title") or "").strip()
        year  = str(meta.get("Year") or "").strip()
        typ   = (meta.get("Type") or "").lower()
        imdb  = self.imdb_id or str(meta.get("imdbID") or "").strip()

        if not title:
            return

        if typ == "series":
            series_root = target_dir
            if series_root.name.lower().startswith("season "):
                series_root = series_root.parent
            root = ET.Element("tvshow")
            ET.SubElement(root, "title").text = title
            if year:
                ET.SubElement(root, "year").text = year
            if imdb:
                uid = ET.SubElement(root, "uniqueid")
                uid.set("type", "imdb")
                uid.set("default", "true")
                uid.text = imdb
            _write_xml(series_root / "tvshow.nfo", root)
        else:
            root = ET.Element("movie")
            ET.SubElement(root, "title").text = title
            if year:
                ET.SubElement(root, "year").text = year
            if imdb:
                uid = ET.SubElement(root, "uniqueid")
                uid.set("type", "imdb")
                uid.set("default", "true")
                uid.text = imdb
            _write_xml(target_dir / "movie.nfo", root)


# ===== helpers =====
def _write_xml(path: Path, root: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        import xml.dom.minidom as minidom
        xml_bytes = ET.tostring(root, encoding="utf-8")
        pretty = minidom.parseString(xml_bytes).toprettyxml(indent="  ")
        path.write_text(pretty, encoding="utf-8")
    except Exception:
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


_safe = re.compile(r'[<>:"/\\|?*\x00-\x1F]+')
def sanitize_folder(name: str) -> str:
    n = _safe.sub("", name).strip()
    n = re.sub(r"\s+", " ", n)
    return n
