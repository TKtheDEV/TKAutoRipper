import socket
import json
from typing import Dict, List

def _query_lact(command: Dict) -> Dict:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect("/run/lactd.sock")
            client.sendall(json.dumps(command).encode() + b"\n")
            response = client.recv(4096)
            return json.loads(response.decode())
    except (FileNotFoundError, ConnectionRefusedError, json.JSONDecodeError):
        return {}

def get_gpu_info() -> List[Dict]:
    gpu_info = []
    device_list = _query_lact({"command": "list_devices"})

    if device_list.get("status") == "ok":
        for device in device_list.get("data", []):
            device_id = device.get("id")
            stats = _query_lact({"command": "device_stats", "args": {"id": device_id}})
            if stats.get("status") == "ok":
                data = stats.get("data", {})
                temps = data.get("temps", {})
                temperature = temps.get("edge", {}).get("current") or temps.get("GPU", {}).get("current", 0.0)

                gpu_info.append({
                    "model": device.get("name", "Unknown"),
                    "total_memory": data.get("vram", {}).get("total", 0),
                    "used_memory": data.get("vram", {}).get("used", 0),
                    "free_memory": data.get("vram", {}).get("total", 0) - data.get("vram", {}).get("used", 0),
                    "percent_memory": round((data.get("vram", {}).get("used", 0) / data.get("vram", {}).get("total", 1)) * 100, 1),
                    "usage": round(data.get("busy_percent", 0.0), 1),
                    "temperature": temperature,
                    "power_draw": round(data.get("power", {}).get("current", 0.0), 1)
                })

    return gpu_info if gpu_info else []
