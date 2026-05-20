"""FastAPI app for the Whisper-Pipeline WebGUI.

Single-User, localhost only. No auth, no CSRF.
"""
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pipeline_core import PipelineConfig, build_command, resolve_audio_path
from .probe import audio_probe
from .runner import registry, spawn_pipeline, StreamEvent
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


class RunRequest(BaseModel):
    audio: str
    viz: str
    language: str
    model: str
    diarize: str
    episode: str
    show_name: str
    skip_transcribe: bool
    skip_meta: bool
    skip_render: bool
    skip_upload: bool


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/api/audio/probe")
async def api_audio_probe(req: AudioProbeRequest):
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


@app.post("/api/runs")
async def api_create_run(req: RunRequest):
    if registry.current is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "slot_busy",
                "stem": registry.current.stem,
                "kind": registry.current.kind,
            },
        )

    audio_path = resolve_audio_path(req.audio, REPO_ROOT)
    stem = audio_path.stem
    output_dir = OUTPUT_ROOT / stem
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_file = output_dir / f"run-{ts}.log"

    cfg = PipelineConfig(
        audio=str(audio_path), viz=req.viz, language=req.language, model=req.model,
        diarize=req.diarize, episode=req.episode, show_name=req.show_name,
        skip_transcribe=req.skip_transcribe, skip_meta=req.skip_meta,
        skip_render=req.skip_render, skip_upload=req.skip_upload,
    )
    cmd = build_command(cfg, REPO_ROOT)

    spawn_pipeline(
        cmd=cmd, stem=stem, audio_path=audio_path,
        output_dir=output_dir, log_file=log_file, registry=registry,
    )
    return RedirectResponse(url=f"/runs/{stem}", status_code=303)


@app.get("/runs/{stem}/stream")
async def runs_stream(stem: str):
    """SSE stream of log events for the active run (if any).

    Returns a done event immediately if no active job for this stem — so clients
    can safely subscribe to historical stems without hanging.
    """
    job = registry.current
    if job is None or job.stem != stem:
        async def _empty():
            yield {"event": "done", "data": json.dumps({"exit_code": 0, "kind": "static"})}
        return EventSourceResponse(_empty())

    async def event_gen():
        while True:
            assert job.queue is not None
            event: StreamEvent = await job.queue.get()
            yield {
                "id": str(event.seq),
                "event": event.type,
                "data": json.dumps(event.data),
            }
            if event.type == "done":
                break

    return EventSourceResponse(event_gen())


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"page_mood": "neutral"},
    )
