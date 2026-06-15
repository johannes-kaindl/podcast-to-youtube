# Explanation — why the pipeline is shaped the way it is

This page is about *understanding*, not doing. If you want step-by-step
instructions, start from the [README](../../README.md); this document explains the
ideas behind the design: the four-phase architecture, why `run-state.json` is the
single resumable source of truth, why everything runs locally on Apple Silicon, why
the upload is never automatic, and how the transcript editor only reruns what an edit
actually invalidated.

## The four-phase architecture

A single audio file becomes a private YouTube video by passing through four phases,
in order:

1. **Transcribe** — WhisperX turns the audio into a word-level transcript
   (`<stem>.whisperx.json` plus `<stem>.srt` / `<stem>.txt`), optionally with speaker
   labels from diarization.
2. **Metadata** — a local LLM reads the transcript and writes the YouTube title,
   description, chapters and tags (`<stem>.youtube-meta.json` / `.md`).
3. **Render** — Remotion composes the audio and transcript into a 1920×1080 MP4 with
   a visualiser (`<stem>-<viz>.mp4`).
4. **Upload** — the YouTube Data API v3 publishes that MP4, as a private (or unlisted)
   video.

Why four discrete phases rather than one monolithic transform? Because each phase has
a fundamentally different cost, failure mode, and trust profile. Transcription is
minutes of GPU/Neural-Engine work; metadata generation is a single slow LLM call that
can produce malformed output; rendering is heavy Node/Remotion work that can crash;
upload is the one irreversible, network-facing, account-touching action. Keeping them
separate means each can be skipped, retried, or rerun on its own, and the boundary
between "everything so far was local and reversible" and "now we touch the outside
world" is drawn cleanly between phase 3 and phase 4.

The phases are also strictly *data-coupled*, not call-coupled: each writes files into
`output/<stem>/`, and the next reads them. Metadata reads the transcript files; render
reads the WhisperX JSON and SRT; upload reads the MP4 and the metadata JSON. This is
what makes resuming and partial reruns possible at all — a later phase doesn't need
the earlier phase's Python objects, only its files on disk.

## `run-state.json` as the resumable source of truth

Every run writes a `run-state.json` into its output directory. It is the durable
record of what happened, and it is deliberately the *only* thing the frontends consult
to decide what a run is and what can be done next. The orchestrator
(`pipeline.py`) treats each phase as a tiny state machine:

```
pending  → running → done       (succeeded)
                    → aborted    (raised an exception / subprocess exit ≠ 0)
pending  → skipped              (a skip flag was set; phase never entered)
```

A phase is marked `running` the moment it starts and `done` only after its outputs
exist; a crash or a non-zero subprocess exit flips it to `aborted` with the error
text attached. There is a subtle but important fourth case the file's own comments
call out: if the process is *killed externally* (closed terminal, OS kill) a phase can
be left stuck at `running`, because no finalising step ever ran. The state file is an
honest record of the last *transition that completed*, not a live heartbeat.

Writes are atomic — the state is written to a `.tmp` file and then `os.replace`d over
the real one — so a reader never sees a half-written file even if it polls during a
phase transition. Each transition also stamps `updated_at`, and preserves the prior
iteration's `started_at` instead of clobbering it, so timing survives reruns.

Because the file is the source of truth, *resuming is just reading it back*. The
orchestrator's `--skip-*` flags mean "this phase is already satisfied on disk, don't
redo it"; combined with the recorded statuses, a run can pick up wherever it left off
without any in-memory continuity. The trade-off is that the state file can drift from
reality if files are deleted by hand or a phase is stuck at `running` — the system
trusts the file, so manual surgery on `output/<stem>/` is effectively editing the
source of truth.

### Why the WebGUI derives a *variant* instead of storing one

The WebGUI never stores "this run is ready to upload" as a fact. Instead, each time
the run page loads, it *derives* a single display variant from the current phase
statuses, with a fixed precedence:

```
aborted  >  done  >  ready-to-upload  >  running
```

- **aborted** — any phase is `aborted`. The page shows the error and offers a retry.
- **done** — the upload phase is `done`. The video is live (privately) on YouTube.
- **ready-to-upload** — render is `done` but upload is not. The MP4 exists; the human
  decision is pending.
- **running** — something is `running`, *or* there are only pending phases with no
  active process (a partial-resume / "needs a nudge" situation, shown with a warning
  mood rather than an error).

This derive-don't-store choice is what keeps the UI honest. There is no separate
"status field" that can disagree with the phases; the variant is a pure function of
the phase map, so editing the transcript, rerunning a single phase, or a crash all
change what the page shows simply by changing the underlying statuses. The
run-history list applies the same principle: filters like *done*, *aborted*,
*unfinished* and *not-uploaded* are computed from the phase statuses across all runs,
never from a cached label.

## Why local-only, and why Apple Silicon

The hard rule of this project is that the *only* network call is the YouTube upload.
Transcription, metadata generation and rendering all run on the machine in front of
you. Three reasons drive that:

