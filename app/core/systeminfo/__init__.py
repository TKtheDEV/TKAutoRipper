import platform

system = platform.system().lower()

if system == "linux":
    from .linux import get_system_info
elif system == "darwin":
    from .mac import get_system_info
elif system == "windows":
    from .windows import get_system_info
else:
    raise NotImplementedError(f"SystemInfo not supported on platform: {system}")
