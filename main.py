from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from app.core.templates import templates
from fastapi.requests import Request
import uvicorn
import subprocess
import logging
from pathlib import Path

from app.api import drives
from app.api import jobs
from app.api import settings
from app.api import systeminfo
from app.api import ws_log
from app.core.auth import verify_web_auth
from app.core.discdetection import linux as discdetection
from app.core.drive.detector import linux as drive_detector
import threading

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Mount static assets and templates
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

# Secure dashboard
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_web_auth)])
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


def generate_ssl_cert(cert_file: Path, key_file: Path):
    logging.info("🔑 Generating self-signed SSL certificate and key...")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-days", "3650",
            "-nodes", "-keyout", str(key_file), "-out", str(cert_file),
            "-subj", "/C=TK/ST=Dev/L=Localhost/O=TKAutoRipper/CN=localhost"
        ],
        check=True
    )
    logging.info("✅ SSL certificate generated.")


# Register API routes
app.include_router(drives.router)
app.include_router(jobs.router)
app.include_router(settings.router)
app.include_router(systeminfo.router)
app.include_router(ws_log.router)

if __name__ == "__main__":
    cert_dir = Path("~/TKAutoRipper/config").expanduser()
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    cert_dir.mkdir(parents=True, exist_ok=True)

    if not cert_file.exists() or not key_file.exists():
        generate_ssl_cert(cert_file, key_file)

    threading.Thread(target=drive_detector.poll_for_drives, daemon=True).start()
    threading.Thread(target=discdetection.monitor_cdrom, daemon=True).start()

    uvicorn.run(
        "main:app",
        host="::",
        port=8000,
        reload=False,
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file)
    )