- **Privacy.** The full audio and the complete transcript — often unpublished, often
  containing things you have not decided to make public yet — never leave the machine.
  The only thing that crosses the network is the finished video you explicitly chose
  to upload.
- **Cost.** There is no per-minute transcription bill and no per-token LLM bill. Once
  the models are on disk (`download_models.py` pre-fetches them for fully offline use
  of phases 1–3), the marginal cost of a run is electricity and time.
- **The Neural Engine instead of a cloud LLM.** The metadata phase talks to a *local*
  MLX server on `http://localhost:8080/v1` over the OpenAI-compatible chat API — not a
  hosted model. MLX runs the quantised model on Apple Silicon's unified memory and
  Neural Engine, which is exactly why the project is Mac-only by design: the
  performance assumptions (and the long, patient 15-minute request timeout for long
  transcripts) are built around that hardware. Pointing `MLX_BASE_URL` / `MLX_MODEL`
  elsewhere is possible, but the design centre of gravity is "a model running on this
  Mac."

The trade-offs are real and chosen deliberately. You provide the hardware and the
local server; a cold first run pays the model-download cost; a cloud service would be
faster to start and would scale past one machine. The project trades all of that away
for keeping your data on your own silicon.

## Why the upload is never automatic

Phases 1–3 are local and reversible: delete the output directory and it's as if the
run never happened. Phase 4 is neither. It pushes a real video to a real Google
account through OAuth credentials you authorised once. That asymmetry is why upload is
treated as a separate *trust moment* rather than the natural tail of a pipeline run.

Concretely, the WebGUI's normal flow stops at **ready-to-upload** and waits. The human
then chooses the visibility (private or unlisted — never fully public from here) and
explicitly triggers the upload. On the CLI the same stance shows up as `--skip-upload`
being the safe, recommended habit, and the orchestrator additionally refuses to upload
unless a rendered video actually exists. Even the default privacy is `private`: the
design assumes you will review the result inside YouTube Studio before anyone else
sees it (the metadata phase even appends a post-upload checklist for exactly that
review). Making upload automatic would save one click while removing the one moment
where a human confirms that this video, with this title, should go to this account.
The project considers that a bad trade.

## The transcript-editor model: edit between phases, rerun only what changed

WhisperX is good but not perfect — it mistypes names, jargon and foreign words, and
diarization sometimes mislabels who spoke. The naive fix is to rerun the whole
pipeline. The expensive truth is that almost nothing downstream actually depends on
re-running *transcription* again; what's wrong is the transcript text, which you can
just correct.

So the editor sits *between* phases and operates on the transcript artifacts directly.
When you save an edit:

1. On the **first** save, a one-time pristine backup is written to
   `<stem>.whisperx.original.json`, so the original Whisper output is never lost. (The
   diff view compares current against this backup.)
2. Changed segments are marked `_edited: true`, and the `.srt` / `.txt` siblings are
   regenerated from the JSON in byte-for-byte the same format the transcription phase
   would have produced — so downstream phases can't tell an edited transcript from a
   freshly transcribed one.
3. Every mutation snapshots the prior state into `output/<stem>/snapshots/`, trimmed
   to the newest 20, which is what powers undo.

The interesting design decision is step four: **saving invalidates the meta and render
phases.** The editor resets those two phases from `done` back to `pending` in
`run-state.json` — and *only* those two. Transcription stays `done` (you just hand-fixed
its output; re-running Whisper would only undo your correction). Upload is
deliberately left untouched as well: V1 treats an edit as affecting transcript-derived
artifacts, and re-publishing to YouTube is the trust moment that must stay an explicit
human action, not a side-effect of fixing a typo.

Why invalidate via the state file rather than immediately re-running? Because of the
derive-don't-store principle above. Flipping meta and render to `pending` is all it
takes: the run page's variant recomputes, the metadata and video previews show as
stale/pending, and a single click re-runs just those phases. Under the hood, that
single-phase rerun is expressed by setting *all* the orchestrator's skip flags to true
except the one phase being run — the same `--skip-*` machinery that powers resume is
reused to power "rerun exactly this phase." So the chain is consistent: an edit
changes the transcript, the state file records that meta+render are no longer valid,
and only those phases recompute from the corrected transcript while the costly
transcription and the irreversible upload stay put.

The trade-off here is scope. The editor's invalidation is intentionally coarse —
*any* saved change invalidates the whole metadata and render phases, even if you only
fixed one word, because both phases read the transcript holistically (the LLM
summarises the whole thing; the renderer lays out every caption). It does not try to
patch the MP4 or the title in place; it reruns the cheap-enough downstream phases from
clean inputs. That keeps the model simple and the outputs trustworthy: what you see
always corresponds to the transcript as it is now, not a partially-patched mix.

---

See also: the [README](../../README.md) for setup and the full feature list, and the
other manual quadrants for tutorials, how-to guides and reference material.
