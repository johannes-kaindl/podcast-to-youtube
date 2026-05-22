# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [v1.0.0] — 2026-05-22 — Initial public release

First public release. A podcast audio file runs end-to-end through a local
four-phase pipeline — transcribe, metadata, render, upload — and lands as a
private YouTube video. Validated on a full-length (40-minute) episode.

### Added

- **Pipeline** — `pipeline.py` orchestrates the four phases (transcribe,
  metadata, render, upload) and records progress in `run-state.json`.
- **WebGUI** — FastAPI + Jinja2 + HTMX + SSE interface (`webgui.py`,
  `http://localhost:8765`): live log streaming, phase indicator, audio probe
  with ETA, inline MP4 preview, click-to-restart for individual phases,
  manual upload with a live progress bar, and a run history.
- **TUI** — the Textual interface is kept as a fallback frontend, sharing
  the same pipeline core.
- **Pipeline steps** — `transcribe.py` (WhisperX), `generate_meta.py`
  (local MLX LLM), `render_video.py` (Remotion), `upload_youtube.py`
  (YouTube Data API v3), each runnable standalone.
- **Chapters** — generated chapters are appended to the YouTube description
  as a timestamped list, which YouTube turns into clickable chapter markers.
- **Offline mode** — `download_models.py` pre-fetches every model so the
  pipeline runs without internet, the upload aside.
- **Test suite** — 64 unit and integration tests.
