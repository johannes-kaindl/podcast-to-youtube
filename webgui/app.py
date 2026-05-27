"""FastAPI app for the Whisper-Pipeline WebGUI.

Single-User, localhost only. No auth, no CSRF.
"""
import json
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from pipeline_core import PipelineConfig, build_command, resolve_audio_path
from transcript_editor import load_segments, save_edits, invalidate_downstream, has_been_edited
from transcript_segment_ops import change_speaker, bulk_rename_speaker, merge_segment, split_segment
from transcript_word_ops import load_words_flat, save_word_edits
from transcript_history import snapshot, undo_last, list_history, cleanup_snapshots
from transcript_diff import compute_segment_diff
from .probe import audio_probe
from .runner import registry, spawn_pipeline, spawn_upload, StreamEvent, latest_logfile, replay_logfile
from .runs import list_runs, filter_runs
from .settings import load_settings, save_settings

REPO_ROOT = Path(__file__).parent.parent
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
OUTPUT_ROOT = REPO_ROOT / "output"
SETTINGS_PATH = Path(os.path.expanduser("~/.whisper-pipeline-ui.json"))

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


def _load_transcript_snippet(stem: str, max_lines: int = 8) -> list[dict]:
    txt = OUTPUT_ROOT / stem / f"{stem}.txt"
    if not txt.exists():
        return []
    lines = []
    for raw in txt.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s:
            continue
        if ":" in s:
            spk, _, text = s.partition(":")
            lines.append({"spk": spk.strip(), "text": text.strip()})
        else:
            lines.append({"spk": "", "text": s})
        if len(lines) >= max_lines:
            break
    return lines


def _load_metadata(stem: str) -> dict | None:
    meta_file = OUTPUT_ROOT / stem / f"{stem}.youtube-meta.json"
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _distinct_speakers(json_path: Path) -> list[str]:
    if not json_path.exists():
        return []
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return sorted({seg.get("speaker", "") for seg in data.get("segments", []) if seg.get("speaker")})


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
    pause_after_transcribe: bool = False


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/api/audio/probe")
async def api_audio_probe(req: AudioProbeRequest):
    audio_path = resolve_audio_path(req.path, REPO_ROOT)
    return audio_probe(audio_path, OUTPUT_ROOT)


