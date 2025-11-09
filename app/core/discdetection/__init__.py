# app/core/discdetection/__init__.py
import platform

system = platform.system().lower()

if system == "linux":
    from .linux import monitor_cdrom
elif system == "darwin":
    from .macos import monitor_cdrom
elif system == "windows":
    from .windows import monitor_cdrom
else:
    raise NotImplementedError(f"SystemInfo not supported on platform: {system}")
