# podcast-to-youtube

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Docs: CC BY-SA 4.0](https://img.shields.io/badge/docs-CC%20BY--SA%204.0-blue.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![Codeberg Release](https://img.shields.io/badge/codeberg-v1.0.0-green)](https://codeberg.org/jkaindl/podcast-to-youtube/releases)
[![Status: Active](https://img.shields.io/badge/status-active-brightgreen)](https://codeberg.org/jkaindl/podcast-to-youtube)
[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Platform: macOS](https://img.shields.io/badge/platform-macOS%2015%2B%20%C2%B7%20Apple%20Silicon-lightgrey)](https://www.apple.com/macos/)
[![Tests](https://img.shields.io/badge/tests-151%20passing-brightgreen)](https://codeberg.org/jkaindl/podcast-to-youtube/src/branch/main/tests)

Automated end-to-end pipeline: podcast audio → finished YouTube video, running locally on Apple Silicon.

**Target platform:** Apple Silicon Mac, macOS 15+. Mac-only by design.

> **Status: v1.0.0 — first public release.** The full four-phase pipeline runs end-to-end; the WebGUI is the primary interface. Mac Silicon, AGPL-3.0.

<p align="center">
  <img src="docs/images/webgui-start.png" width="880"
       alt="The WebGUI start screen: an audio-path field, the visualizer, language, model and speaker options, and the Start pipeline button.">
</p>

<p align="center"><sub>Drop an episode, pick the options, start the pipeline — everything runs locally.</sub></p>

---

## About

A single audio file (`.m4a` / `.mp3` / `.wav`) becomes a private YouTube video. Everything runs locally on Mac hardware — transcription with WhisperX, metadata generation with a local MLX-served LLM, video rendering with Remotion. The only network call is the YouTube upload itself.

---

## Release status

For full per-release notes see [`CHANGELOG.md`](CHANGELOG.md).

| Version | Date       | Headline                                                                                                                |
| ------- | ---------- | ----------------------------------------------------------------------------------------------------------------------- |
| v1.0.0  | 2026-05-22 | **Initial public release** — four-phase pipeline (transcribe · metadata · render · upload), WebGUI + TUI, 64 tests.     |

---

## What it does

Four phases, one pipeline:

```mermaid
flowchart TD
    A[Audio · m4a / mp3 / wav] --> B[Transcribe · WhisperX]
    B --> C[Metadata · local LLM]
    C --> D[Render · Remotion]
    D --> E[Upload · YouTube Data API]
    E --> F[Private video]
```

1. **Transcribe** — WhisperX produces a word-level transcript (JSON / SRT / TXT) with speaker labels.
2. **Metadata** — a local MLX LLM generates the YouTube title, description, tags and chapters.
3. **Render** — Remotion renders a 1920×1080 MP4 with an audio visualiser.
4. **Upload** — the YouTube Data API v3 publishes the video as private. Upload is a manual, explicit step.

---

## Quick start

```bash
git clone https://codeberg.org/jkaindl/podcast-to-youtube.git
cd podcast-to-youtube

# Python environment
uv venv .venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt

# system tools
brew install ffmpeg

# Remotion dependencies (once)
cd visualizer && npm install && cd ..

# YouTube OAuth (once — needs a real terminal for the browser flow)
python auth_youtube.py

# launch the WebGUI
python webgui.py
```

The WebGUI opens at `http://localhost:8765`.

Two external prerequisites: a local **MLX server on port 8080** serving the metadata LLM, and a Google Cloud **OAuth client** (`client_secrets.json`, Desktop App, with the YouTube Data API v3 enabled). `upload_youtube.py` prints the Google Cloud setup steps if `client_secrets.json` is missing.

---

## WebGUI

`python webgui.py` starts a FastAPI + HTMX interface and opens the browser at `http://localhost:8765`.

Pick an audio file, choose the options, click **Start pipeline**. The run page streams the live log and phase progress over Server-Sent Events. After the render phase the MP4 preview plays inline. Upload is never automatic — choose the visibility (private / unlisted) and click **Upload to YouTube**.

<table>
  <tr>
    <td width="33%" valign="top">
      <a href="docs/images/webgui-running.png"><img src="docs/images/webgui-running.png"
        alt="WebGUI during a live run: the render phase in progress, the pipeline log streaming, and the transcript and YouTube-metadata previews already populated."></a>
      <br><sub><b>Live run</b> — phase stepper, streaming log, transcript &amp; metadata as they land.</sub>
    </td>
    <td width="33%" valign="top">
      <a href="docs/images/webgui-upload.png"><img src="docs/images/webgui-upload.png"
        alt="WebGUI ready-to-upload state: the rendered video preview with the upload card, where you choose private or unlisted visibility before confirming the upload."></a>
      <br><sub><b>Ready to upload</b> — render preview ready; you pick visibility and confirm. Never automatic.</sub>
    </td>
    <td width="33%" valign="top">
      <a href="docs/images/webgui-done.png"><img src="docs/images/webgui-done.png"
        alt="WebGUI finished state: all four phases complete, the rendered video, and a card linking to the uploaded YouTube video."></a>
      <br><sub><b>Done</b> — all four phases complete, video rendered and uploaded.</sub>
    </td>
  </tr>
</table>

| Key | Action |
|---|---|
| `Ctrl+R` | Open the start-pipeline dialog |
| `Ctrl/Cmd+Z` | *(on edit page)* Undo the last editor action — native field-undo wins while a text input is focused |
| `Ctrl/Cmd+S` | *(on edit page)* Save & return to the run page |

### Transcript editor

Whisper occasionally mistypes names, jargon, and foreign words. Rather than re-running the whole pipeline, the editor lets the transcript be corrected between phases and reruns only what changed.

Two ways in:

- **Pause after transcribe** — tick the *Pause after transcribe for editing* checkbox on the start form. The pipeline stops after Whisper finishes; the run page surfaces an *Edit Transcript* button.
- **Edit anytime** — every run with a transcript exposes an *Edit transcript* link on the run page. Saving an edit resets the `meta` + `render` phases to `pending`; click the phase indicator to re-run them with the corrected transcript.

What the editor can do:

- **Segment text** — fix mistyped names, jargon, foreign words.
- **Speaker re-labelling** — change the speaker per segment, or bulk-rename `SPEAKER_00` → `Anna` across the whole transcript.
- **Merge / split segments** — combine two consecutive segments or split one at the cursor position.
- **Word-level edits** — `/runs/<stem>/edit/words` opens a per-word table for finer-grained corrections.
- **Diff view** — `/runs/<stem>/diff` shows original vs. current, word-by-word.
- **Undo** — every action snapshots the prior state. The Undo dropdown shows the recent history; `Ctrl/Cmd+Z` reverts the last action.

The first save creates a one-time `<stem>.whisperx.original.json` backup. Snapshots accumulate in `output/<stem>/snapshots/`, auto-trimmed to the 20 newest.

---

## CLI

The pipeline also runs headless:

```bash
source .venv/bin/activate

# full run — transcribe, metadata, render, upload
python pipeline.py podcast.m4a

# skip the upload
python pipeline.py podcast.m4a --skip-upload

# pick a visualiser
python pipeline.py podcast.m4a --viz dialogue --skip-upload
python pipeline.py podcast.m4a --viz monologue --skip-upload

# speaker diarization (requires accepting the pyannote terms on huggingface.co)
python pipeline.py podcast.m4a --hf-token $HF_TOKEN

python pipeline.py --help
```

A Textual TUI is kept as a fallback frontend: `python tui.py podcast.m4a`.

Output lands in `output/<stem>/`:

- `<stem>.whisperx.json` — word-level transcript with speaker labels
- `<stem>.whisperx.original.json` — pristine backup, created the first time the transcript is edited (see [Transcript editor](#transcript-editor))
- `<stem>.srt` — subtitles
- `<stem>.txt` — plain-text transcript
- `<stem>.youtube-meta.json` — title, description, tags, chapters
- `<stem>-<viz>.mp4` — the finished video (1920×1080, 30 fps)
- `snapshots/<unix-ts>.json` — per-mutation undo snapshots written by the editor; auto-trimmed to the 20 newest

### Scripts

| Script | Purpose |
|---|---|
| `pipeline.py` | Orchestrates all four phases |
| `transcribe.py` | WhisperX: audio → JSON / SRT / TXT |
| `generate_meta.py` | MLX LLM: transcript → YouTube metadata |
| `render_video.py` | Remotion: audio + transcript → MP4 |
| `upload_youtube.py` | YouTube Data API v3: MP4 → private video |
| `auth_youtube.py` | One-time OAuth authorisation |
| `download_models.py` | Pre-fetch all models for offline use |

---

## Configuration

| File | Contents |
|---|---|
| `client_secrets.json` | Google OAuth credentials (not committed) |
| `.youtube_token.pickle` | Cached OAuth token (not committed) |
| `playlists.json` | Playlist auto-assignment — copy from `playlists.example.json` |
| `.env` | Optional environment variables |

Environment variables:

- `MLX_BASE_URL` — base URL of the local LLM server (default `http://localhost:8080/v1`)
- `MLX_MODEL` — the local LLM model id
- `HF_TOKEN` — Hugging Face token for speaker diarization

### Offline use

`python download_models.py` pre-fetches the Whisper and alignment models so the pipeline runs without internet (except the upload). `--hf-token` adds the diarization model; `--status` shows the cache state.

---

## Test suite

```bash
.venv/bin/python -m pytest tests/ -q
```

151 unit and integration tests covering the shared pipeline core, the probe and run-history helpers, the job runner, every WebGUI route, and the four transcript-editor modules (`transcript_editor`, `transcript_segment_ops`, `transcript_word_ops`, `transcript_history`, `transcript_diff`). Runs in ~3 s on Apple Silicon.

---

## Project layout

```
pipeline.py            Orchestrator — four phases, writes run-state.json
pipeline_core.py       Shared helpers (TUI + WebGUI)
transcribe.py          WhisperX step
generate_meta.py       Metadata step (local MLX LLM)
render_video.py        Render step (Remotion)
upload_youtube.py      Upload step (YouTube Data API v3)
transcript_editor.py        Editor V1 — load / save / regen / invalidate
transcript_segment_ops.py   Editor — merge, split, change_speaker, bulk_rename
transcript_word_ops.py      Editor — load_words_flat, save_word_edits
transcript_history.py       Editor — snapshot, undo_last, cleanup_snapshots
transcript_diff.py          Editor — compute_segment_diff vs .original.json
webgui/                FastAPI app — routes, job runner, SSE, templates, static
webgui.py              WebGUI entry point
tui*.py                Textual TUI (fallback frontend)
visualizer/            Remotion project (Node) — the video renderer
tests/                 pytest suite
docs/                  Design specs, implementation plans, screenshots
tools/                 Dev tooling (e.g. screenshot regeneration)
```

---

## Contributing

Issues and pull requests are welcome at [Codeberg](https://codeberg.org/jkaindl/podcast-to-youtube) — the issue templates in [`.forgejo/issue_template/`](.forgejo/issue_template/) prompt for everything that's needed. For larger changes, open an issue first. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the development workflow and [`SECURITY.md`](SECURITY.md) for security-sensitive reports.

---

## Project status

Actively maintained by a single contributor. Apple Silicon focus — the pipeline is Mac-only by design. Cross-platform pull requests are accepted but not actively driven.

---

## License

Code: AGPL-3.0-or-later ([`LICENSE`](LICENSE)). Documentation: CC BY-SA 4.0 ([`LICENSE-DOCS`](LICENSE-DOCS)).

The AGPL network clause keeps modifications to a networked deployment open-source.

---

Copyright (C) 2026 Johannes Kaindl.