@app.post("/api/audio/pick")
async def api_audio_pick():
    """Open a native macOS file-picker via osascript. Returns {path} or {cancelled: true}.

    Workaround for browsers that strip the OS path from drag-drop events.
    Single-user / localhost only — never expose without auth.
    """
    script = (
        'try\n'
        '  POSIX path of (choose file of type {"public.audio"} '
        'with prompt "Choose audio for the pipeline")\n'
        'on error number -128\n'
        '  return ""\n'
        'end try'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise HTTPException(status_code=500, detail=f"osascript failed: {exc}")
    path = (result.stdout or "").strip()
    if not path:
        return {"cancelled": True}
    return {"path": path}


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


@app.post("/runs/{stem}/phase/{phase}/start")
async def runs_phase_start(stem: str, phase: str):
    """Start (or restart) a single phase of an existing run.

    Reads the run-state.json for audio + config, then spawns either
    pipeline.py (with all *other* phases --skip-…) or upload_youtube.py
    (for the upload phase). Caller is responsible for prerequisite checks
    (e.g. you can't start render without a transcript on disk).
    """
    if phase not in ("transcribe", "meta", "render", "upload"):
        raise HTTPException(status_code=400, detail="Unknown phase")
    if registry.current is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "slot_busy", "stem": registry.current.stem,
                    "kind": registry.current.kind},
        )

    state_file = OUTPUT_ROOT / stem / "run-state.json"
    if not state_file.exists():
        raise HTTPException(status_code=404, detail="Run-state not found")
    state = _load_state(stem)
    audio_str = state.get("audio")
    if not audio_str or not Path(audio_str).exists():
        raise HTTPException(status_code=404, detail="Original audio file is gone")

    output_dir = OUTPUT_ROOT / stem
    ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_file = output_dir / f"run-{ts}.log"

    if phase == "upload":
        mp4 = _find_mp4(stem)
        if mp4 is None:
            raise HTTPException(status_code=404, detail="No MP4 to upload — run render first")
        privacy = state.get("config", {}).get("privacy", "private")
        if privacy not in ("private", "unlisted"):
            privacy = "private"
        spawn_upload(
            video_path=mp4, stem=stem, privacy=privacy,
            output_dir=output_dir, log_file=log_file, registry=registry,
        )
    else:
        cfg_dict = state.get("config", {})
        diarize_raw = cfg_dict.get("diarize", True)
        if diarize_raw is False:
            diarize = "off"
        elif isinstance(cfg_dict.get("num_speakers"), int):
            diarize = str(cfg_dict["num_speakers"])
        else:
            diarize = "auto"
        skip_map = {
            "transcribe": "skip_transcribe", "meta": "skip_meta",
            "render": "skip_render", "upload": "skip_upload",
        }
        skips = {key: True for key in skip_map.values()}
        skips[skip_map[phase]] = False
        cfg = PipelineConfig(
            audio=audio_str,
            viz=cfg_dict.get("viz_type", "dialogue"),
            language=cfg_dict.get("language", "de"),
            model=cfg_dict.get("model", "large-v3-turbo"),
            diarize=diarize,
            episode=cfg_dict.get("episode", "EP 01"),
            show_name=cfg_dict.get("show_name", "Signal"),
            **skips,
        )
        cmd = build_command(cfg, REPO_ROOT)
        spawn_pipeline(
            cmd=cmd, stem=stem, audio_path=Path(audio_str),
            output_dir=output_dir, log_file=log_file, registry=registry,
        )
    return RedirectResponse(url=f"/runs/{stem}", status_code=303)


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

    # Pause-after-transcribe is shorthand for skipping everything after.
    skip_meta = req.skip_meta or req.pause_after_transcribe
    skip_render = req.skip_render or req.pause_after_transcribe
    skip_upload = req.skip_upload or req.pause_after_transcribe

    cfg = PipelineConfig(
        audio=str(audio_path), viz=req.viz, language=req.language, model=req.model,
        diarize=req.diarize, episode=req.episode, show_name=req.show_name,
        skip_transcribe=req.skip_transcribe, skip_meta=skip_meta,
        skip_render=skip_render, skip_upload=skip_upload,
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
    is_starting = (
        registry.current is not None and registry.current.stem == stem
        and not state_file.exists()
    )
    if not state_file.exists() and not is_starting:
        raise HTTPException(status_code=404, detail="Run not found")
    state = _load_state(stem)  # returns "all pending" default if file missing
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

    transcript_json = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    transcript_exists = transcript_json.exists()
    edited_any = has_been_edited(str(transcript_json)) if transcript_exists else False
    is_paused = (
        transcript_exists
        and phases.get("transcribe", {}).get("status") == "done"
        and phases.get("meta", {}).get("status") in ("pending", "skipped")
        and state.get("config", {}).get("skip_meta") is True
        and registry.current is None
    )

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
            "transcript_lines": _load_transcript_snippet(stem),
            "youtube_meta": _load_metadata(stem),
            "transcript_exists": transcript_exists,
            "edited_any": edited_any,
            "is_paused": is_paused,
        },
    )


