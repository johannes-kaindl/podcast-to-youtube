"""FastAPI app for the Whisper-Pipeline WebGUI.

Single-User, localhost only. No auth, no CSRF.
"""
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .probe import audio_probe
from .runs import list_runs, filter_runs

REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_ROOT = REPO_ROOT / "output"

app = FastAPI(title="Whisper-Pipeline WebGUI")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


class AudioProbeRequest(BaseModel):
    path: str


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/api/audio/probe")
async def api_audio_probe(req: AudioProbeRequest):
    from pipeline_core import resolve_audio_path
    audio_path = resolve_audio_path(req.path, REPO_ROOT)
    return audio_probe(audio_path, OUTPUT_ROOT)


@app.get("/runs")
async def runs_view(request: Request, filter: str = "all"):
    all_runs = list_runs(OUTPUT_ROOT)
    runs = filter_runs(all_runs, filter)
    return templates.TemplateResponse(
        request,
        "runs.html",
        {
            "runs": runs,
            "active_filter": filter,
            "total_count": len(all_runs),
            "page_mood": "neutral",
        },
    )


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"page_mood": "neutral"},
    )
