# app/core/rippers/audio/windows.py
from typing import List, Tuple
import re

from app.core.integration.freac.windows import run_freac
from app.core.configmanager import config
from app.core.job.job import Job


class FreacProgressAdapter:
    """
    Windows-specific progress adapter for freaccmd.

    freaccmd outputs lines like:
        Ripping track 1 of 12
        Encoding track 1 of 12 (FLAC)
    """

    rip_re = re.compile(r"Ripping track\s+(\d+)\s+of\s+(\d+)", re.I)
    enc_re = re.compile(r"Encoding track\s+(\d+)\s+of\s+(\d+)", re.I)

    def on_start(self, job: Job, cmd: List[str], state: dict) -> None:
        state.clear()

    def _parse(self, line: str, state: dict):
        for regex in (self.rip_re, self.enc_re):
            m = regex.search(line)
            if m:
                cur = int(m.group(1))
                total = int(m.group(2))
                state["total"] = total
                state["current"] = cur
                pct = ((cur - 1) / total) * 100.0
                return pct
        return None

    def on_line(self, line: str, state: dict, job: Job):
        pct = self._parse(line, state)
        return (pct, None)


def rip_audio_cd(job: Job) -> List[Tuple]:
    cd_cfg = config.section("CD")
    cmd = run_freac(
        drive_path=job.drive,
        output_format=cd_cfg["outputformat"],
        config_path=cd_cfg["configpath"],
        additional_options=cd_cfg["additionaloptions"],
        output_dir=job.output_path,
    )
    adapter = FreacProgressAdapter()
    return [(cmd, "Ripping & Encoding Audio CD", True, adapter)]
