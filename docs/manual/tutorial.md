# Your first video

This is a start-to-finish walkthrough. By the end you will have turned one podcast
audio file into a finished, **private** YouTube video — all from the WebGUI, with
everything except the final upload running locally on your Mac.

You do not need to understand the whole pipeline yet. Just follow along. We will
take one concrete episode through all four phases — **transcribe → metadata →
render → upload** — and you will watch each one happen on screen.

> **What you need:** an Apple Silicon Mac running macOS 15+, and one podcast audio
> file (`.m4a`, `.mp3`, or `.wav`). A short episode is perfect for a first run.

When you finish, see [How-to guides](./how-to.md) and the [Reference](./reference.md)
for the options we skip past here, and the project [README](../../README.md) for the
big picture.

---

## 1. Install

Open Terminal and clone the project, then let `uv` build the Python environment.
`uv sync` reads `pyproject.toml` and `uv.lock` and creates a `.venv` for you.

```bash
git clone https://codeberg.org/jkaindl/podcast-to-youtube.git
cd podcast-to-youtube

# Python environment for the WebGUI, metadata, and upload
uv sync

# The transcription phase (WhisperX) pulls a large extra stack — add it now
uv sync --extra transcribe
```

Install `ffmpeg` (used for audio handling) with Homebrew:

```bash
brew install ffmpeg
```

The renderer is a small Node project under `visualizer/`. Install its dependencies
once:

```bash
cd visualizer && npm install && cd ..
```

That is the whole code setup. Two external pieces remain — the local LLM that writes
your metadata, and your YouTube authorization. We will set those up next.

---

## 2. Start the local metadata LLM

The metadata phase (titles, description, tags, chapters) is written by a **local**
language model — nothing is sent to a cloud service. The pipeline talks to it over
an OpenAI-compatible HTTP endpoint on **port 8080**.

On Apple Silicon this is served by [`mlx_lm`](https://github.com/ml-explore/mlx-lm).
Start the server in its own terminal window and leave it running:

```bash
mlx_lm.server --port 8080
```

The pipeline expects the server at `http://localhost:8080/v1` (the default
`MLX_BASE_URL`). You do not need to configure anything for a first run — as long as
that server is up and serving a model when the metadata phase begins, you are set.

> Keep this terminal open for the whole walkthrough. If the metadata phase ever
> fails, the first thing to check is that this server is still running.

---

## 3. Authorize YouTube (once)

The very last phase uploads your finished video. That needs a one-time Google
authorization, which has two parts.

**a) Get a Google OAuth client.** In the
[Google Cloud Console](https://console.cloud.google.com/), create a project, enable
the **YouTube Data API v3**, then create an **OAuth 2.0 Client ID** of type
**Desktop App**. Download the JSON and save it as `client_secrets.json` in the
project root.

> If you skip this, `upload_youtube.py` will print these exact steps the first time
> it needs the file — so you can always come back to it.

**b) Run the authorization flow.** This opens a browser, so run it directly in your
terminal (not through a wrapper):

```bash
source .venv/bin/activate
python auth_youtube.py
```

Sign in with the Google account that owns your YouTube channel and approve access.
The script caches a token to `.youtube_token.pickle`. From now on, uploads run
without a browser popup.

---

## 4. Launch the WebGUI

The WebGUI is the primary interface. Start it with:

```bash
uv run python webgui.py
```

You will see a line like:

```
  Whisper-Pipeline WebGUI  ->  http://127.0.0.1:8765
```

Your browser opens automatically at **http://localhost:8765**. (If it doesn't, open
that address yourself.) You should see the start screen with a single audio-path
field and a configuration card below it.

---

## 5. Pick your audio file

On the start screen, find the **Audio path** field under "01 · Source".

Click **Browse** to open a native macOS file picker and choose your episode, or
paste an **absolute** path directly (for example
`/Users/you/Podcasts/episode-01.m4a`). The field accepts `.m4a`, `.mp3`, and `.wav`.

Once a valid file is recognized, the **Start pipeline** button at the bottom becomes
clickable and a small pre-flight readout (estimated time, disk free) appears.

---

## 6. Choose your options

Under "03 · Configuration" you will see a handful of choices. For your first video,
the defaults are deliberately sensible — you only need to set two text fields.

