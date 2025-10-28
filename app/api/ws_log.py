# app/api/ws_log.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import base64

from app.core.job.tracker import job_tracker
from app.core.configmanager import config

router = APIRouter()
TERMINAL = {"Finished", "Failed", "Cancelled"}

def snapshot(job):
    return {
        "type": "tick",
        "progress": getattr(job, "progress", 0),
        "step_progress": getattr(job, "step_progress", 0),
        "title_progress": getattr(job, "title_progress", 0),
        "status": getattr(job, "status", "Unknown"),
        "step": getattr(job, "step_description", ""),
        "waiting_for_rename": bool(getattr(job, "waiting_for_rename", False)),
        "proposed_output": getattr(job, "proposed_output", None),
        "output_locked": getattr(job, "output_locked", False),
        "output_path": str(getattr(job, "output_path", "")),
    }

def _ws_basic_auth_ok(ws: WebSocket) -> bool:
    auth = ws.headers.get("authorization") or ws.headers.get("Authorization") or ""
    try:
        kind, b64 = auth.split(" ", 1)
        if kind.lower() != "basic":
            return False
        userpass = base64.b64decode(b64.strip()).decode("utf-8", "ignore")
        username, password = userpass.split(":", 1)
        return (
            username == str(config.get("auth", "username")) and
            password == str(config.get("auth", "password"))
        )
    except Exception:
        return False

@router.websocket("/ws/jobs/{job_id}")
async def job_ws(ws: WebSocket, job_id: str):
    # Enforce Basic Auth for WebSocket too (HTTPS assumed)
    if not _ws_basic_auth_ok(ws):
        # 1008: Policy Violation
        await ws.close(code=1008)
        return

    await ws.accept()
    job = job_tracker.get_job(job_id)
    if not job:
        try:
            await ws.send_json({"type": "tick", "status": "Unknown"})
        except Exception:
            pass
        return

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    # Per-connection listener
    def handle_output(line: str):
        data = snapshot(job)
        data.update({"type": "log", "line": line})
        try:
            loop.call_soon_threadsafe(q.put_nowait, data)
        except RuntimeError:
            pass

    if getattr(job, "runner", None):
        job.runner.add_output_listener(handle_output)

    await q.put(snapshot(job))

    async def heartbeat():
        try:
            while True:
                await asyncio.sleep(0.5)
                await q.put(snapshot(job))
                if job.status in TERMINAL:
                    await asyncio.sleep(0.5)
                    break
        except asyncio.CancelledError:
            pass

    hb_task = asyncio.create_task(heartbeat())

    try:
        while True:
            msg = await q.get()
            try:
                await ws.send_json(msg)
            except (WebSocketDisconnect, RuntimeError, Exception):
                break
            if msg.get("type") == "tick" and msg.get("status") in TERMINAL:
                break
    finally:
        hb_task.cancel()
        if getattr(job, "runner", None):
            job.runner.remove_output_listener(handle_output)
