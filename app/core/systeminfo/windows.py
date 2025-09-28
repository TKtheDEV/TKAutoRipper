import os
import platform
import psutil
import cpuinfo
import time
from typing import Dict, Any

# from ..configmanager import config   # Uncomment if needed
from ..integration.handbrake import windows as handbrake
# from ..integration.lact import windows as lact


def get_system_info() -> Dict[str, Any]:
    return {
        "os_info": _get_os_info(),
        "cpu_info": _get_cpu_info(),
        "memory_info": _get_memory(),
        "storage_info": _get_storage(),
        "gpu_info": _get_gpu_info(),  # Replace with lact.get_gpu_info()
        "hwenc_info": handbrake.get_available_hw_encoders()
    }


def _get_os_info() -> Dict:
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "kernel": (platform.platform()),
        "uptime": _format_uptime(psutil.boot_time())
    }


def _format_uptime(boot_time: float) -> str:
    seconds = int(time.time() - boot_time)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{days}d {hours}h {minutes}m {seconds}s"


def _get_cpu_info() -> Dict:
    temp = "N/A"  # Windows temperature requires WMI or third-party libs

    return {
        "model": cpuinfo.get_cpu_info()["brand_raw"],
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


def _get_storage() -> Dict[str, Dict]:
    storage_info = {}
    for partition in psutil.disk_partitions(all=False):
        if "cdrom" in partition.opts or not partition.fstype:
            continue

        try:
            usage = psutil.disk_usage(partition.mountpoint)
            storage_info[partition.device] = {
                "mountpoint": partition.mountpoint,
                "fstype": partition.fstype,
                "total": usage.total,
                "used": usage.used,
                "available": usage.free,
                "percent": usage.percent
            }
        except PermissionError:
            continue

    return storage_info


def _get_gpu_info() -> Dict:
    return {
        "gpu": "Unknown - replace with lact.get_gpu_info() or WMI-based code"
    }
