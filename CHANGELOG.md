# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **`SECURITY.md`** — disclosure policy, supported versions, reporting channel.
- **`.editorconfig`** — shared editor defaults (4-space Python, 2-space web/data, LF, UTF-8).
- **`.forgejo/issue_template/`** — bug-report and feature-request templates for the Codeberg tracker.

### Changed

- **README** — added Python / platform / tests / docs-license badges, a release-status table, and corrected the test count to 64.
- **CONTRIBUTING.md** — referenced the issue templates and `SECURITY.md`, expanded the development-setup block, restated the out-of-scope list.
- **Codeberg repo metadata** — set the public description and topics so the project shows up correctly in topic searches.

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
