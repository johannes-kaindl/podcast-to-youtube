# Reference

Complete, information-oriented reference for **podcast-to-youtube** — the local,
Apple-Silicon pipeline that turns a podcast audio file into a private YouTube video.
For task-oriented guidance see the other manual pages; for the project overview see
[../../README.md](../../README.md).

The pipeline has four phases: **transcribe** (WhisperX) · **meta** (a local MLX LLM
served on port 8080, OpenAI-compatible HTTP) · **render** (Remotion) · **upload**
(YouTube Data API v3).

---

## Contents

- [Entry scripts](#entry-scripts)
  - [`pipeline.py`](#pipelinepy)
  - [`webgui.py`](#webguipy)
  - [`tui.py`](#tuipy)
  - [`transcribe.py`](#transcribepy)
  - [`generate_meta.py`](#generate_metapy)
  - [`render_video.py`](#render_videopy)
  - [`upload_youtube.py`](#upload_youtubepy)
  - [`auth_youtube.py`](#auth_youtubepy)
  - [`download_models.py`](#download_modelspy)
- [WebGUI routes](#webgui-routes)
- [Output artifacts](#output-artifacts)
- [`run-state.json`](#run-statejson)
- [Configuration and environment](#configuration-and-environment)
- [Makefile targets](#makefile-targets)
- [pytest markers](#pytest-markers)

---

## Entry scripts

All scripts run from the repo root inside the uv-managed environment. Either activate
the venv (`source .venv/bin/activate`) or prefix with `uv run`, e.g.
`uv run python pipeline.py …`.

### `pipeline.py`

Orchestrates all four phases and writes [`run-state.json`](#run-statejson).

```bash
python pipeline.py <audio> [options]
```

| Flag | Type / choices | Default | Meaning |
|---|---|---|---|
| `audio` (positional) | path | — | Audio file (`.m4a` / `.mp3` / `.wav`). Required. |
| `--output-dir`, `-o` | path | `./output/<stem>/` | Output directory. The default is `output/` next to `pipeline.py`, with the audio file's stem as the subfolder name. |
| `--show-name` | string | `Signal` | Podcast series name. |
| `--episode` | string | `EP 01` | Episode label. |
| `--language`, `-l` | string | `de` | Language code: `de`, `en`, `auto`, … |
| `--model`, `-m` | `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`, `large-v3-turbo` | `large-v3-turbo` | Whisper model. |
| `--hf-token` | string | `None` (falls back to `HF_TOKEN` env) | Hugging Face token for speaker diarization. |
| `--no-diarize` | flag | off | Disable speaker diarization (monologue). |
| `--speakers` | int | `None` (auto) | Exact number of speakers. |
| `--viz` | `dialogue`, `monologue` | `dialogue` | Visualizer type. |
| `--privacy` | `private`, `unlisted` | `private` | YouTube visibility after upload. |
| `--skip-transcribe` | flag | off | Skip transcription; reuse existing files (aborts if `<stem>.txt` is missing). |
| `--skip-meta` | flag | off | Skip metadata generation. |
| `--skip-render` | flag | off | Skip video rendering. |
| `--skip-upload` | flag | off | Skip the YouTube upload. |

The upload phase runs only if `--skip-upload` is **not** set **and** a rendered video
exists. Each phase wraps its work in a `running` → `done` / `aborted` state transition;
skipped phases are recorded as `skipped`. Diarization actually runs only when a token is
available *or* the pyannote model is cached (see [`transcribe.py`](#transcribepy)).

### `webgui.py`

Starts the FastAPI + HTMX WebGUI (the primary interface) via uvicorn and opens the
browser.

```bash
python webgui.py [options]      # or: make serve
```

| Flag | Type | Default | Meaning |
|---|---|---|---|
| `--host` | string | `127.0.0.1` | Bind host. |
| `--port` | int | `8765` | Bind port. |
| `--no-open` | flag | off | Do not auto-open the browser. |
| `--reload` | flag | off | Dev mode: reload on file change (`make watch`). |

The server is single-user, localhost-only, with no auth or CSRF. Default URL:
`http://127.0.0.1:8765`.

### `tui.py`

Textual full-screen TUI — the fallback frontend.

```bash
python tui.py [audio]
```

| Argument | Meaning |
|---|---|
| `audio` (optional positional) | Pre-fills the audio path. Omit to start with an empty field. |

The TUI takes no flags; it delegates to `tui_app.PipelineTUI`.

### `transcribe.py`

WhisperX transcription with optional speaker diarization. Writes
`<stem>.whisperx.json`, `<stem>.srt`, `<stem>.txt`.

```bash
python transcribe.py <audio> [options]
```

| Flag | Type / choices | Default | Meaning |
|---|---|---|---|
| `audio` (positional) | path | — | Audio file (`m4a` / `mp3` / `wav`). |
| `--output-dir`, `-o` | path | `./output` | Output directory. |
| `--language`, `-l` | string | `de` | Language code; `auto` lets faster-whisper detect. |
| `--model`, `-m` | `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3`, `large-v3-turbo` | `large-v3-turbo` | Whisper model. |
| `--hf-token` | string | falls back to `HF_TOKEN` env | HF token for diarization. |
| `--no-diarize` | flag | off | Disable diarization. |
| `--speakers` | int | `None` (auto) | Exact number of speakers. |

Runs on `device="cpu"`, `compute_type="int8"`. Diarization uses
`pyannote/speaker-diarization-3.1`; it runs only if diarization is enabled **and** a
token is provided or the model is already cached (in which case `HF_HUB_OFFLINE=1` is
set). When diarization is off or skipped, every segment gets `speaker = "SPEAKER_00"`.

### `generate_meta.py`

Generates YouTube metadata (title, description, chapters, tags) from a transcript by
calling the **local MLX server** (OpenAI-compatible API on port 8080). It does **not**
call any cloud LLM.

```bash
python generate_meta.py <transcript.txt> [options]
```

| Flag | Type | Default | Meaning |
|---|---|---|---|
| `transcript` (positional) | path | — | Transcript text file (`.txt`). |
| `--whisperx` | path | `None` | WhisperX JSON, used for timestamps / chapter building. |
| `--show-name` | string | `Signal` | Podcast series name. |
| `--episode` | string | `EP 01` | Episode label. |
| `--language`, `-l` | string | `de` | Metadata language: `de`, `en`, `auto`, … `auto` resolves from the WhisperX JSON's detected language. |
| `--output-dir`, `-o` | path | `./output` | Output directory. |
| `--model` | string | `None` | MLX model id; overrides the `MLX_MODEL` env var for this run. |

Details:

- The HTTP call goes to `<MLX_BASE_URL>/chat/completions` with a 900-second timeout.
- Prompts are loaded from `prompts/meta-system.md` and `prompts/meta-generation.md`
  (optional `---` frontmatter is stripped on load).
- Transcripts are truncated to 60,000 characters before being sent.
- If the model returns no usable chapters, chapters are derived from the WhisperX JSON
  (a new chapter at each ≥ 300-second gap, plus a `00:00 Intro`).
- A transparency footer (NotebookLM / local pipeline credit) is appended to the
  description.
- Outputs `<stem>.youtube-meta.json` and `<stem>.youtube-meta.md` (the `.md` carries
  YAML frontmatter and a post-upload YouTube Studio checklist).
- On unparseable model output the raw response is written to
  `.last-failed-meta-response.txt` and the script exits with code 1.

### `render_video.py`

Renders the Remotion video. Converts the audio to WAV (with 20 s trailing silence),
copies inputs into `visualizer/public/`, then invokes
`npx remotion render`.

```bash
python render_video.py <audio> --whisperx <json> [options]
```

| Flag | Type / choices | Default | Meaning |
|---|---|---|---|
| `audio` (positional) | path | — | Audio file. |
| `--whisperx` | path | — (**required**) | WhisperX JSON. |
| `--srt` | path | `None` | SRT file for caption ducking (optional; an empty SRT is written if absent). |
| `--output`, `-o` | path | `visualizer/out/<stem>-<viz>.mp4` | Output MP4 path. |
| `--viz` | `dialogue`, `monologue` | `dialogue` | Visualizer type → Remotion composition `Podcast-Dialogue` / `Podcast-Monologue`. |
| `--title` | string | `Podcast Episode` | Video title prop. |
| `--episode` | string | `EP 01` | Episode prop. |
| `--show-name` | string | `Signal` | Show-name prop. |

Output is 1920×1080 at 30 fps. Requires `ffmpeg` / `ffprobe` on `PATH` and the Remotion
project (`cd visualizer && npm install`). A non-zero Remotion or ffmpeg exit makes the
script `sys.exit(1)`.

### `upload_youtube.py`

Uploads an MP4 to YouTube via the Data API v3. Auto-discovers metadata and writes the
`upload` phase back into the run's `run-state.json`.

```bash
python upload_youtube.py <video.mp4> [options]
```

| Flag | Type / choices | Default | Meaning |
|---|---|---|---|
| `video` (positional) | path | — | MP4 file. |
| `--meta` | path | auto-discovered | Metadata JSON (from `generate_meta.py`). If omitted, the first `*.youtube-meta.json` next to the video is used. |
| `--title` | string | from meta / video stem | Title (overrides `--meta`). |
| `--description` | string | from meta | Description (overrides `--meta`). |
| `--tags` | list (`nargs="+"`) | from meta | Tags (overrides `--meta`). |
| `--privacy` | `private`, `unlisted`, `public` | `private` | Visibility. |
| `--publish-at` | ISO-8601 string | `None` | Scheduled publish time; only honored when `--privacy private`. |
| `--thumbnail` | path | `None` | Thumbnail image. |
| `--playlist-id` | string | `None` | Playlist id; overrides `show_name`-based mapping. |

Behavior:

- Title is truncated to 100 chars, description to 5000, tags to 500 entries.
- The status body always sets `selfDeclaredMadeForKids=False` and
  `containsSyntheticMedia=True`.
- Chapters from the metadata are appended to the description **only** if there are at
  least three and the first starts at `0:00` / `00:00`.
- Playlist resolution order: explicit `--playlist-id` → `show_name` match in
  `playlists.json` → the `default` key → none. A failed playlist assignment is logged
  but does not fail the upload.
- Credentials come from `.youtube_token.pickle`, auto-refreshed when possible; a
  revoked/expired refresh token triggers re-authorization. If `client_secrets.json` is
  missing the script prints the Google Cloud setup steps and exits 1.

### `auth_youtube.py`

One-time interactive OAuth authorization. Must run in a real terminal so a browser can
open.

```bash
python auth_youtube.py
```

Takes no flags. Reads `client_secrets.json`, runs the installed-app flow
(`run_local_server(port=0)`), and writes `.youtube_token.pickle`. If the token already
exists it prints a message and exits 0 (re-authorize with
`rm .youtube_token.pickle && python auth_youtube.py`). Requested OAuth scopes:
`youtube.upload` and `youtube`.

### `download_models.py`

Pre-fetches models for offline operation.

```bash
python download_models.py [options]      # default: Whisper + alignment (de, en)
```

| Flag | Type | Default | Meaning |
|---|---|---|---|
| `--whisper-models` | list (`nargs="+"`) | all seven sizes | Whisper models to download. |
| `--languages` | list (`nargs="+"`) | `de en` | Languages for alignment models. |
| `--hf-token` | string | falls back to `HF_TOKEN` env | HF token; if present, also downloads the pyannote diarization model. |
| `--status` | flag | off | Only print the cache status, download nothing. |

The cache status (always printed first) reports the Whisper cache
(`~/.cache/whisper/<size>.pt`) and the Hugging Face hub directory
(`$HF_HOME/hub`, default `~/.cache/huggingface/hub`), including whether
`pyannote/speaker-diarization-3.1` is cached.

---

## WebGUI routes

Defined in `webgui/app.py` (FastAPI). Paths use `<stem>` = the audio file's stem (also
the `output/<stem>/` directory name). Only one subprocess runs at a time; routes that
start work return HTTP 409 (`slot_busy`) if a job is already active.

### Pages (HTML)

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Start page (index). |
| GET | `/runs` | Run history. Query `filter` ∈ `all`, `done`, `aborted`, `unfinished`, `not-uploaded`. |
| GET | `/runs/{stem}` | Run-detail page. Variant precedence: aborted > done > ready-to-upload > running. |
| GET | `/runs/{stem}/edit` | Transcript editor (per-segment). |
| GET | `/runs/{stem}/edit/words?segment_index=N` | Per-word editor for one segment. |
| GET | `/runs/{stem}/diff` | Original-vs-current segment diff. |

### Transcript editor mutations

| Method | Path | Purpose |
|---|---|---|
| POST | `/runs/{stem}/edit` | Save all segment texts. Form field `action=save-continue` re-runs the meta phase (HTTP 307); otherwise returns to the run page (303). Saving invalidates the downstream `meta`/`render` phases. |
| POST | `/runs/{stem}/edit/speaker` | Change one segment's speaker; returns the segment partial. |
| POST | `/runs/{stem}/edit/bulk-rename` | Rename a speaker across the whole transcript (`old_name` → `new_name`). |
| POST | `/runs/{stem}/edit/merge` | Merge a segment with the next one. |
| POST | `/runs/{stem}/edit/split` | Split a segment at `char_position`. |
| POST | `/runs/{stem}/edit/words` | Save edited words for one segment. |
| POST | `/runs/{stem}/edit/undo` | Undo the last editor action (re-generates SRT/TXT). |

All mutating edit routes take a snapshot first, then call `invalidate_downstream` and
`cleanup_snapshots`.

### Run lifecycle

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/runs` | Start a full run (JSON `RunRequest`). `pause_after_transcribe=true` is shorthand for skipping meta/render/upload. Redirects (303) to `/runs/{stem}`. |
| POST | `/runs/{stem}/phase/{phase}/start` | Start/restart one phase (`transcribe`/`meta`/`render`/`upload`). For `upload` it spawns `upload_youtube.py`; otherwise it spawns `pipeline.py` with the other phases skipped. |
| POST | `/runs/{stem}/upload` | Start an upload (JSON `{privacy}`; `private`/`unlisted` only). 202 Accepted. |
| POST | `/runs/{stem}/skip-upload` | Mark the upload phase `skipped`. 204. |
| POST | `/runs/{stem}/abort` | Send SIGTERM to the active job for this stem. 204. |

### Streaming and fragments

| Method | Path | Purpose |
|---|---|---|
| GET | `/runs/{stem}/stream` | Server-Sent Events: live from the active job, or replay from the persisted logfile. Honors `Last-Event-ID`. Event types: `log`, `phase`, `progress`, `done`. |
| GET | `/runs/{stem}/phases` | Phase-indicator HTML fragment. |
| GET | `/runs/{stem}/resume-banner` | Resume-banner fragment (`aborted` / `complete` / `inprogress`). |
| GET | `/runs/{stem}/progress?value=&label=` | Progress-bar fragment. |
| GET | `/runs/{stem}/preview.mp4` | The rendered MP4 with HTTP Range support (206 partial content). |

### API / utility

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness probe (`{"status":"ok"}`). |
| POST | `/api/audio/probe` | Probe an audio path (JSON `{path}`). |
| POST | `/api/audio/pick` | Native macOS file picker via `osascript`. Returns `{path}` or `{cancelled:true}`. |
| GET | `/api/settings` | Read UI settings. |
| POST | `/api/settings` | Patch UI settings (`theme`, `tail_default`, `preferred_visualizer`, `preferred_model`). 204. |
| POST | `/open/finder` | Reveal a repo/output path in Finder (`open -R`). 204. |
| POST | `/open/quicktime` | Open a repo/output path in QuickTime Player. 204. |

`/open/*` validate that the path stays inside the repo or `output/` tree.

---

## Output artifacts

For a given input, everything lands in `output/<stem>/` (`<stem>` is the audio
filename without extension).

| Artifact | Written by | Contents |
|---|---|---|
| `<stem>.whisperx.json` | transcribe | Word-level transcript with speaker labels (`segments`, `language`). |
| `<stem>.whisperx.original.json` | editor (first edit) | One-time pristine backup of the transcript. |
| `<stem>.srt` | transcribe | Subtitles; text prefixed with `[SPEAKER_xx]`. |
| `<stem>.txt` | transcribe | Plain-text transcript with `Speaker:` blocks. |
| `<stem>.youtube-meta.json` | meta | Title, description, tags, chapters, category, language, show_name. |
| `<stem>.youtube-meta.md` | meta | Same metadata as Markdown with YAML frontmatter + post-upload checklist. |
| `<stem>-<viz>.mp4` | render | The finished video (1920×1080, 30 fps); `<viz>` is `dialogue` / `monologue`. |
| `run-state.json` | pipeline / editor / upload | Phase + config state (see below). |
| `run-<timestamp>.log` | WebGUI runner | Full subprocess stdout/stderr per run, used for SSE replay. |
| `snapshots/<unix-ts>.json` | editor | Per-mutation undo snapshots; auto-trimmed to the 20 newest. |

The repo-level debug file `.last-failed-meta-response.txt` is written next to
`generate_meta.py` only when the LLM output cannot be parsed.

---

## `run-state.json`

Schema version `1`. Written atomically (tmp + `os.replace`) by `pipeline.py`; the editor
and `upload_youtube.py` also patch it. Phases: `transcribe`, `meta`, `render`, `upload`.

Top-level shape:

```json
{
  "schema_version": 1,
  "audio": "/abs/path/to/podcast.m4a",
  "stem": "podcast",
  "started_at": "2026-06-15T10:00:00Z",
  "updated_at": "2026-06-15T10:12:00Z",
  "config": {
    "show_name": "Signal",
    "episode": "EP 01",
    "language": "de",
    "model": "large-v3-turbo",
    "viz_type": "dialogue",
    "diarize": true,
    "num_speakers": null,
    "privacy": "private",
    "skip_transcribe": false,
    "skip_meta": false,
    "skip_render": false,
    "skip_upload": false
  },
  "phases": {
    "transcribe": { "status": "done", "started_at": "…", "finished_at": "…",
                    "segments": 712, "detected_language": "de",
                    "files": ["podcast.whisperx.json", "podcast.srt", "podcast.txt"] },
    "meta":       { "status": "done", "title": "…",
                    "files": ["podcast.youtube-meta.json", "podcast.youtube-meta.md"] },
    "render":     { "status": "done", "viz_type": "dialogue",
                    "output": "podcast-dialogue.mp4", "size_mb": 84.2 },
    "upload":     { "status": "done", "url": "https://www.youtube.com/watch?v=…",
                    "video_id": "…", "privacy": "private" }
  }
}
```

### Phase statuses

| Status | Meaning |
|---|---|
| `pending` | Not yet run. |
| `running` | In progress (`started_at` set). |
| `done` | Completed successfully (`finished_at` set). |
| `aborted` | Exception or non-zero subprocess exit; carries an `error` string. |
| `skipped` | The phase's `skip_*` flag was set and the phase was never entered; carries a `note`. |

State machine: `pending → running → done | aborted`; or `pending → skipped`. If the
process is killed externally a phase can be left in `running`.

### Per-phase extra fields

| Phase | Fields when `done` | Fields when `aborted` |
|---|---|---|
| `transcribe` | `segments`, `detected_language`, `files` | `error` |
| `meta` | `title`, `files` | `error` |
| `render` | `viz_type`, `output`, `size_mb` | `viz_type`, `error` |
| `upload` | `url`, `video_id`, `privacy` | `error` |

Note: `upload_youtube.py` patches `phases.upload` with `status` / `url` / `privacy` /
`started_at` / `finished_at` / `error` and does **not** preserve other keys; the
WebGUI's `/runs/{stem}/skip-upload` writes `{"status":"skipped"}`. Consumers
(`webgui/runs.py`) read `phases.render.output` for the video path and
`phases.upload.url` for the YouTube link, and compute the total run `duration_s` only
when every phase is `done`/`skipped`.

---

## Configuration and environment

### Files (repo root)

| File | Committed? | Contents |
|---|---|---|
| `client_secrets.json` | no | Google OAuth client (Desktop App, YouTube Data API v3 enabled). |
| `.youtube_token.pickle` | no | Cached OAuth token. |
| `playlists.json` | no | Playlist mapping; copy from `playlists.example.json`. Keys are `show_name` (plus a `default` fallback); keys starting with `_` and empty values are ignored. |
| `.env` | no | Optional environment variables. |
| `prompts/meta-system.md`, `prompts/meta-generation.md` | yes | Metadata-generation prompts (editable without code changes). |

WebGUI settings persist to `~/.whisper-pipeline-ui.json` (keys: `theme`,
`tail_default`, `preferred_visualizer`, `preferred_model`, `pause_after_transcribe`).
The first four are patchable via `POST /api/settings`; `pause_after_transcribe` is a
persisted default only (it is chosen per run on the start form, not via that endpoint).

### Environment variables

| Variable | Default | Used by | Meaning |
|---|---|---|---|
| `MLX_BASE_URL` | `http://localhost:8080/v1` | `generate_meta.py` | Base URL of the local OpenAI-compatible LLM server. |
| `MLX_MODEL` | `mlx-community/Qwen3.6-35B-A3B-4bit` | `generate_meta.py` | Local LLM model id (also settable per-run with `--model`). |
| `HF_TOKEN` | unset | transcribe / download / pipeline | Hugging Face token for pyannote diarization. |
| `HF_HOME` | `~/.cache/huggingface` | transcribe / download | Hugging Face cache root (the pyannote cache check uses `$HF_HOME/hub`). |

### External prerequisites

- A **local MLX server on port 8080** serving the metadata LLM with an OpenAI-compatible
  `/v1/chat/completions` endpoint. Not a cloud LLM. If unreachable, `generate_meta.py`
  exits 1.
- A Google Cloud **OAuth client** (`client_secrets.json`) with the YouTube Data API v3
  enabled, plus a one-time `auth_youtube.py` run.
- `ffmpeg` / `ffprobe` on `PATH` (`brew install ffmpeg`) and the Remotion project
  installed (`cd visualizer && npm install`).
- WhisperX is an optional extra: `uv sync --extra transcribe`.

---

## Makefile targets

| Target | Command | Purpose |
|---|---|---|
| `install` | `uv sync` | Sync the environment (add `--extra transcribe` for WhisperX). |
| `build` | `check` | Full quality gate (this is a flat app, not a wheel). |
| `lint` | `uv run ruff check .` | Lint. |
| `format` | `uv run ruff format .` | Format. |
| `typecheck` | `uv run mypy .` | Strict type check. |
| `test` | `uv run pytest tests/ -q -m "not slow and not needs_models and not needs_youtube"` | Fast unit/integration tests. |
| `test-all` | `uv run pytest tests/ -q` | All tests, incl. slow/integration. |
| `check` | `lint typecheck test` | The full gate (mirrors pre-push). |
| `serve` | `uv run python webgui.py` | Run the WebGUI on `http://localhost:8765`. |
| `watch` | `uv run python webgui.py --reload` | WebGUI with autoreload. |
| `screenshots` | `uv run python tools/screenshots/regenerate.py` | Regenerate `docs/images/`. |
| `hooks` | `uv run pre-commit install --hook-type pre-commit --hook-type pre-push` | Install git hooks. |

---

## pytest markers

Configured in `pyproject.toml` (`addopts = "-ra --strict-markers"`, `asyncio_mode = "auto"`).

| Marker | Meaning |
|---|---|
| `slow` | Slow tests (deselect with `-m "not slow"`). |
| `needs_models` | Requires the WhisperX models / `transcribe` extra. |
| `needs_youtube` | Requires real YouTube Data API credentials. |

`make test` deselects all three; `make test-all` runs everything.
