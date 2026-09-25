"""FastAPI server: streams the Heisenbug investigation to the browser over SSE."""

from __future__ import annotations

import asyncio
import json
import os
import queue
import threading

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from . import config, targets
from .hunt import Heisenbug

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.join(ROOT, "flaky_repo")
FRONTEND = os.path.join(ROOT, "frontend")

app = FastAPI(title="Heisenbug")


@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


@app.get("/api/config")
def get_config():
    return {
        "demo_mode": config.DEMO_MODE,
        "executor": "local-fork" if config.DEMO_MODE else "nebius-sandboxes",
        "models": {"nano": config.MODEL_NANO, "super": config.MODEL_SUPER,
                   "ultra": config.MODEL_ULTRA},
        "fork_points": config.FORK_POINTS,
        "replicas": config.REPLICAS,
    }


@app.get("/api/source")
def source():
    p = os.path.join(REPO, "tests", "test_service.py")
    with open(p) as fh:
        return {"path": "tests/test_service.py", "content": fh.read()}


@app.get("/api/targets")
def list_targets():
    return {"targets": [
        {"key": t.key, "name": t.name, "description": t.description,
         "real_repo": bool(t.git_url), "notes": t.notes}
        for t in targets.TARGETS.values()
    ]}


@app.get("/api/hunt")
async def hunt(target: str = "demo"):
    q: queue.Queue = queue.Queue()

    def emit(event: str, data: dict) -> None:
        q.put((event, data))

    def worker() -> None:
        try:
            Heisenbug(REPO, emit, target_key=target).run()
        except Exception as exc:
            emit("log", {"msg": f"fatal: {exc}", "kind": "bad"})
            emit("done", {"verdicts": [], "error": str(exc)})
        finally:
            q.put(("__eof__", {}))

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        loop = asyncio.get_event_loop()
        while True:
            event, data = await loop.run_in_executor(None, q.get)
            if event == "__eof__":
                break
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
