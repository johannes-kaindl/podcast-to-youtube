"""FastAPI app for the Whisper-Pipeline WebGUI.

Single-User, localhost only. No auth, no CSRF.
"""
import json
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pipeline_core import PipelineConfig, build_command, resolve_audio_path
from .probe import audio_probe
from .runner import registry, spawn_pipeline, spawn_upload, StreamEvent, latest_logfile, replay_logfile
from .runs import list_runs, filter_runs

REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_ROOT = REPO_ROOT / "output"

app = FastAPI(title="Whisper-Pipeline WebGUI")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


def _load_state(stem: str) -> dict:
    state_file = OUTPUT_ROOT / stem / "run-state.json"
    default = {
        "phases": {p: {"status": "pending"}
                   for p in ("transcribe", "meta", "render", "upload")}
    }
    if not state_file.exists():
        return default
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


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


@app.get("/runs/{stem}", response_class=HTMLResponse)
async def runs_detail(stem: str, request: Request):
    state_file = OUTPUT_ROOT / stem / "run-state.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    state = _load_state(stem)
    phases = state.get("phases", {})

    # Variant precedence: aborted > done > ready-to-upload > running
    if any(phases.get(p, {}).get("status") == "aborted"
           for p in ("transcribe", "meta", "render", "upload")):
        variant = "aborted"
        page_mood = "error"
    elif phases.get("upload", {}).get("status") == "done":
        variant = "done"
        page_mood = "success"
    elif phases.get("render", {}).get("status") == "done":
        variant = "ready-to-upload"
        page_mood = "neutral"
    elif any(phases.get(p, {}).get("status") == "running"
             for p in ("transcribe", "meta", "render", "upload")):
        variant = "running"
        page_mood = "neutral"
    else:
        # Pending phases without a running process — partial-resume / warning
        variant = "running"
        page_mood = "warning"

    active = registry.current is not None and registry.current.stem == stem

    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "stem": stem,
            "state": state,
            "phases": phases,
            "variant": variant,
            "page_mood": page_mood,
            "active": active,
        },
    )


@app.get("/runs/{stem}/stream")
async def runs_stream(stem: str, request: Request):
    """SSE stream — live from active job, or replay from persisted logfile."""
    last_id_str = request.headers.get("Last-Event-ID", "0")
    try:
        last_seq = int(last_id_str)
    except ValueError:
        last_seq = 0

    job = registry.current

    async def replay_then_done():
        output_dir = OUTPUT_ROOT / stem
        log_file = latest_logfile(output_dir)
        if log_file is not None:
            for event in replay_logfile(log_file, start_seq=last_seq):
                yield {
                    "id": str(event.seq),
                    "event": event.type,
                    "data": json.dumps(event.data),
                }
        yield {
            "event": "done",
            "data": json.dumps({"exit_code": 0, "kind": "replay"}),
        }

    if job is None or job.stem != stem:
        return EventSourceResponse(replay_then_done())

    async def live_then_drain():
        # 1) Replay from the logfile up to current job.seq (catch up after reconnect)
        log_file = job.log_file
        if log_file.exists():
            for event in replay_logfile(log_file, start_seq=last_seq):
                if event.seq > job.seq:
                    break
                yield {
                    "id": str(event.seq),
                    "event": event.type,
                    "data": json.dumps(event.data),
                }
        # 2) Drain the live queue
        while True:
            assert job.queue is not None
            event: StreamEvent = await job.queue.get()
            if event.seq <= last_seq:
                continue
            yield {
                "id": str(event.seq),
                "event": event.type,
                "data": json.dumps(event.data),
            }
            if event.type == "done":
                break

    return EventSourceResponse(live_then_drain())


@app.get("/runs/{stem}/phases", response_class=HTMLResponse)
async def runs_phases_fragment(stem: str, request: Request):
    state = _load_state(stem)
    return templates.TemplateResponse(
        request,
        "_partials/phase_indicator.html",
        {"phases": state.get("phases", {})},
    )


