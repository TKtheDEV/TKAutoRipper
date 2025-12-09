# app/core/rippers/audio/linux.py
from typing import List, Tuple
import re

from app.core.integration.abcde.macos import run_abcde
from app.core.configmanager import config
from app.core.job.job import Job


class AbcdeProgressAdapter:
    """
    Linux-specific progress adapter for abcde/cdparanoia.

    Looks at lines like:
      - "Grabbing entire CD - tracks:  01 02 03 ..."
      - "Grabbing track 01: Tender..."
    and approximates progress as (tracks_finished / total_tracks).
    """

    _tracks_re = re.compile(r"Grabbing entire CD - tracks:\s+([\d ]+)")
    _track_re = re.compile(r"Grabbing track\s+(\d+)\s*:")

    def on_start(self, job: Job, cmd: List[str], state: dict) -> None:
        state.clear()  # total_tracks, current_track

    def on_line(self, line: str, state: dict, job: Job):
        total = state.get("total_tracks")

        m_all = self._tracks_re.search(line)
        if m_all:
            nums = [int(x) for x in m_all.group(1).split() if x.isdigit()]
            if nums:
                total = max(nums)
                state["total_tracks"] = total

        m_track = self._track_re.search(line)
        if m_track and total:
            cur = int(m_track.group(1))
            state["current_track"] = cur
            done_tracks = max(0, cur - 1)
            pct = (done_tracks / total) * 100.0
            return (pct, None)

        return (None, None)


def rip_audio_cd(job: Job) -> List[Tuple]:
    """
    Audio CD – one step with abcde; drive can be released immediately
    afterwards (abcde ejects anyway).

    Returns a step tuple with an AbcdeProgressAdapter so the runner
    can stay OS-agnostic.
    """
    cd_cfg = config.section("CD")
    cmd = run_abcde(
        drive_path=job.drive,
        output_format=cd_cfg["outputformat"],
        config_path=cd_cfg["configpath"],
        additional_options=cd_cfg["additionaloptions"],
    )
    adapter = AbcdeProgressAdapter()
    return [(cmd, "Ripping & Encoding Audio CD", True, adapter)]
