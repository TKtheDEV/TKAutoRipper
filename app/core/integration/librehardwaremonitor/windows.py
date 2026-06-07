from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def _candidate_dll_paths() -> List[Path]:
    candidates: List[Path] = []

    env_path = os.environ.get("TKAR_LIBREHARDWAREMONITOR_DLL")
    if env_path:
        candidates.append(Path(env_path))

    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(env_name)
        if not base:
            continue

        root = Path(base)
        candidates.extend(
            [
                root / "LibreHardwareMonitor" / "LibreHardwareMonitorLib.dll",
                root / "Libre Hardware Monitor" / "LibreHardwareMonitorLib.dll",
                root / "Programs" / "LibreHardwareMonitor" / "LibreHardwareMonitorLib.dll",
                root / "Programs" / "Libre Hardware Monitor" / "LibreHardwareMonitorLib.dll",
            ]
        )

    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        winget_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            candidates.extend(
                winget_root.glob(
                    "LibreHardwareMonitor.LibreHardwareMonitor_*/*/LibreHardwareMonitorLib.dll"
                )
            )
            candidates.extend(
                winget_root.glob(
                    "LibreHardwareMonitor.LibreHardwareMonitor_*/LibreHardwareMonitorLib.dll"
                )
            )

    deduped: List[Path] = []
    seen = set()
    for path in candidates:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            deduped.append(path)
    return deduped


def _find_lhm_dll() -> Optional[Path]:
    for candidate in _candidate_dll_paths():
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


def get_gpu_info(timeout: float = 4.0) -> List[Dict[str, Any]]:
    dll_path = _find_lhm_dll()
    if not dll_path:
        return []

    script = Path(__file__).with_name("windows_lhm_gpu.ps1")
    if not script.exists():
        return []

    try:
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-DllPath",
                str(dll_path),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []

    if not isinstance(payload, list):
        return []

    return [gpu for gpu in payload if isinstance(gpu, dict)]
