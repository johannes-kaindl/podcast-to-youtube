# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added

- **Transcript editor V1** — `GET`/`POST /runs/{stem}/edit` with two entry points: an opt-in *Pause after transcribe* checkbox on the start form (pipeline stops after transcription so the user can edit) and a post-hoc edit link on every completed run. First save creates a one-time `<stem>.whisperx.original.json` backup and resets the `meta` + `render` phases to `pending` so the existing click-to-restart machinery handles the re-run.
- **Transcript editor Phase 2** — five editing capabilities on top of V1:
  - **Speaker re-labelling** — per-segment dropdown (`POST /edit/speaker`) and bulk rename (`POST /edit/bulk-rename`).
  - **Merge / split segments** — HTMX endpoints (`POST /edit/merge`, `POST /edit/split`) that re-render the segment list in place. Split uses linear time interpolation refined to a word boundary when word timings are available.
  - **Word-level edits** — `GET`/`POST /runs/{stem}/edit/words` opens a per-word table; segment text is rebuilt from the edited word list on save. No audio re-alignment in this phase — run *Transcribe* again for fresh word timings.
  - **Diff view** — `GET /runs/{stem}/diff` shows side-by-side original (from the `.original.json` backup) vs. current, with word-level `<ins>` / `<del>` highlighting via `difflib`. Merge / split origins surface as badges.
  - **Undo stack** — every mutating endpoint writes a pre-mutation snapshot to `output/{stem}/snapshots/<ts>.json` and appends a `_history` entry. `POST /edit/undo` restores the latest snapshot; the stack auto-trims to the 20 newest entries.
- **Editor keyboard shortcuts** — `Ctrl/Cmd+Z` (undo) and `Ctrl/Cmd+S` (save & return) on the edit page. Native field-undo is preserved while a text input has focus.
- **`SECURITY.md`** — disclosure policy, supported versions, reporting channel.
- **`.editorconfig`** — shared editor defaults (4-space Python, 2-space web/data, LF, UTF-8).
- **`.forgejo/issue_template/`** — bug-report and feature-request templates for the Codeberg tracker.
- **WebGUI screenshots** — `docs/images/` with a hero start-screen shot and a three-up gallery (live run, ready-to-upload, finished), embedded in the README.
- **`tools/screenshots/`** — regenerates those screenshots from the real WebGUI (synthetic, schema-accurate demo runs + Playwright capture).

### Changed

- **README** — added Python / platform / tests / docs-license badges, a release-status table, and corrected the test count to 64.
- **CONTRIBUTING.md** — referenced the issue templates and `SECURITY.md`, expanded the development-setup block, restated the out-of-scope list.
- **Codeberg repo metadata** — set the public description and topics so the project shows up correctly in topic searches.
- **Test suite** — grew from 64 to 151 tests (transcript editor V1 + Phase 2 modules and routes).

### Fixed

- **Speaker dropdown duplicated the current speaker** — the fallback `<option>` rendered unconditionally, so any speaker already present in the distinct-speakers list appeared twice in every segment dropdown. The fallback now renders only when the speaker is unknown.

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
