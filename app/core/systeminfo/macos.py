import platform
import psutil
import re
import subprocess
import time
from typing import Dict, Any
from ..configmanager import config
from ..integration.handbrake import macos as handbrake

def get_system_info() -> Dict[str, Any]:
    return {
        "os_info": _get_os_info(),
        "cpu_info": _get_cpu_info(),
        "memory_info": _get_memory(),
        "storage_info": _get_storage(),
        "gpu_info": "not available",
        "hwenc_info": handbrake.get_available_hw_encoders(),
    }

def _get_os_info() -> Dict:
        output = subprocess.check_output(["sw_vers"]).decode()
        lines = {}
        for line in output.strip().split("\n"):
            key_value = re.split(r":\s+", line, maxsplit=1)
            if len(key_value) == 2:
                key, value = key_value
                lines[key.strip()] = value.strip()
        
        return {
            "os": lines.get("ProductName", "N/A"),
            "os_version": lines.get("ProductVersion", "N/A"),
            "kernel": platform.release(),
            "uptime": _format_uptime(psutil.boot_time())
        }


def _format_uptime(boot_time: float) -> str:
    seconds = int(time.time() - boot_time)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def _get_cpu_info() -> Dict:
    try:
        model = subprocess.check_output(["sysctl", "-n", "machdep.cpu.brand_string"]).decode().strip()
    except FileNotFoundError:
        model = platform.processor()
 
    return {
        "model": model,
        "cores": psutil.cpu_count(logical=False),
        "threads": psutil.cpu_count(logical=True),
        "frequency": int(psutil.cpu_freq().current),
        "usage": psutil.cpu_percent(interval=1),
        "temperature": "N/A"
    }


def _get_memory() -> Dict:
    mem = psutil.virtual_memory()
    return {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": mem.percent
    }


def _get_storage() -> Dict:
    disk = psutil.disk_usage('/')
    return {
        "total": disk.total,
        "used": disk.used,
        "available": disk.free,
        "percent": disk.percent
    }
