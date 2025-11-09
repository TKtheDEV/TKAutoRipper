# main.py
from fastapi import FastAPI, Depends
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
import uvicorn
import subprocess
import logging
from pathlib import Path
import threading

from app.core.templates import templates
from app.api import drives
from app.api import jobs
from app.api import settings
from app.api import systeminfo
from app.api import ws_log
from app.core.auth import verify_web_auth
import app.core.discdetection as discdetection
import app.core.drive.detector as drive_detector

app = FastAPI()
logging.basicConfig(level=logging.INFO)

# Mount static assets and templates
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")

# Secure dashboard
@app.get("/", response_class=HTMLResponse, dependencies=[Depends(verify_web_auth)])
def dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


def generate_ssl_cert(cert_file: Path, key_file: Path):
    """
    Generate a self-signed certificate with proper SANs for localhost / IPv6.
    This is REQUIRED — the server will not start without TLS.
    """
    logging.info("🔑 Generating self-signed SSL certificate and key (with SANs)…")
    # Modern OpenSSL supports -addext for SAN; this avoids needing a temp config file.
    cmd = [
        "openssl",
        "req", "-x509",
        "-newkey", "rsa:2048",
        "-days", "3650",
        "-nodes",
        "-keyout", str(key_file),
        "-out", str(cert_file),
        "-subj", "/C=TK/ST=Dev/L=Localhost/O=TKAutoRipper/CN=localhost",
        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:::1",
    ]
    subprocess.run(cmd, check=True)
    logging.info("✅ SSL certificate generated.")


# Register API routes
app.include_router(drives.router)
app.include_router(jobs.router)
app.include_router(settings.router)
app.include_router(systeminfo.router)
app.include_router(ws_log.router)

if __name__ == "__main__":
    # Enforce TLS and IPv6
    cert_dir = Path("~/TKAutoRipper/config").expanduser()
    cert_file = cert_dir / "cert.pem"
    key_file = cert_dir / "key.pem"
    cert_dir.mkdir(parents=True, exist_ok=True)

    if not cert_file.exists() or not key_file.exists():
        # If we cannot create a cert, we fail fast (HTTPS-only requirement).
        generate_ssl_cert(cert_file, key_file)

    # Background watchers (Linux MVP)
    threading.Thread(target=drive_detector.poll_for_drives, daemon=True).start()
    threading.Thread(target=discdetection.monitor_cdrom, daemon=True).start()

    # Bind to IPv6 (“::”) and use TLS only
    uvicorn.run(
        "main:app",
        host="::",
        port=8000,
        reload=False,
        ssl_certfile=str(cert_file),
        ssl_keyfile=str(key_file),
    )
