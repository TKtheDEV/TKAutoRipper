# app/core/drive/detector/__init__.py
import platform

system = platform.system().lower()

if system == "linux":
    from .linux import _get_drive_model
    from .linux import poll_for_drives
elif system == "darwin":
    from .macos import poll_for_drives
elif system == "windows":
    from .windows import _get_drive_model
    from .windows import poll_for_drives
else:
    raise NotImplementedError(f"SystemInfo not supported on platform: {system}")
