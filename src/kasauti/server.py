"""FastAPI app — serves the Kasauti web UI and a streaming check endpoint.

POST /api/check streams NDJSON: progress events as the pipeline works, then the
full report. The UI narrates the agent's work live — no spinners of mystery.
"""
from __future__ import annotations

import asyncio
import json
import queue
import threading
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .llm import LLM
from .pipeline import check
from .serp import KasautiError, SerpSearcher

load_dotenv()

app = FastAPI(title="Kasauti", version="0.1.0")

_WEBUI_DIR = Path(__file__).parent / "webui"
_EXAMPLES_FILE = Path(__file__).parent / "examples" / "examples.json"


class CheckRequest(BaseModel):
    text: str = ""
    image_url: Optional[str] = None
    reply_lang: Optional[str] = None
    offline: bool = False


@app.get("/api/health")
def health() -> dict[str, Any]:
    llm = LLM()
    try:
        searcher = SerpSearcher()
        serp_ok, offline = True, searcher.offline
    except KasautiError:
        serp_ok, offline = False, False
    return {
        "serpapi": serp_ok,
        "offline": offline,
        "llm": llm.provider,
        "mode": "LLM-assisted" if llm.available else "rule-based",
    }


@app.get("/api/examples")
def examples() -> JSONResponse:
    if _EXAMPLES_FILE.exists():
        try:
            return JSONResponse(json.loads(_EXAMPLES_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return JSONResponse([])


@app.post("/api/check")
async def api_check(req: CheckRequest) -> StreamingResponse:
    q: "queue.Queue[Optional[dict[str, Any]]]" = queue.Queue()

    def on_event(stage: str, detail: str) -> None:
        q.put({"type": "event", "stage": stage, "detail": detail})

    def worker() -> None:
        try:
            searcher = SerpSearcher(offline=True if req.offline else None)
            report = check(
                req.text,
                image_url=(req.image_url or None),
                searcher=searcher,
                reply_language=req.reply_lang,
                on_event=on_event,
            )
            q.put({"type": "report", "report": json.loads(report.model_dump_json())})
        except (KasautiError, ValueError) as exc:
            q.put({"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 - surface anything to the UI
            q.put({"type": "error", "message": f"Unexpected error: {exc}"})
        finally:
            q.put(None)

    threading.Thread(target=worker, daemon=True).start()
    loop = asyncio.get_running_loop()

    async def stream():
        while True:
            item = await loop.run_in_executor(None, q.get)
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


app.mount("/", StaticFiles(directory=str(_WEBUI_DIR), html=True), name="webui")
