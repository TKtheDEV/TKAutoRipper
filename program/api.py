from datetime import datetime
from fastapi import BackgroundTasks, Body, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import GPUtil
from pydantic import BaseModel
import logging
import os
import psutil
import subprocess

from cd import CDRipper
from detect_drives import get_connected_drives
from job_tracker import job_tracker
from utils import ConfigLoader

app = FastAPI()
config_loader = ConfigLoader(config_file="~/TKAutoRipper/config/TKAutoRipper.conf")
config = config_loader.get_general_settings()

# Mount static files for serving CSS, JS
app.mount("/static", StaticFiles(directory="static"), name="static")

# Use templates for HTML rendering
templates = Jinja2Templates(directory="templates")

class LicenseCheckResponse(BaseModel):
    is_valid: bool
    message: str

class ConfigUpdateRequest(BaseModel):
    section: str
    option: str
    value: str

def read_cpu_temp():
    """Read CPU temperature from /sys/class/thermal/thermal_zone0/temp"""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = int(f.read()) // 1000
            return f"{temp}°C"
    except FileNotFoundError:
        return "N/A"

def format_uptime():
    """Convert system uptime into a human-readable format"""
    boot_time = psutil.boot_time()
    current_time = datetime.now().timestamp()
    uptime_seconds = current_time - boot_time

    # Convert uptime from seconds to days, hours, minutes
    days = int(uptime_seconds // (24 * 3600))
    hours = int((uptime_seconds % (24 * 3600)) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    return f"{days}d {hours}h {minutes}m"

def get_os_info():
    """Get OS information from /etc/os-release"""
    os_info = {}
    try:
        with open("/etc/os-release", "r") as f:
            for line in f:
                key, value = line.strip().split("=")
                os_info[key] = value.strip('"')
    except FileNotFoundError:
        os_info["NAME"] = "Unknown OS"
        os_info["VERSION"] = ""
    return f"{os_info.get('NAME', 'Unknown OS')} {os_info.get('VERSION', '')}"

@app.get("/system-info")
async def system_info():
    # Get OS information from /etc/os-release
    os_info = get_os_info()
    # System Information (RAM, Disk, GPU, etc.)
    ram_info = psutil.virtual_memory()
    disk_info = psutil.disk_usage('/')

    # Format the data for display like XGB/YGB
    disk_total_gb = disk_info.total / (1024 ** 3)  # Total disk space in GB
    disk_free_gb = disk_info.free / (1024 ** 3)    # Free disk space in GB
    ram_total_gb = ram_info.total / (1024 ** 3)    # Total RAM in GB
    ram_available_gb = ram_info.available / (1024 ** 3)  # Available RAM in GB
    # Read CPU temperature from thermal zone
    cpu_temp = read_cpu_temp()
    # Format uptime
    formatted_uptime = format_uptime()

    system_data = {
        "OS": os_info,
        "Kernel": os.uname().release,
        "Disk Available": f"{disk_free_gb:.2f}GB/{disk_total_gb:.2f}GB",  # Disk usage as XGB/YGB
        "RAM Available": f"{ram_available_gb:.2f}GB/{ram_total_gb:.2f}GB",  # RAM usage as XGB/YGB
        "Uptime": formatted_uptime,  # Human-readable uptime
        "CPU Temp": cpu_temp,  # CPU temperature from thermal zone
        "GPU Temp": GPUtil.getGPUs()[0].temperature if GPUtil.getGPUs() else "N/A"
    }

    # GPU Information
    gpu_info = []
    for gpu in GPUtil.getGPUs():
        gpu_info.append({
            "name": gpu.name,
            "temperature": gpu.temperature,
            "utilization": gpu.load * 100,
            "memoryTotal": gpu.memoryTotal,
            "memoryUsed": gpu.memoryUsed,
        })

    system_data['GPUs'] = gpu_info
    return system_data

@app.get("/drives")
async def get_drives():
    """Get drive information and job status for each detected drive."""
    drives = get_connected_drives()
    drive_status = []

    for drive in drives:
        if drive in job_tracker.get_jobs():
            job_info = job_tracker.get_jobs()[drive]
            drive_status.append({
                "drive": drive,
                "status": job_info['status'],
                "job_id": job_info['job_id'],
                "start_time": job_info['start_time']
            })
        else:
            drive_status.append({
                "drive": drive,
                "status": "Idle",
                "job_id": None,
                "start_time": None
            })

    return drive_status

@app.get("/jobs")
async def get_jobs():
    return job_tracker.get_jobs()

@app.post("/start-job/{drive}")
async def start_job(drive: str):
    job_id = len(job_tracker.get_jobs()) + 1
    job_tracker.add_job(drive, job_id, "Ripping in progress")
    return {"status": "Ripping started", "job_id": job_id}

@app.post("/stop-job/{drive}")
async def stop_job(drive: str):
    job_tracker.update_job(drive, "Stopped")
    return {"status": "Ripping stopped", "drive": drive}

@app.post("/eject/{drive}")
async def eject_drive(drive: str):
    drive_path = f"/dev/{drive}"  # Construct the full path to the drive
    try:
        subprocess.run(["eject", drive_path], check=True)
        return {"status": "Ejected", "drive": drive}
    except subprocess.CalledProcessError as e:
        logging.error("Failed to eject drive %s: %s", drive, e.stderr.decode())
        raise HTTPException(status_code=500, detail=f"Failed to eject drive {drive}")

@app.post("/rip-cd/{drive}")
async def rip_cd(drive: str, background_tasks: BackgroundTasks):
    job_id = len(job_tracker.get_jobs()) + 1
    job_tracker.add_job(drive, job_id, "Ripping CD in progress")
    # Start the ripping process in the background
    background_tasks.add_task(run_cd_ripping, drive, job_tracker)
    return {"status": "Ripping CD started", "job_id": job_id}

def run_cd_ripping(drive, job_tracker):
    """Run the CD ripping process in the background."""
    ripper = CDRipper(config_file="~/TKAutoRipper/config/TKAutoRipper.conf", drive=drive, job_tracker=job_tracker)
    result = ripper.rip_cd()
    if result:
        job_tracker.update_job(drive, "Ripping CD completed")
    else:
        job_tracker.update_job(drive, "Ripping CD failed")

@app.get("/drive-details/{drive}", response_class=HTMLResponse)
async def drive_details(request: Request, drive: str):
    """Serve the detailed status page for a specific drive."""
    job = job_tracker.get_jobs().get(drive, None)
    drive_info = {
        "drive": drive,
        "status": job['status'] if job else "Idle",
        "job_id": job['job_id'] if job else "N/A",
        "start_time": job['start_time'] if job else "N/A",
        "logs": job.get('logs', []) if job else [],  # Get logs from job tracker
    }
    return templates.TemplateResponse("drive_details.html", {"request": request, "drive_info": drive_info})

@app.get("/api/license-check", response_model=LicenseCheckResponse)
async def check_license():
    license_key = config['MakeMKVLicenseKey']
    if not license_key:
        raise HTTPException(status_code=400, detail="License key not found in configuration.")
    
    try:
        cmd = f"makemkvcon reg {license_key}"
        subprocess.run(cmd, shell=True, check=True, capture_output=True)
        return LicenseCheckResponse(is_valid=True, message="License key is valid.")
    except subprocess.CalledProcessError as e:
        logging.error("Invalid MakeMKV license key: %s", e.stderr.decode())
        return LicenseCheckResponse(is_valid=False, message="Invalid MakeMKV license key.")

@app.get("/api/settings")
async def get_settings():
    config = config_loader._load_config(config_loader.config_file)
    settings = {section: dict(config.items(section)) for section in config.sections()}
    return settings

@app.put("/api/settings", response_model=ConfigUpdateRequest)
async def update_setting(update_request: ConfigUpdateRequest):
    config = config_loader._load_config(config_loader.config_file)

    if not config.has_section(update_request.section):
        raise HTTPException(status_code=404, detail="Section not found in configuration.")
    
    if not config.has_option(update_request.section, update_request.option):
        raise HTTPException(status_code=404, detail="Option not found in configuration.")

    config.set(update_request.section, update_request.option, update_request.value)
    config_loader.save()
    return update_request

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    return templates.TemplateResponse("settings.html", {"request": request})

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
