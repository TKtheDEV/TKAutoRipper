import platform
import psutil
import time
from typing import Dict, Any

from ..configmanager import config
from ..integration.handbrake import linux as handbrake
from ..integration.lact import linux as lact


def get_system_info() -> Dict[str, Any]:
    return {
        "os_info": _get_os_info(),
        "cpu_info": _get_cpu_info(),
        "memory_info": _get_memory(),
        "storage_info": _get_storage(),
        "gpu_info": lact.get_gpu_info(),
        "hwenc_info": handbrake.get_available_hw_encoders()
    }


def _get_os_info() -> Dict:
    try:
        with open("/etc/os-release", "r") as f:
            os_release = f.readlines()
            os_version = next((line.split("=")[1].strip().strip('"') for line in os_release if line.startswith("VERSION=")), platform.version())
    except FileNotFoundError:
        os_version = platform.version()

    return {
        "os": platform.system(),
        "os_version": os_version,
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
        with open("/proc/cpuinfo", "r") as f:
            model = next((line.split(": ")[1].strip() for line in f if line.startswith("model name")), platform.processor())
    except FileNotFoundError:
        model = platform.processor()

    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read().strip()) / 1000.0
    except:
        temp = "N/A"

    return {
        "model": model,
        "cores": psutil.cpu_count(logical=False),
        "threads": psutil.cpu_count(logical=True),
        "frequency": int(psutil.cpu_freq().current),
        "usage": psutil.cpu_percent(interval=1),
        "temperature": temp
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
