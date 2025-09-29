# app/api/ws_log.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from app.core.job.tracker import job_tracker

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

@router.websocket("/ws/jobs/{job_id}")
async def job_ws(ws: WebSocket, job_id: str):
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