- **Visualizer** — leave it on **Dialogue** (a two-column waveform). Good for a
  conversation. (Use **Monologue** for a single speaker.)
- **Language** — choose **Auto-detect**, or pick **de — German** / **en — English**
  if you already know.
- **Whisper model** — leave it on **large-v3-turbo · recommended**.
- **Speakers** — leave it on **Auto**.
- **Episode** — type something like `EP 01`.
- **Channel · series** — type your show name, e.g. `Signal`.

Under **Skip phases**, notice that **Skip upload** is **checked by default**. That is
intentional: the pipeline never uploads automatically. We will run the first three
phases, watch the preview, and then upload by hand in step 10. Leave the skip
checkboxes as they are.

Leave **Pause after transcribe for editing** unchecked for this first happy path.

That's it — don't worry about the other options. They are covered in the
[How-to guides](./how-to.md) and [Reference](./reference.md).

---

## 7. Start the run

Click the big **Start pipeline** button (or press **Ctrl + R**). A pre-flight dialog
appears summarizing what will run. Click **Start pipeline** again to confirm.

The browser navigates to the **run page** at `/runs/<your-file-stem>`. This is where
you will spend the next few minutes watching the work happen.

---

## 8. Watch the four phases

The run page shows a **phase stepper** across the top — Transcribe, Metadata, Render,
Upload — and a live log that streams from the running pipeline over Server-Sent
Events. A progress bar tracks the current phase. Here is what to expect:

1. **Transcribe** — WhisperX loads the model, transcribes your audio, aligns it at
   the word level, and labels speakers. This is usually the longest phase. As it
   finishes, a short transcript preview appears on the page.
2. **Metadata** — the local LLM on port 8080 reads the transcript and writes your
   YouTube title, description, tags, and chapters. Watch the metadata card on the
   right fill in.
3. **Render** — Remotion renders a 1920×1080 MP4 with your chosen audio visualizer.
   You will see a rising "Rendering NN%" in the log.
4. **Upload** — this stays **pending**, because we left "Skip upload" checked. You'll
   do it explicitly in a moment.

You can leave the page open and watch. The phase stepper and progress bar update on
their own as each phase completes.

> If a phase turns red (aborted), the run page shows which phase failed and the error
> tail. The most common first-run snag is the metadata phase failing because the
> local LLM server (step 2) isn't running — start it and re-run that phase from the
> phase stepper.

---

## 9. Preview the render

When the **Render** phase reaches *done*, the run page shows a **Rendered video ·
ready** card with an inline video player. Press play and watch your episode with its
visualizer and captions — right there in the browser, before anything leaves your
Mac.

The file itself lives at `output/<stem>/<stem>-dialogue.mp4`, listed next to the
preview.

---

## 10. Upload as private

Below the preview you'll see the **upload card** — "↑ Final phase — upload to
YouTube". This is the one network step in the whole pipeline, and it only happens
because you click the button.

1. Under **Visibility**, leave **Private** selected. (Unlisted is also available;
   Public is intentionally disabled here — you flip a video to public later from
   YouTube Studio.)
2. Click **Upload to YouTube**.

The upload runs as its own phase; you'll see its progress in the log. When it
finishes, the page switches to its **done** state and shows an **Open on YouTube ↗**
button linking to your new private video.

That's your first video — start to finish.

---

## What you just did

In one sitting you:

- installed the pipeline with `uv` and set up `ffmpeg`, the Remotion renderer, the
  local MLX metadata LLM, and YouTube OAuth;
- launched the WebGUI and picked a real audio file;
- ran all four phases — **transcribe → metadata → render → upload** — and watched
  each one stream live;
- previewed the rendered MP4 in the browser;
- uploaded it to YouTube as a **private** video, on your own explicit click.

Everything except that final upload ran entirely on your Mac.

## Next steps

- **[How-to guides](./how-to.md)** — task recipes: editing the transcript before
  rendering, pausing after transcribe, choosing visualizers, re-running a single
  phase, assigning playlists, working offline.
- **[Reference](./reference.md)** — every option, flag, route, environment variable,
  and output file, described precisely.
- **[Explanation](./explanation.md)** — why the pipeline is structured this way and
  why it runs locally.
- **[README](../../README.md)** — the project overview, including the CLI and the
  fallback TUI.