@app.get("/runs/{stem}/edit", response_class=HTMLResponse)
async def run_edit(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    segments = load_segments(str(json_path))
    backup_exists = json_path.with_name(json_path.stem + ".original.json").exists()
    edited_any = has_been_edited(str(json_path))
    return templates.TemplateResponse(
        request,
        "run_edit.html",
        {
            "stem": stem,
            "segments": segments,
            "backup_exists": backup_exists,
            "edited_any": edited_any,
            "page_mood": "neutral",
        },
    )


@app.post("/runs/{stem}/edit")
async def run_edit_save(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    if registry.current is not None:
        raise HTTPException(
            status_code=409,
            detail={"error": "slot_busy", "stem": registry.current.stem,
                    "kind": registry.current.kind},
        )
    form = await request.form()
    # Form fields come back as segment_text_0, segment_text_1, … — collect in order
    segments = load_segments(str(json_path))
    new_texts: list[str] = []
    for i in range(len(segments)):
        new_text = form.get(f"segment_text_{i}")
        if new_text is None:
            raise HTTPException(status_code=400, detail=f"Missing segment_text_{i}")
        new_texts.append(new_text)
    save_edits(str(json_path), new_texts)

    state_path = OUTPUT_ROOT / stem / "run-state.json"
    invalidate_downstream(str(state_path))

    action = form.get("action", "save-return")
    if action == "save-continue":
        return RedirectResponse(
            url=f"/runs/{stem}/phase/meta/start",
            status_code=307,  # preserve POST method
        )
    return RedirectResponse(url=f"/runs/{stem}", status_code=303)


@app.post("/runs/{stem}/edit/speaker", response_class=HTMLResponse)
async def run_edit_speaker(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    form = await request.form()
    try:
        segment_index = int(form.get("segment_index", "-1"))
    except ValueError:
        raise HTTPException(status_code=400, detail="segment_index must be int")
    new_speaker = form.get("speaker", "").strip()
    if not new_speaker:
        raise HTTPException(status_code=400, detail="speaker required")
    snapshot(str(json_path), action="edit_speaker", metric=f"segment {segment_index} → {new_speaker}")
    try:
        change_speaker(str(json_path), segment_index, new_speaker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    invalidate_downstream(str(OUTPUT_ROOT / stem / "run-state.json"))
    cleanup_snapshots(str(json_path))

    segments = load_segments(str(json_path))
    speakers = _distinct_speakers(json_path)
    seg = segments[segment_index]
    return templates.TemplateResponse(
        request, "_partials/segment_editor.html",
        {"stem": stem, "seg": seg, "loop_index": segment_index, "speakers": speakers},
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
        {"phases": state.get("phases", {}), "stem": stem},
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
    # Authoritative: the file the last render actually wrote.
    rendered = _load_state(stem).get("phases", {}).get("render", {}).get("output")
    if rendered:
        candidate = output_dir / rendered
        if candidate.exists():
            return candidate
    # Fallback: newest by mtime — alphabetic sort would pick the wrong viz
    # variant when an output dir holds several .mp4 files.
    mp4s = sorted(output_dir.glob(f"{stem}-*.mp4"), key=lambda p: p.stat().st_mtime)
    if not mp4s:
        mp4s = sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
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


class OpenRequest(BaseModel):
    path: str


def _path_is_safe(path: Path) -> bool:
    try:
        resolved = path.resolve()
        return (resolved.is_relative_to(REPO_ROOT.resolve())
                or resolved.is_relative_to(OUTPUT_ROOT.resolve()))
    except (OSError, ValueError):
        return False


@app.post("/runs/{stem}/abort", status_code=204)
async def runs_abort(stem: str):
    from fastapi import Response
    job = registry.current
    if job is None or job.stem != stem:
        raise HTTPException(status_code=404, detail="No active run for this stem")
    if job.process and job.process.poll() is None:
        try:
            job.process.send_signal(signal.SIGTERM)
        except ProcessLookupError:
            pass
    return Response(status_code=204)


@app.post("/open/finder", status_code=204)
async def open_finder(req: OpenRequest):
    from fastapi import Response
    path = Path(req.path)
    if not _path_is_safe(path):
        raise HTTPException(status_code=400, detail="Path outside repo")
    subprocess.run(["open", "-R", str(path)], check=False)
    return Response(status_code=204)


@app.post("/open/quicktime", status_code=204)
async def open_quicktime(req: OpenRequest):
    from fastapi import Response
    path = Path(req.path)
    if not _path_is_safe(path):
        raise HTTPException(status_code=400, detail="Path outside repo")
    subprocess.run(["open", "-a", "QuickTime Player", str(path)], check=False)
    return Response(status_code=204)


class SettingsPatch(BaseModel):
    theme: str | None = None
    tail_default: bool | None = None
    preferred_visualizer: str | None = None
    preferred_model: str | None = None


@app.get("/api/settings")
async def api_get_settings():
    return load_settings(SETTINGS_PATH)


@app.post("/api/settings", status_code=204)
async def api_post_settings(patch: SettingsPatch):
    from fastapi import Response
    payload = {k: v for k, v in patch.model_dump().items() if v is not None}
    save_settings(SETTINGS_PATH, payload)
    return Response(status_code=204)


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"page_mood": "neutral"},
    )
