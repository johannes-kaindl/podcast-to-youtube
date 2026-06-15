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
- **WebGUI screenshots** — `docs/images/` with a hero start-screen shot (incl. the *Pause after transcribe* control), a three-up gallery (live run, ready-to-upload, finished) that surfaces the post-hoc *Edit transcript* affordance, plus a paused-after-transcribe shot and a transcript-editor shot, all embedded in the README.
- **`tools/screenshots/`** — regenerates those screenshots from the real WebGUI (synthetic, schema-accurate demo runs incl. WhisperX JSON for the editor view + Playwright capture).
- **uv + `pyproject.toml`** — canonical python-uv layout (deps + ruff/mypy/pytest config) with a committed `uv.lock`; WhisperX is the optional `transcribe` extra, and `[tool.uv] package = false` reflects the flat app layout.
- **pre-commit hooks** — `ruff`(`--fix`)/`ruff-format` at commit; `mypy --strict` + a fast pytest run at pre-push.
- **`Makefile`** — standard uv targets (`install` / `check` / `lint` / `format` / `typecheck` / `test` / `serve` / `watch` / `screenshots` / `hooks`).
- **Diátaxis user manual** — `docs/manual/` (tutorial · how-to · reference · explanation), linked from the README.
- **Visualizer dev tooling** — npm scripts (`dev` / `build` / `test` / `lint` / `typecheck`), vitest tests for the timeline + speaker helpers, and biome lint/format.
- **Dual-licensing** — `LICENSING.md` (AGPL by default + an on-request commercial license) and `CLA.md` (a lightweight inbound contributor grant that keeps relicensing possible), linked from the README and CONTRIBUTING.
- **German README** — `README.de.md` (full translation), with a language-toggle line at the top of both READMEs.
- **CI** — `.github/workflows/ci.yml` runs the full gate on every push / PR: `ruff` + `ruff format --check` + `mypy --strict` + the fast pytest selection, plus the visualizer's biome / tsc / vitest. Runs on the GitHub mirror (free) and on Codeberg when Forgejo Actions is enabled.

### Changed

- **README** — added Python / platform / tests / docs-license badges, a release-status table, and corrected the test count to 64.
- **CONTRIBUTING.md** — referenced the issue templates and `SECURITY.md`, expanded the development-setup block, restated the out-of-scope list.
- **Codeberg repo metadata** — set the public description and topics so the project shows up correctly in topic searches.
- **Test suite** — grew from 64 to 151 tests (transcript editor V1 + Phase 2 modules and routes).
- **Strict lint + types** — the codebase now passes `ruff` and `mypy --strict` (app modules); a one-time `ruff format` was applied. `.editorconfig`: TOML set to 4-space.
- **Setup → uv** — README + CONTRIBUTING use `uv sync` (`--extra transcribe` for WhisperX) instead of `pip install -r requirements.txt`.
- **README badges** — reordered to the canonical License · Release · CI · Platform sequence.

### Removed

- **`requirements.txt`** — superseded by `pyproject.toml` + `uv.lock` as the single dependency source.
- **Unused dependencies** — dropped `anthropic` (metadata runs on a local MLX server — no cloud LLM) and `python-dotenv` (unreferenced).

### Fixed

- **Stale docs + broken render scripts** — rewrote `visualizer/README.md` to the current Dialogue/Monologue architecture; fixed the broken `render:waveform` / `render:ring` npm scripts (those compositions no longer exist) to `render:dialogue` / `render:monologue`; corrected stale module docstrings (`render_video.py` converts to WAV not MP3; `pipeline.py` metadata is a local MLX LLM, not the "Claude API").
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
