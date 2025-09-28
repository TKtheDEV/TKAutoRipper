# app/core/rippers/audio/linux.py
from typing import List, Tuple

from app.core.integration.abcde.linux import run_abcde
from app.core.configmanager import config
from app.core.job.job import Job


def rip_audio_cd(job: Job) -> List[Tuple[List[str], str, bool]]:
    """
    Audio CD – one step with abcde; drive can be released immediately
    afterwards (abcde ejects anyway).
    """
    cd_cfg = config.section("CD")
    cmd = run_abcde(
        drive_path=job.drive,
        output_format=cd_cfg["outputformat"],
        config_path=cd_cfg["configpath"],
        additional_options=cd_cfg["additionaloptions"],
    )
    return [(cmd, "Ripping & Encoding Audio CD", True)]
