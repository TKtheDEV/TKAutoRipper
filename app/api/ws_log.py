from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio, functools
from app.core.job.tracker import job_tracker

router = APIRouter()

@router.websocket("/ws/jobs/{job_id}")
async def job_ws(ws: WebSocket, job_id: str):
    await ws.accept()
    job = job_tracker.get_job(job_id)                 
    if not job or not job.runner:
        return await ws.close()

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    def handle_output(line: str):
        loop.call_soon_threadsafe(q.put_nowait, {     # ✅
            "type": "log",
            "line": line,
            "progress": job.progress,
            "status": job.status,
            "step": job.step_description,
        })

    job.runner.on_output = handle_output

    try:
        while True:
            msg = await q.get()
            await ws.send_json(msg)
    except WebSocketDisconnect:
        pass