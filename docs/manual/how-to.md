# How-to guides

Task-oriented recipes for the [podcast-to-youtube](../../README.md) pipeline. Each
guide is a focused "How to X": a goal, numbered steps, and the result you should see.

The pipeline turns one podcast audio file (`.m4a` / `.mp3` / `.wav`) into a private
YouTube video in four phases — **transcribe** (WhisperX), **metadata** (a local MLX
LLM on port 8080), **render** (Remotion), **upload** (YouTube Data API v3). The
[WebGUI](../../README.md#webgui) is the primary interface; the recipes below cover both
the WebGUI and the headless CLI.

Everything runs through [`uv`](https://docs.astral.sh/uv/). Either activate the venv once
(`source .venv/bin/activate`) and call `python …`, or prefix each command with
`uv run python …`. The recipes use the `uv run` form so they work without activation.

> **WhisperX is an optional extra.** The transcribe phase needs the `transcribe` extra:
> `uv sync --extra transcribe`. The other phases work after a plain `uv sync`.

See also: the [reference](./reference.md) for the full flag/route catalogue, the
[tutorial](./tutorial.md) for a first end-to-end run, and the
[explanation](./explanation.md) for how the phases fit together.

---

## How to run the pipeline headless via the CLI

**Goal:** produce a video from an audio file without opening the WebGUI.

1. Sync the environment with the transcribe extra (once):

   ```bash
   uv sync --extra transcribe
   ```

2. Make sure the prerequisites for the phases you'll run are up:
   - **Metadata** needs the local MLX LLM server reachable at `http://localhost:8080/v1`
     (override with `MLX_BASE_URL`).
   - **Upload** needs a one-time OAuth authorisation — run `uv run python auth_youtube.py`
     first (it needs a real terminal for the browser flow).

3. Run the full pipeline. With no flags it transcribes, generates metadata, renders, and
   uploads as **private**:

   ```bash
   uv run python pipeline.py podcast.m4a
   ```

4. Add flags to control behaviour. The most common ones:

   ```bash
   # English podcast, the monologue visualiser, a custom episode label
   uv run python pipeline.py podcast.m4a --language en --viz monologue --episode "EP 42"

   # name the series and set the YouTube category metadata
   uv run python pipeline.py podcast.m4a --show-name "Mein Podcast" --episode "EP 07"
   ```

   Full flag list: `uv run python pipeline.py --help`. Key flags:

   | Flag | Default | Meaning |
   |---|---|---|
   | `--output-dir`, `-o` | `./output/<stem>/` | where artifacts land |
   | `--show-name` | `Signal` | podcast series name |
   | `--episode` | `EP 01` | episode label |
   | `--language`, `-l` | `de` | `de`, `en`, `auto` |
   | `--model`, `-m` | `large-v3-turbo` | Whisper model (`tiny`…`large-v3-turbo`) |
   | `--viz` | `dialogue` | `dialogue` or `monologue` |
   | `--hf-token` | — | HuggingFace token for diarization |
   | `--no-diarize` | off | disable speaker diarization (monologue) |
   | `--speakers N` | auto | force exact speaker count |
   | `--privacy` | `private` | `private` or `unlisted` |
   | `--skip-transcribe` / `--skip-meta` / `--skip-render` / `--skip-upload` | off | skip a phase |

**Result:** the run prints a per-phase log and a final `FERTIG` summary with the
transcript segment count, the generated title, the video path, and the YouTube URL.
Artifacts land in `output/<stem>/` and a `run-state.json` records each phase's status.

---

## How to pause after transcribe so you can edit first

**Goal:** stop after Whisper finishes, correct the transcript, then continue with metadata
and render using the corrected text.

### In the WebGUI

1. Start the WebGUI:

   ```bash
   uv run python webgui.py      # or: make serve
   ```

   It opens at `http://localhost:8765`.

2. On the start form pick the audio file and options, then under **Editing workflow** tick
   **Pause after transcribe for editing**. (This is shorthand: the WebGUI skips meta,
   render and upload, so the pipeline stops the moment Whisper is done.)

3. Click **Start pipeline**. The run page streams the log; once transcribe finishes it
   shows a *⏸ Pipeline paused after Transcribe* banner with an **📝 Edit Transcript**
   button (and a **▶ Continue without editing** button if you change your mind).

4. Click **Edit Transcript**, make your corrections (see the next recipe), and save with
   **Save & Continue** to kick off meta + render with the corrected transcript.

### On the CLI

The CLI has no single "pause" flag — express it by skipping the later phases:

1. Transcribe only:

   ```bash
   uv run python pipeline.py podcast.m4a --skip-meta --skip-render --skip-upload
   ```

2. Edit the transcript by hand (or via the WebGUI editor — open
   `http://localhost:8765/runs/<stem>/edit`).

3. Resume the rest, skipping the already-done transcribe step:

   ```bash
   uv run python pipeline.py podcast.m4a --skip-transcribe --skip-upload
   ```

   `--skip-transcribe` reuses the existing files in `output/<stem>/`; it aborts with an
   error if `<stem>.txt` is missing.

**Result:** the pipeline stops after transcribe, leaving `<stem>.whisperx.json`,
`<stem>.srt`, and `<stem>.txt` on disk for editing before the remaining phases run.

---

## How to correct a transcript and re-run only what changed

**Goal:** fix mistyped names/jargon, relabel speakers, and merge/split segments — then have
only metadata and render re-run, not the whole pipeline.

1. From any run page (a transcript must exist), open the editor:
   - **post-hoc:** click **✎ Edit transcript**, or
   - go directly to `http://localhost:8765/runs/<stem>/edit`.

2. **Fix segment text.** Each segment card has an editable text field for the spoken text.
   Edit any number of fields. A segment whose text changed is flagged `_edited: true`.

3. **Save.** Two buttons:
   - **Save & Return** — saves and goes back to the run page.
   - **Save & Continue** — saves, then immediately starts the metadata phase.

4. **Word-level edits (optional).** For finer corrections, open the per-word table at
   `/runs/<stem>/edit/words` (add `?segment_index=N` to jump to a segment).

5. **Review your changes (optional).** `/runs/<stem>/diff` shows original vs. current,
   word by word, against the one-time backup.

6. **Re-run the affected phases.** After save, the `meta` and `render` phases are reset to
   `pending` (upload is left untouched). Either use **Save & Continue** to start meta right
   away, or click the phase indicator on the run page to re-run them. On the CLI:

   ```bash
   uv run python pipeline.py podcast.m4a --skip-transcribe --skip-upload
   ```

**Result:** Saving rewrites `<stem>.whisperx.json` and regenerates the `.srt` / `.txt`
siblings in the same format as the original transcribe step. The first edit creates a
one-time `<stem>.whisperx.original.json` backup. Only `meta` and `render` re-run; the
existing transcript is reused.

> **Why only meta + render?** Both phases consume the transcript: metadata is generated
> from the text, and the render burns captions from the transcript. Transcribe already ran,
> and the editor treats edits as not affecting an already-completed upload — so it resets
> exactly those two phases to `pending`.

---

## How to relabel and bulk-rename speakers

**Goal:** change who's speaking on a segment, or rename a diarization label like
`SPEAKER_00` to a real name everywhere at once.

1. Open the editor (`/runs/<stem>/edit`).

2. **Per-segment relabel:** each segment card has a speaker dropdown listing the existing
   speakers. Pick a different speaker for that segment. The change saves immediately for
   that one segment.

3. **Bulk rename:** use the bulk speaker-rename form at the top of the editor. Enter the
   old label (e.g. `SPEAKER_00`) and the new name (e.g. `Anna`) and submit. Every segment
   carrying the old label is renamed in one pass.

4. (Optional) Verify on the diff view (`/runs/<stem>/diff`), which flags speaker changes.

**Result:** the speaker labels are rewritten in `<stem>.whisperx.json` and the regenerated
`.srt` / `.txt`. Each speaker action snapshots the prior state (undoable) and resets `meta`
and `render` to `pending` so the new labels flow into the metadata and the rendered video.

---

## How to merge or split segments

**Goal:** combine two consecutive segments into one, or split one segment at a cursor
position.

1. Open the editor (`/runs/<stem>/edit`).

2. **Merge:** on a segment, use its merge control to fold it together with the *next*
   segment. The two become one (the merged text + word lists are joined).

3. **Split:** place the cursor in a segment's text where you want the break, then use the
   split control. The segment is divided at that character position into two segments.

4. **Undo if needed.** Every merge/split snapshots the prior state. Use the **Undo**
   dropdown (top-right) or press `Ctrl/Cmd+Z` to revert the last action.

**Result:** the segment list in `<stem>.whisperx.json` is restructured and the `.srt` /
`.txt` regenerated. As with every editor mutation, `meta` and `render` are reset to
`pending` so the change propagates downstream when you re-run them.

---

## How to skip phases

**Goal:** run only the phases you need — e.g. re-render with a different visualiser without
re-transcribing, or regenerate metadata without re-rendering.

### On the CLI

Each phase has a `--skip-…` flag. A skipped phase reuses the existing files in
`output/<stem>/`:

1. Skip the upload (transcribe + meta + render only):

   ```bash
   uv run python pipeline.py podcast.m4a --skip-upload
   ```

2. Re-render only, reusing the existing transcript and metadata:

   ```bash
   uv run python pipeline.py podcast.m4a --skip-transcribe --skip-meta --skip-upload --viz monologue
   ```

3. Regenerate metadata only:

   ```bash
   uv run python pipeline.py podcast.m4a --skip-transcribe --skip-render --skip-upload
   ```

   > **Caveat:** `--skip-transcribe` requires `output/<stem>/<stem>.txt` to already exist —
   > the run aborts with an error otherwise.

### In the WebGUI

- On the start form, the **Skip phases** checkboxes (`Skip transcribe`, `Skip metadata`,
  `Skip render`, `Skip upload`) map one-to-one to the CLI flags. *Skip upload* is ticked by
  default, so a fresh run transcribes, generates metadata and renders, but stops before
  uploading.
- To re-run a single phase of an existing run, open its run page and click that phase's
  indicator — the WebGUI re-runs just that phase (every other phase passed as `--skip-…`).

**Result:** only the requested phases run; skipped phases are recorded as `skipped` (or kept
as `done`) in `run-state.json` and their existing artifacts are reused.

---

## How to pre-fetch models for offline use

**Goal:** download the Whisper, alignment, and (optionally) diarization models ahead of time
so the pipeline runs without internet — except the final upload.

1. Pre-fetch the Whisper models plus alignment models for German and English (the defaults):

   ```bash
   uv run python download_models.py
   ```

2. Narrow the download to specific models or languages if you don't need all of them:

   ```bash
   # only two Whisper models
   uv run python download_models.py --whisper-models base large-v3-turbo

   # alignment models for more languages
   uv run python download_models.py --languages de en fr
   ```

3. Add the speaker-diarization model (needs a HuggingFace token *and* you must have accepted
   the pyannote terms on huggingface.co):

   ```bash
   uv run python download_models.py --hf-token hf_xxx
   ```

   Once cached, diarization works offline without the token. If the terms aren't accepted
   yet the script prints the `pyannote/speaker-diarization-3.1` URL to visit.

4. Check what's already cached without downloading anything:

   ```bash
   uv run python download_models.py --status
   ```

**Result:** the models are cached under `~/.cache/whisper` (Whisper) and the HuggingFace hub
(`$HF_HOME/hub`, default `~/.cache/huggingface/hub`). The script prints a cache-status table
before and after, marking each model ✓ cached or ✗ missing.

---

## How to choose upload visibility (private / unlisted)

**Goal:** publish the finished video as **private** (default) or **unlisted**. Public is not
offered by this tool — set that manually in YouTube Studio afterwards.

### In the WebGUI

1. Run the pipeline up to render (upload is never automatic). On the run page, once render is
   done, the **upload card** appears.
2. Under **Visibility**, choose **Private** (default) or **Unlisted**. *Public* is shown but
   disabled.
3. Click **Upload to YouTube**. (Or click **Skip upload · keep local** to keep the video
   local and mark the upload phase skipped.)

### On the CLI

1. Pass `--privacy`:

   ```bash
   # private (default)
   uv run python pipeline.py podcast.m4a

   # unlisted
   uv run python pipeline.py podcast.m4a --privacy unlisted
   ```

   Valid values for `pipeline.py`: `private`, `unlisted`. (The standalone
   `upload_youtube.py` additionally accepts `public`, but the pipeline does not.)

**Result:** the video is uploaded with the chosen `privacyStatus`. The upload log notes the
status and reminds you to flip it to Public in YouTube Studio when you're ready to publish.
The run page's **Done** state links straight to the uploaded video.

---

## How to regenerate the documentation screenshots

**Goal:** rebuild the WebGUI screenshots in `docs/images/` used by the top-level README.

1. Sync the dev environment (Playwright lives in the dev group; no `transcribe` extra
   needed — the screenshots don't run the ML stack):

   ```bash
   uv sync
   ```

2. Make sure the prerequisites are present:
   - **Google Chrome** installed — Playwright drives it via `channel="chrome"`.
   - **ffmpeg** for the poster frame, and optionally **pngquant** for PNG optimisation
     (without it the larger raw PNGs are copied through).

3. Run the regenerator (via the Makefile or directly):

   ```bash
   make screenshots
   # equivalently:
   uv run python tools/screenshots/regenerate.py            # default port 8799
   ```

   Useful flags:

   ```bash
   uv run python tools/screenshots/regenerate.py --port 9000 --keep-demo
   ```

   - `--port` — port for the temporary WebGUI (default `8799`).
   - `--keep-demo` — keep the synthetic `output/` demo runs for inspection instead of
     deleting them.

**Result:** the tool builds a synthetic demo `output/` tree, starts the real WebGUI, drives
it through five views with Playwright (dark theme forced), optimises the PNGs, and writes
them to `docs/images/`: `webgui-start.png`, `webgui-running.png`, `webgui-upload.png`,
`webgui-done.png`, and `webgui-editor.png`. The capture is deterministic, so re-running
produces the same images; the synthetic runs are cleaned up afterwards unless `--keep-demo`
is set. See [`tools/screenshots/README.md`](../../tools/screenshots/README.md) for details.

---

Back to the [README](../../README.md) · [Reference](./reference.md) ·
[Tutorial](./tutorial.md) · [Explanation](./explanation.md)