@app.get("/runs/{stem}/resume-banner", response_class=HTMLResponse)
async def runs_resume_banner(stem: str, request: Request):
    state = _load_state(stem)
    phases = state.get("phases", {})
    aborted_phase = next(
        (p for p in ("transcribe", "meta", "render", "upload")
         if phases.get(p, {}).get("status") == "aborted"),
        None,
    )
    if aborted_phase:
        variant = "aborted"
    elif all(phases.get(p, {}).get("status") in ("done", "skipped")
             for p in ("transcribe", "meta", "render", "upload")):
        variant = "complete"
    else:
        variant = "inprogress"
    return templates.TemplateResponse(
        request,
        "_partials/resume_banner.html",
        {"phases": phases, "variant": variant, "aborted_phase": aborted_phase},
    )


@app.get("/runs/{stem}/progress", response_class=HTMLResponse)
async def runs_progress_fragment(stem: str, request: Request,
                                  value: float = 0, label: str = ""):
    return templates.TemplateResponse(
        request,
        "_partials/progress_bar.html",
        {"progress": {"value": value, "label": label}},
    )


def _find_mp4(stem: str) -> Path | None:
    output_dir = OUTPUT_ROOT / stem
    if not output_dir.exists():
        return None
    mp4s = sorted(output_dir.glob(f"{stem}-*.mp4"))
    if not mp4s:
        mp4s = sorted(output_dir.glob("*.mp4"))
    return mp4s[-1] if mp4s else None


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    if not header or not header.startswith("bytes="):
        return None
    spec = header[6:].split(",")[0].strip()
    if "-" not in spec:
        return None
    start_s, end_s = spec.split("-", 1)
    try:
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else size - 1
    except ValueError:
        return None
    if start < 0 or end >= size or start > end:
        return None
    return start, end


@app.get("/runs/{stem}/preview.mp4")
async def runs_preview_mp4(stem: str, request: Request):
    mp4 = _find_mp4(stem)
    if mp4 is None:
        raise HTTPException(status_code=404, detail="MP4 not found")
    size = mp4.stat().st_size
    range_header = request.headers.get("Range")
    rng = _parse_range(range_header, size)

    def file_iter(start: int, end: int, chunk_size: int = 65536):
        with mp4.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                yield chunk
                remaining -= len(chunk)

    if rng is None:
        return StreamingResponse(
            file_iter(0, size - 1),
            media_type="video/mp4",
            headers={"Content-Length": str(size), "Accept-Ranges": "bytes"},
        )
    start, end = rng
    return StreamingResponse(
        file_iter(start, end),
        status_code=206,
        media_type="video/mp4",
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
        },
    )


class UploadRequest(BaseModel):
    privacy: str = "private"


@app.post("/runs/{stem}/upload", status_code=202)
async def runs_upload(stem: str, req: UploadRequest):
    if req.privacy not in ("private", "unlisted"):
        raise HTTPException(status_code=400, detail="Privacy must be 'private' or 'unlisted'")
    mp4 = _find_mp4(stem)
    if mp4 is None:
        raise HTTPException(status_code=404, detail="MP4 not found")
    if registry.current is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "slot_busy", "stem": registry.current.stem,
                    "kind": registry.current.kind},
        )

    output_dir = OUTPUT_ROOT / stem
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_file = output_dir / f"run-{ts}.log"

    spawn_upload(
        video_path=mp4, stem=stem, privacy=req.privacy,
        output_dir=output_dir, log_file=log_file, registry=registry,
    )
    return {"status": "accepted", "stem": stem}


@app.post("/runs/{stem}/skip-upload", status_code=204)
async def runs_skip_upload(stem: str):
    from fastapi import Response
    state_file = OUTPUT_ROOT / stem / "run-state.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="Run not found")
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state.setdefault("phases", {})["upload"] = {"status": "skipped"}
    state["updated_at"] = datetime.now().isoformat() + "Z"
    state_file.write_text(json.dumps(state, indent=2))
    return Response(status_code=204)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"page_mood": "neutral"},
    )
