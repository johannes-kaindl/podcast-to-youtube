# Transkript-Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Browser-based editor for whisper transcripts — fix Whisper errors in names/jargon before Meta/Render run, without re-transcribing.

**Architecture:** Pure-Python `transcript_editor.py` module (load/save/regenerate/invalidate, no FastAPI dependency) + 2 new FastAPI routes (`GET`/`POST /runs/{stem}/edit`) + 1 new template (`run_edit.html`) + 1 new partial (`_partials/edit_cta.html`). Opt-in "pause after transcribe" reuses existing `--skip-meta/--skip-render/--skip-upload` flags via a new `pause_after_transcribe` field on `RunRequest`. Post-hoc edits set `meta`/`render` phases to `pending` so the existing click-to-restart-phase mechanic handles the re-run.

**Tech Stack:** Python 3.12, FastAPI/Starlette 1.0+, Jinja2, pytest, uv-managed venv at `.venv/`.

---

## File Structure

**Create:**
- `transcript_editor.py` (repo root) — pure-Python helpers
- `webgui/templates/run_edit.html` — editor page
- `webgui/templates/_partials/edit_cta.html` — buttons embedded in `run_detail.html`
- `tests/test_transcript_editor.py` — ~10 unit tests
- `tests/test_webgui_edit_routes.py` — ~6 route tests
- `tests/test_pause_after_transcribe.py` — ~3 settings/route tests
- `tests/fixtures/sample-transcript.whisperx.json` — 3-segment fixture
- `tests/fixtures/run-states/paused-after-transcribe.json` — paused-run fixture

**Modify:**
- `webgui/app.py` — add `RunRequest.pause_after_transcribe`, translate to skip-flags in `/api/runs`, add `GET`/`POST /runs/{stem}/edit` routes, expose `has_been_edited` and `is_paused` to run_detail template
- `webgui/settings.py` — extend `DEFAULTS` with `pause_after_transcribe: False`
- `webgui/templates/_partials/config_form.html` — add pause checkbox
- `webgui/templates/run_detail.html` — include `edit_cta.html`
- `AGENTS.md` — document new feature

**Do not modify:**
- `pipeline.py`, `transcribe.py`, `generate_meta.py`, `render_video.py`, `upload_youtube.py`
- `webgui/runner.py` (no changes needed — RunRequest translation happens in `/api/runs`)

---

## Conventions Reminder

- **TemplateResponse:** Starlette 1.0+ signature → `templates.TemplateResponse(request, name, context)` (request as first positional)
- **Tests:** Run from repo root with `VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_X.py -v`
- **Encoding:** UTF-8 everywhere; JSON writes use `ensure_ascii=False`
- **Commits:** Conventional commits (`feat(transcript-editor): …`, `test(transcript-editor): …`). Co-Authored-By footer for Claude commits.
- **Style:** Match existing module style (module docstring at top, type hints throughout)

---

## Task 1: transcript_editor.load_segments

**Files:**
- Create: `transcript_editor.py`
- Create: `tests/test_transcript_editor.py`
- Create: `tests/fixtures/sample-transcript.whisperx.json`

- [ ] **Step 1.1: Create the fixture**

Write `tests/fixtures/sample-transcript.whisperx.json`:

```json
{
  "segments": [
    {
      "start": 0.04,
      "end": 0.24,
      "text": " All right.",
      "words": [
        {"word": "All", "start": 0.04, "end": 0.1, "score": 0.0},
        {"word": "right.", "start": 0.12, "end": 0.24, "score": 0.375}
      ],
      "speaker": "SPEAKER_00"
    },
    {
      "start": 0.26,
      "end": 2.284,
      "text": "Let's dive into this autopoiesis thing.",
      "words": [
        {"word": "Let's", "start": 0.26, "end": 0.421, "score": 0.5}
      ],
      "speaker": "SPEAKER_01"
    },
    {
      "start": 2.5,
      "end": 4.0,
      "text": "Sounds good to me.",
      "words": [],
      "speaker": "SPEAKER_00"
    }
  ]
}
```

- [ ] **Step 1.2: Write the failing test**

Append to `tests/test_transcript_editor.py`:

```python
"""Tests for transcript_editor — pure-Python load/save/regenerate/invalidate."""
import json
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def sample_run(tmp_path, fixtures_dir):
    """Copy sample-transcript.whisperx.json into a fresh output dir as 'ep01'."""
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    src = fixtures_dir / "sample-transcript.whisperx.json"
    dst = run_dir / f"{stem}.whisperx.json"
    shutil.copy(src, dst)
    return {"dir": run_dir, "stem": stem, "json_path": dst}


def test_load_segments_returns_list_with_text_speaker_times(sample_run):
    from transcript_editor import load_segments
    segs = load_segments(str(sample_run["json_path"]))
    assert isinstance(segs, list)
    assert len(segs) == 3
    assert segs[0]["text"] == " All right."
    assert segs[0]["speaker"] == "SPEAKER_00"
    assert segs[0]["start"] == 0.04
    assert segs[0]["end"] == 0.24
    assert segs[1]["speaker"] == "SPEAKER_01"
    assert segs[2]["text"] == "Sounds good to me."


def test_load_segments_includes_edited_flag_default_false(sample_run):
    from transcript_editor import load_segments
    segs = load_segments(str(sample_run["json_path"]))
    # _edited defaults to False when not present in JSON
    assert segs[0].get("_edited", False) is False
    assert segs[1].get("_edited", False) is False
```

- [ ] **Step 1.3: Run test to verify it fails**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: FAIL with `ImportError` or `ModuleNotFoundError` for `transcript_editor`.

- [ ] **Step 1.4: Write minimal implementation**

Create `transcript_editor.py`:

```python
"""Transcript editor helpers — load, save, regenerate, invalidate.

Pure Python, no FastAPI dependency. Tested standalone in
tests/test_transcript_editor.py.
"""
import json
import shutil
from pathlib import Path


def load_segments(json_path: str) -> list[dict]:
    """Return the list of segments from a WhisperX JSON file.

    Each segment dict carries: start, end, text, speaker, words (list),
    _edited (bool, defaults False if absent).
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return data.get("segments", [])
```

- [ ] **Step 1.5: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 2 PASS.

- [ ] **Step 1.6: Commit**

```bash
git add transcript_editor.py tests/test_transcript_editor.py tests/fixtures/sample-transcript.whisperx.json
git commit -m "$(cat <<'EOF'
feat(transcript-editor): add load_segments helper + fixture

Pure-Python module loads WhisperX JSON segments for the editor UI.
3-segment fixture covers two speakers and a word-level structure.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: transcript_editor.save_edits — basic text update

**Files:**
- Modify: `transcript_editor.py`
- Modify: `tests/test_transcript_editor.py`

- [ ] **Step 2.1: Write the failing test**

Append to `tests/test_transcript_editor.py`:

```python
def test_save_edits_updates_text(sample_run):
    from transcript_editor import save_edits
    new_texts = ["Hello.", "Autopoiesis is fascinating.", "Sounds good to me."]
    result = save_edits(str(sample_run["json_path"]), new_texts)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["text"] == "Hello."
    assert data["segments"][1]["text"] == "Autopoiesis is fascinating."
    assert data["segments"][2]["text"] == "Sounds good to me."
    assert result["total_segments"] == 3


def test_save_edits_preserves_times_and_speakers(sample_run):
    from transcript_editor import save_edits
    new_texts = ["Hello.", "Autopoiesis is fascinating.", "Sounds good to me."]
    save_edits(str(sample_run["json_path"]), new_texts)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["start"] == 0.04
    assert data["segments"][0]["end"] == 0.24
    assert data["segments"][0]["speaker"] == "SPEAKER_00"
    assert data["segments"][1]["speaker"] == "SPEAKER_01"


def test_save_edits_raises_on_length_mismatch(sample_run):
    from transcript_editor import save_edits
    with pytest.raises(ValueError, match="length"):
        save_edits(str(sample_run["json_path"]), ["only one"])
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 3 FAIL (`save_edits` not defined).

- [ ] **Step 2.3: Add minimal implementation**

Append to `transcript_editor.py`:

```python
def save_edits(json_path: str, new_texts: list[str]) -> dict:
    """Update each segment's text from new_texts (parallel list).

    Returns: {"total_segments": int, "edited_count": int, "backup_created": bool}.
    Backup, SRT/TXT regeneration, and _edited-flag logic are added in later tasks.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    if len(new_texts) != len(segments):
        raise ValueError(
            f"new_texts length {len(new_texts)} != segments length {len(segments)}"
        )
    for seg, new_text in zip(segments, new_texts):
        seg["text"] = new_text
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "total_segments": len(segments),
        "edited_count": 0,
        "backup_created": False,
    }
```

- [ ] **Step 2.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 5 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add transcript_editor.py tests/test_transcript_editor.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): add save_edits — basic text update

Updates segment text in-place; preserves times, speakers, and words.
Backup-once and _edited-flag logic come in follow-up tasks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: transcript_editor.save_edits — _edited flag

**Files:**
- Modify: `transcript_editor.py`
- Modify: `tests/test_transcript_editor.py`

- [ ] **Step 3.1: Write the failing test**

Append to `tests/test_transcript_editor.py`:

```python
def test_save_edits_sets_edited_flag_when_text_differs(sample_run):
    from transcript_editor import save_edits
    new_texts = ["CHANGED.", "Let's dive into this autopoiesis thing.", "ALSO CHANGED."]
    result = save_edits(str(sample_run["json_path"]), new_texts)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["_edited"] is True
    assert data["segments"][1].get("_edited", False) is False  # unchanged → no flag
    assert data["segments"][2]["_edited"] is True
    assert result["edited_count"] == 2


def test_save_edits_does_not_set_edited_flag_when_text_same(sample_run):
    from transcript_editor import save_edits
    original = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    new_texts = [s["text"] for s in original["segments"]]
    result = save_edits(str(sample_run["json_path"]), new_texts)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    for seg in data["segments"]:
        assert seg.get("_edited", False) is False
    assert result["edited_count"] == 0


def test_has_been_edited_returns_true_when_any_segment_edited(sample_run):
    from transcript_editor import save_edits, has_been_edited
    assert has_been_edited(str(sample_run["json_path"])) is False
    save_edits(str(sample_run["json_path"]), ["CHANGED.", "Let's dive into this autopoiesis thing.", "Sounds good to me."])
    assert has_been_edited(str(sample_run["json_path"])) is True
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 3 FAIL.

- [ ] **Step 3.3: Update save_edits + add has_been_edited**

Replace the `save_edits` body in `transcript_editor.py` and append `has_been_edited`:

```python
def save_edits(json_path: str, new_texts: list[str]) -> dict:
    """Update each segment's text from new_texts (parallel list).

    Sets `_edited: true` on segments where the new text differs from the existing.
    Returns: {"total_segments": int, "edited_count": int, "backup_created": bool}.
    Backup and SRT/TXT regeneration are added in later tasks.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    if len(new_texts) != len(segments):
        raise ValueError(
            f"new_texts length {len(new_texts)} != segments length {len(segments)}"
        )
    edited_count = 0
    for seg, new_text in zip(segments, new_texts):
        if seg.get("text") != new_text:
            seg["text"] = new_text
            seg["_edited"] = True
            edited_count += 1
        # else: leave seg untouched (keep prior _edited flag if it was set)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "total_segments": len(segments),
        "edited_count": edited_count,
        "backup_created": False,
    }


def has_been_edited(json_path: str) -> bool:
    """Return True if any segment in the JSON has _edited: true."""
    path = Path(json_path)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return any(seg.get("_edited") for seg in data.get("segments", []))
```

- [ ] **Step 3.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 8 PASS.

- [ ] **Step 3.5: Commit**

```bash
git add transcript_editor.py tests/test_transcript_editor.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): mark edited segments with _edited flag

Only segments whose text actually changed get _edited: true.
has_been_edited() helper for UI badges and downstream checks.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: transcript_editor.save_edits — backup once

**Files:**
- Modify: `transcript_editor.py`
- Modify: `tests/test_transcript_editor.py`

- [ ] **Step 4.1: Write the failing test**

Append to `tests/test_transcript_editor.py`:

```python
def test_save_edits_creates_backup_on_first_call(sample_run):
    from transcript_editor import save_edits
    json_path = sample_run["json_path"]
    backup_path = json_path.with_name(json_path.stem.replace(".whisperx", "") + ".whisperx.original.json")
    assert not backup_path.exists()
    new_texts = ["Hello.", "Let's dive into this autopoiesis thing.", "Sounds good to me."]
    result = save_edits(str(json_path), new_texts)
    assert backup_path.exists()
    assert result["backup_created"] is True


def test_save_edits_backup_is_pristine_copy(sample_run):
    from transcript_editor import save_edits
    json_path = sample_run["json_path"]
    backup_path = json_path.with_name(json_path.stem.replace(".whisperx", "") + ".whisperx.original.json")
    original_content = json_path.read_text(encoding="utf-8")
    save_edits(str(json_path), ["CHANGED.", "Let's dive into this autopoiesis thing.", "Sounds good to me."])
    assert backup_path.read_text(encoding="utf-8") == original_content


def test_save_edits_does_not_overwrite_backup_on_second_call(sample_run):
    from transcript_editor import save_edits
    json_path = sample_run["json_path"]
    backup_path = json_path.with_name(json_path.stem.replace(".whisperx", "") + ".whisperx.original.json")
    save_edits(str(json_path), ["First.", "Let's dive into this autopoiesis thing.", "Sounds good to me."])
    first_backup_content = backup_path.read_text(encoding="utf-8")
    result = save_edits(str(json_path), ["Second.", "Let's dive into this autopoiesis thing.", "Sounds good to me."])
    assert backup_path.read_text(encoding="utf-8") == first_backup_content
    assert result["backup_created"] is False
```

- [ ] **Step 4.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 3 FAIL.

- [ ] **Step 4.3: Add backup logic**

Replace `save_edits` in `transcript_editor.py`:

```python
def _backup_path_for(json_path: Path) -> Path:
    """Given <stem>.whisperx.json, return <stem>.whisperx.original.json."""
    # json_path.stem strips only the LAST .json suffix → keep ".whisperx" intact
    return json_path.with_name(json_path.stem + ".original.json")


def save_edits(json_path: str, new_texts: list[str]) -> dict:
    """Update each segment's text from new_texts (parallel list).

    On first save, creates a one-time backup at <stem>.whisperx.original.json.
    Sets `_edited: true` on segments where the new text differs from the existing.
    Returns: {"total_segments": int, "edited_count": int, "backup_created": bool}.
    """
    path = Path(json_path)
    backup_path = _backup_path_for(path)
    backup_created = False
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
        backup_created = True

    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    if len(new_texts) != len(segments):
        raise ValueError(
            f"new_texts length {len(new_texts)} != segments length {len(segments)}"
        )
    edited_count = 0
    for seg, new_text in zip(segments, new_texts):
        if seg.get("text") != new_text:
            seg["text"] = new_text
            seg["_edited"] = True
            edited_count += 1
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "total_segments": len(segments),
        "edited_count": edited_count,
        "backup_created": backup_created,
    }
```

- [ ] **Step 4.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 11 PASS.

- [ ] **Step 4.5: Commit**

```bash
git add transcript_editor.py tests/test_transcript_editor.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): create one-time backup before first edit

Backup lives at <stem>.whisperx.original.json. Subsequent saves
do not overwrite it — Phase 2 diff-view will read from there.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: transcript_editor.regenerate_srt_txt

**Files:**
- Modify: `transcript_editor.py`
- Modify: `tests/test_transcript_editor.py`

- [ ] **Step 5.1: Write the failing test**

Append to `tests/test_transcript_editor.py`:

```python
def test_regenerate_srt_txt_writes_both_files(sample_run):
    from transcript_editor import regenerate_srt_txt
    json_path = sample_run["json_path"]
    srt_path, txt_path = regenerate_srt_txt(str(json_path))
    assert Path(srt_path).exists()
    assert Path(txt_path).exists()
    assert Path(srt_path).name == "ep01.srt"
    assert Path(txt_path).name == "ep01.txt"


def test_regenerate_srt_txt_srt_format(sample_run):
    from transcript_editor import regenerate_srt_txt
    srt_path, _ = regenerate_srt_txt(str(sample_run["json_path"]))
    content = Path(srt_path).read_text(encoding="utf-8")
    # First cue: index 1, [SPEAKER_00] prefix, the original text trimmed
    assert content.startswith("1\n")
    assert "[SPEAKER_00]" in content
    assert "All right." in content
    # Three cues total
    assert "\n3\n" in content


def test_regenerate_srt_txt_txt_groups_by_speaker(sample_run):
    from transcript_editor import regenerate_srt_txt
    _, txt_path = regenerate_srt_txt(str(sample_run["json_path"]))
    content = Path(txt_path).read_text(encoding="utf-8")
    assert "SPEAKER_00:" in content
    assert "SPEAKER_01:" in content
    assert "All right." in content


def test_save_edits_regenerates_srt_and_txt(sample_run):
    from transcript_editor import save_edits
    srt_path = sample_run["dir"] / "ep01.srt"
    txt_path = sample_run["dir"] / "ep01.txt"
    new_texts = ["Hello.", "Autopoiesis is fascinating.", "Sounds good to me."]
    save_edits(str(sample_run["json_path"]), new_texts)
    assert srt_path.exists()
    assert txt_path.exists()
    assert "Hello." in srt_path.read_text(encoding="utf-8")
    assert "Autopoiesis is fascinating." in txt_path.read_text(encoding="utf-8")
```

- [ ] **Step 5.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 4 FAIL.

- [ ] **Step 5.3: Add regenerate_srt_txt + wire into save_edits**

Append to `transcript_editor.py`:

```python
def _format_srt_time(seconds: float) -> str:
    """HH:MM:SS,mmm — matches transcribe.format_srt_time."""
    millis = int(round(seconds * 1000))
    h, rem = divmod(millis, 3600 * 1000)
    m, rem = divmod(rem, 60 * 1000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def regenerate_srt_txt(json_path: str) -> tuple[str, str]:
    """Rewrite <stem>.srt and <stem>.txt siblings from the JSON segments.

    Same format as transcribe.py — SRT carries [SPEAKER_id] prefix per cue,
    TXT groups consecutive same-speaker segments under a speaker header.
    Returns (srt_path, txt_path) as strings.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    # Strip ".whisperx" from path.stem to recover the base stem ("ep01.whisperx" → "ep01")
    base_stem = path.stem
    if base_stem.endswith(".whisperx"):
        base_stem = base_stem[: -len(".whisperx")]
    srt_path = path.parent / f"{base_stem}.srt"
    txt_path = path.parent / f"{base_stem}.txt"

    with srt_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            speaker = seg.get("speaker", "SPEAKER_00")
            text = f"[{speaker}] {seg['text'].strip()}"
            f.write(
                f"{i}\n"
                f"{_format_srt_time(seg['start'])} --> {_format_srt_time(seg['end'])}\n"
                f"{text}\n\n"
            )

    with txt_path.open("w", encoding="utf-8") as f:
        current_speaker = None
        for seg in segments:
            speaker = seg.get("speaker", "SPEAKER_00")
            if speaker != current_speaker:
                current_speaker = speaker
                f.write(f"\n{speaker}:\n")
            f.write(seg["text"].strip() + " ")
        f.write("\n")

    return str(srt_path), str(txt_path)
```

Then modify `save_edits` to call `regenerate_srt_txt` at the end (just before the `return`):

```python
    # Existing code in save_edits ends with path.write_text(...). After it:
    regenerate_srt_txt(str(path))
    return {
        "total_segments": len(segments),
        "edited_count": edited_count,
        "backup_created": backup_created,
    }
```

- [ ] **Step 5.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 15 PASS.

- [ ] **Step 5.5: Commit**

```bash
git add transcript_editor.py tests/test_transcript_editor.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): regenerate SRT + TXT siblings on save

Format matches transcribe.py exactly — Remotion + downstream readers see
no schema drift. save_edits triggers regeneration automatically.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: transcript_editor.invalidate_downstream

**Files:**
- Modify: `transcript_editor.py`
- Modify: `tests/test_transcript_editor.py`

- [ ] **Step 6.1: Write the failing test**

Append to `tests/test_transcript_editor.py`:

```python
@pytest.fixture
def sample_run_state(tmp_path):
    """A run-state.json fixture with all phases done."""
    state = {
        "schema_version": 1,
        "stem": "ep01",
        "phases": {
            "transcribe": {"status": "done", "finished_at": "2026-05-26T10:00:00Z"},
            "meta": {"status": "done", "finished_at": "2026-05-26T10:01:00Z"},
            "render": {"status": "done", "finished_at": "2026-05-26T10:05:00Z"},
            "upload": {"status": "skipped"},
        },
    }
    path = tmp_path / "run-state.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return path


def test_invalidate_downstream_resets_meta_render_to_pending(sample_run_state):
    from transcript_editor import invalidate_downstream
    invalidated = invalidate_downstream(str(sample_run_state))
    state = json.loads(sample_run_state.read_text(encoding="utf-8"))
    assert state["phases"]["meta"]["status"] == "pending"
    assert state["phases"]["render"]["status"] == "pending"
    assert "meta" in invalidated
    assert "render" in invalidated


def test_invalidate_downstream_leaves_transcribe_done(sample_run_state):
    from transcript_editor import invalidate_downstream
    invalidate_downstream(str(sample_run_state))
    state = json.loads(sample_run_state.read_text(encoding="utf-8"))
    assert state["phases"]["transcribe"]["status"] == "done"


def test_invalidate_downstream_leaves_upload_alone(sample_run_state):
    from transcript_editor import invalidate_downstream
    invalidate_downstream(str(sample_run_state))
    state = json.loads(sample_run_state.read_text(encoding="utf-8"))
    # upload was "skipped" — stays skipped (V1 doesn't invalidate upload)
    assert state["phases"]["upload"]["status"] == "skipped"


def test_invalidate_downstream_returns_empty_when_already_pending(sample_run_state):
    from transcript_editor import invalidate_downstream
    state = json.loads(sample_run_state.read_text(encoding="utf-8"))
    state["phases"]["meta"]["status"] = "pending"
    state["phases"]["render"]["status"] = "pending"
    sample_run_state.write_text(json.dumps(state, indent=2), encoding="utf-8")
    invalidated = invalidate_downstream(str(sample_run_state))
    assert invalidated == []
```

- [ ] **Step 6.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 4 FAIL.

- [ ] **Step 6.3: Add invalidate_downstream**

Append to `transcript_editor.py`:

```python
def invalidate_downstream(run_state_path: str) -> list[str]:
    """Reset meta + render phases to 'pending' if they were 'done'.

    Returns list of invalidated phase names. Upload is intentionally left
    alone — V1 treats edits as affecting transcript-derived artifacts only.
    """
    path = Path(run_state_path)
    if not path.exists():
        return []
    state = json.loads(path.read_text(encoding="utf-8"))
    phases = state.setdefault("phases", {})
    invalidated: list[str] = []
    for phase in ("meta", "render"):
        entry = phases.get(phase, {})
        if entry.get("status") == "done":
            phases[phase] = {"status": "pending"}
            invalidated.append(phase)
    if invalidated:
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return invalidated
```

- [ ] **Step 6.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_editor.py -v
```

Expected: 19 PASS.

- [ ] **Step 6.5: Sanity-check all existing tests still pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v
```

Expected: 81 PASS (62 existing + 19 new).

- [ ] **Step 6.6: Commit**

```bash
git add transcript_editor.py tests/test_transcript_editor.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): invalidate_downstream — reset meta + render to pending

Post-hoc edits trigger this — click-to-restart-phase then handles the
re-run. Upload phase is left alone (V1 scope: transcript-derived artifacts).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Settings — pause_after_transcribe field

**Files:**
- Modify: `webgui/settings.py`
- Modify: `tests/test_settings.py`

- [ ] **Step 7.1: Write the failing test**

Append to `tests/test_settings.py`:

```python
def test_default_pause_after_transcribe_is_false(tmp_path):
    from webgui.settings import load_settings
    s = load_settings(tmp_path / "nope.json")
    assert s["pause_after_transcribe"] is False


def test_pause_after_transcribe_persists(tmp_path):
    from webgui.settings import load_settings, save_settings
    p = tmp_path / "settings.json"
    save_settings(p, {"pause_after_transcribe": True})
    loaded = load_settings(p)
    assert loaded["pause_after_transcribe"] is True
```

- [ ] **Step 7.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_settings.py -v
```

Expected: 2 FAIL (`KeyError` on `pause_after_transcribe`).

- [ ] **Step 7.3: Add field to DEFAULTS**

In `webgui/settings.py`, update the `DEFAULTS` dict:

```python
DEFAULTS = {
    "theme": "dark",
    "tail_default": True,
    "preferred_visualizer": "dialogue",
    "preferred_model": "large-v3-turbo",
    "pause_after_transcribe": False,
}
```

- [ ] **Step 7.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_settings.py -v
```

Expected: 5 PASS (3 existing + 2 new).

- [ ] **Step 7.5: Commit**

```bash
git add webgui/settings.py tests/test_settings.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): add pause_after_transcribe setting (default false)

Persists via ~/.whisper-pipeline-ui.json. Surfaced as a checkbox in the
start-form; translated to --skip-meta/--skip-render/--skip-upload in
the /api/runs handler.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: API — RunRequest + /api/runs translates pause flag

**Files:**
- Modify: `webgui/app.py`
- Create: `tests/test_pause_after_transcribe.py`

- [ ] **Step 8.1: Write the failing test**

Create `tests/test_pause_after_transcribe.py`:

```python
"""Tests for pause-after-transcribe behavior in /api/runs."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from webgui.app import app
    return TestClient(app)


def test_run_request_accepts_pause_field(client, fixtures_dir, monkeypatch):
    """POST /api/runs with pause_after_transcribe=true should not 422."""
    # Block actual subprocess spawn — we only care about request validation
    from webgui import app as app_mod
    calls = []

    def fake_spawn_pipeline(**kwargs):
        calls.append(kwargs)
        class FakeJob:
            pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    r = client.post("/api/runs", json={
        "audio": str(fixtures_dir / "sample.m4a"),
        "viz": "dialogue", "language": "auto", "model": "tiny",
        "diarize": "off", "episode": "EP TEST", "show_name": "Signal",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": True,
        "pause_after_transcribe": True,
    }, follow_redirects=False)
    assert r.status_code in (303, 200), r.text
    # spawn_pipeline was called
    assert len(calls) == 1


def test_pause_flag_forces_skip_meta_render_upload(client, fixtures_dir, monkeypatch):
    """When pause=true, the spawned command must include skip flags."""
    from webgui import app as app_mod
    captured_cmd = []

    def fake_spawn_pipeline(cmd, **kwargs):
        captured_cmd.append(cmd)
        class FakeJob: pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    client.post("/api/runs", json={
        "audio": str(fixtures_dir / "sample.m4a"),
        "viz": "dialogue", "language": "auto", "model": "tiny",
        "diarize": "off", "episode": "EP TEST", "show_name": "Signal",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": False,
        "pause_after_transcribe": True,
    }, follow_redirects=False)
    assert len(captured_cmd) == 1
    cmd = captured_cmd[0]
    cmd_str = " ".join(cmd)
    assert "--skip-meta" in cmd_str
    assert "--skip-render" in cmd_str
    assert "--skip-upload" in cmd_str


def test_pause_flag_default_false_does_not_inject_skips(client, fixtures_dir, monkeypatch):
    """Without pause flag, skip flags follow the explicit request fields only."""
    from webgui import app as app_mod
    captured_cmd = []

    def fake_spawn_pipeline(cmd, **kwargs):
        captured_cmd.append(cmd)
        class FakeJob: pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    client.post("/api/runs", json={
        "audio": str(fixtures_dir / "sample.m4a"),
        "viz": "dialogue", "language": "auto", "model": "tiny",
        "diarize": "off", "episode": "EP TEST", "show_name": "Signal",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": False,
        "pause_after_transcribe": False,
    }, follow_redirects=False)
    cmd_str = " ".join(captured_cmd[0])
    assert "--skip-meta" not in cmd_str
    assert "--skip-render" not in cmd_str
    # skip_upload was False → no flag injected
    assert "--skip-upload" not in cmd_str
```

- [ ] **Step 8.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_pause_after_transcribe.py -v
```

Expected: 3 FAIL (422 validation error — RunRequest has no `pause_after_transcribe`).

- [ ] **Step 8.3: Add the field and translation logic in app.py**

In `webgui/app.py`, modify the `RunRequest` model:

```python
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
```

Then in `api_create_run`, after building `cfg` but before `build_command(cfg, REPO_ROOT)`, translate the pause flag:

```python
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
```

- [ ] **Step 8.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_pause_after_transcribe.py -v
```

Expected: 3 PASS.

- [ ] **Step 8.5: Sanity-check all existing tests still pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v
```

Expected: 84 PASS (81 + 3 new). If anything red — fix before moving on.

- [ ] **Step 8.6: Commit**

```bash
git add webgui/app.py tests/test_pause_after_transcribe.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): wire pause_after_transcribe into /api/runs

Translates the convenience flag to --skip-meta/--skip-render/--skip-upload.
Existing per-phase skip checkboxes still work independently — pause OR's
into them, never clears.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Config-form — pause-after-transcribe checkbox

**Files:**
- Modify: `webgui/templates/_partials/config_form.html`
- Modify: `webgui/templates/index.html` (only if it bootstraps settings JS — likely unchanged)
- Modify: `webgui/static/app.js` (if the form is serialized there — verify first)
- Add inline test via existing `test_routes.py`

- [ ] **Step 9.1: Inspect how the form is submitted (no test yet)**

Run:

```bash
grep -n "skip_upload\|skip_meta\|cfg-\|pause" webgui/static/app.js webgui/templates/index.html webgui/templates/_partials/config_form.html
```

If `app.js` reads `skip_upload` etc. by name and packages them into the JSON body, we MUST add `pause_after_transcribe` to that serialization. If app.js relies on a `FormData → JSON` generic conversion, no JS change is needed.

- [ ] **Step 9.2: Write the failing route test**

Append to `tests/test_routes.py`:

```python
def test_config_form_renders_pause_checkbox(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'name="pause_after_transcribe"' in r.text
    assert "Pause after transcribe" in r.text
```

- [ ] **Step 9.3: Run test to verify it fails**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_routes.py::test_config_form_renders_pause_checkbox -v
```

Expected: FAIL (text not in response).

- [ ] **Step 9.4: Add the checkbox to config_form.html**

In `webgui/templates/_partials/config_form.html`, add a new field row AFTER the existing "Skip phases" field (after line 56). Insert just before the closing `</form>`:

```html
  <div class="field field--full">
    <label class="field-label">Editing workflow</label>
    <div class="row" style="gap:24px; flex-wrap:wrap;">
      <label class="check"><input type="checkbox" name="pause_after_transcribe"><span class="box"></span><span>Pause after transcribe for editing</span></label>
    </div>
    <p class="muted" style="font-size: 12px; margin-top: 4px;">
      Pipeline stops after transcription. You'll edit the transcript in the browser,
      then click "Continue" to run Meta + Render with the corrected text.
    </p>
  </div>
```

- [ ] **Step 9.5: If app.js serializes the form by named field, add `pause_after_transcribe`**

Look at the result of Step 9.1's grep. If app.js builds the JSON body manually, add `pause_after_transcribe: form.pause_after_transcribe.checked` (or equivalent) so the field travels to `/api/runs`. If FormData-based, skip — the field will travel automatically.

- [ ] **Step 9.6: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v
```

Expected: 85 PASS.

- [ ] **Step 9.7: Commit**

```bash
git add webgui/templates/_partials/config_form.html webgui/static/app.js
git commit -m "$(cat <<'EOF'
feat(transcript-editor): expose pause-after-transcribe in start form

Checkbox under a new "Editing workflow" row. Help-text explains the
flow so users know what to expect after the run starts.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

(If app.js was unchanged, drop it from the `git add`.)

---

## Task 10: Editor — GET /runs/{stem}/edit

**Files:**
- Modify: `webgui/app.py`
- Create: `webgui/templates/run_edit.html`
- Create: `tests/test_webgui_edit_routes.py`

- [ ] **Step 10.1: Write the failing test**

Create `tests/test_webgui_edit_routes.py`:

```python
"""Tests for /runs/{stem}/edit GET + POST routes."""
import json
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from webgui.app import app
    return TestClient(app)


@pytest.fixture
def populated_run(tmp_path, fixtures_dir, monkeypatch):
    """Build a tmp OUTPUT_ROOT containing one stem 'ep01' with a transcript JSON
    and a minimal run-state.json."""
    out = tmp_path / "output"
    ep_dir = out / "ep01"
    ep_dir.mkdir(parents=True)
    shutil.copy(fixtures_dir / "sample-transcript.whisperx.json",
                ep_dir / "ep01.whisperx.json")
    state = {
        "schema_version": 1,
        "stem": "ep01",
        "audio": str(fixtures_dir / "sample.m4a"),
        "phases": {
            "transcribe": {"status": "done"},
            "meta": {"status": "done"},
            "render": {"status": "done"},
            "upload": {"status": "skipped"},
        },
        "config": {"skip_meta": False, "skip_render": False},
    }
    (ep_dir / "run-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    return out


def test_get_edit_renders_segments(client, populated_run):
    r = client.get("/runs/ep01/edit")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    # All three segment texts are rendered in textareas
    assert "All right." in r.text
    assert "autopoiesis" in r.text
    assert "Sounds good to me." in r.text
    # Speaker labels present
    assert "SPEAKER_00" in r.text
    assert "SPEAKER_01" in r.text


def test_get_edit_404_when_transcribe_missing(client, tmp_path, monkeypatch):
    out = tmp_path / "output"
    (out / "ghost").mkdir(parents=True)
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    r = client.get("/runs/ghost/edit")
    assert r.status_code == 404
```

- [ ] **Step 10.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_edit_routes.py -v
```

Expected: 2 FAIL (404 for both — routes not defined).

- [ ] **Step 10.3: Add the GET route**

In `webgui/app.py`, add this import at the top with the other imports:

```python
from transcript_editor import load_segments, save_edits, invalidate_downstream, has_been_edited
```

Then add the GET route (place near the other `/runs/{stem}/...` routes):

```python
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
```

- [ ] **Step 10.4: Create the editor template**

Create `webgui/templates/run_edit.html`:

```html
{% extends "base.html" %}
{% block title %}Edit · {{ stem }}{% endblock %}
{% block content %}
<header class="run-header">
  <div class="left">
    <div class="crumbs"><a href="/runs/{{ stem }}">← Back to run</a></div>
    <h1><span class="accent-mark">✎</span>Edit transcript: {{ stem }}</h1>
    <p class="muted" style="margin-top:8px; font-size: 13px;">
      Edit text only. Speaker labels and timecodes are preserved.
      Saving invalidates Meta + Render — they will need to re-run.
    </p>
    {% if backup_exists %}
      <p class="muted mono" style="font-size: 11px; margin-top:4px;">Original backup: ✓ saved</p>
    {% endif %}
  </div>
</header>

<form id="edit-form" method="post" action="/runs/{{ stem }}/edit" class="edit-form">
  {% for seg in segments %}
    <div class="edit-segment {% if seg.get('_edited') %}is-edited{% endif %}">
      <div class="edit-segment-header mono">
        <span class="time">{{ "%02d:%02d"|format((seg.start|int)//60, (seg.start|int)%60) }}</span>
        <span class="speaker">{{ seg.speaker | default("SPEAKER_00") }}</span>
        {% if seg.get('_edited') %}<span class="edit-badge">★ edited</span>{% endif %}
      </div>
      <textarea name="segment_text_{{ loop.index0 }}"
                class="edit-textarea"
                rows="2">{{ seg.text }}</textarea>
      <input type="hidden" name="original_text_{{ loop.index0 }}" value="{{ seg.text }}">
    </div>
  {% endfor %}

  <div class="edit-actions" style="margin-top: 24px; display:flex; gap:12px; flex-wrap:wrap;">
    <button type="submit" name="action" value="save-return" class="btn">Save & Return</button>
    <button type="submit" name="action" value="save-continue" class="btn btn-primary">Save & Continue</button>
    <a href="/runs/{{ stem }}" class="btn btn-ghost">Cancel</a>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 10.5: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_edit_routes.py -v
```

Expected: 2 PASS.

- [ ] **Step 10.6: Commit**

```bash
git add webgui/app.py webgui/templates/run_edit.html tests/test_webgui_edit_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): add GET /runs/{stem}/edit + run_edit.html

Reuses transcript_editor.load_segments. Renders each segment as a
named textarea with hidden 'original_text_N' for server-side diff.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Editor — POST /runs/{stem}/edit (save & return)

**Files:**
- Modify: `webgui/app.py`
- Modify: `tests/test_webgui_edit_routes.py`

- [ ] **Step 11.1: Write the failing test**

Append to `tests/test_webgui_edit_routes.py`:

```python
def test_post_edit_save_updates_json_and_redirects(client, populated_run):
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    form = {
        "segment_text_0": "All right!!",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-return",
    }
    r = client.post(f"/runs/ep01/edit", data=form, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/runs/ep01"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["segments"][0]["text"] == "All right!!"
    assert data["segments"][0].get("_edited") is True


def test_post_edit_save_invalidates_downstream(client, populated_run):
    state_path = populated_run / "ep01" / "run-state.json"
    form = {
        "segment_text_0": "Changed.",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-return",
    }
    client.post(f"/runs/ep01/edit", data=form, follow_redirects=False)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["phases"]["meta"]["status"] == "pending"
    assert state["phases"]["render"]["status"] == "pending"
    assert state["phases"]["transcribe"]["status"] == "done"


def test_post_edit_404_when_transcribe_missing(client, tmp_path, monkeypatch):
    out = tmp_path / "output"
    (out / "ghost").mkdir(parents=True)
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    r = client.post("/runs/ghost/edit", data={"action": "save-return"},
                    follow_redirects=False)
    assert r.status_code == 404
```

- [ ] **Step 11.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_edit_routes.py -v
```

Expected: 3 FAIL (POST not defined → 405 or 404).

- [ ] **Step 11.3: Add the POST route**

In `webgui/app.py`, append after `run_edit` (GET handler):

```python
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
```

- [ ] **Step 11.4: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_edit_routes.py -v
```

Expected: 5 PASS.

- [ ] **Step 11.5: Commit**

```bash
git add webgui/app.py tests/test_webgui_edit_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): add POST /runs/{stem}/edit — save & return

Parses segment_text_N form fields in order, calls save_edits +
invalidate_downstream, then redirects back to /runs/{stem}.
"Save & Continue" handled in next task (307 → phase/meta/start).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Editor — Save & Continue → kicks off Meta phase

**Files:**
- Modify: `tests/test_webgui_edit_routes.py`

This task is mostly verifying the previous task's `action == "save-continue"` branch already works end-to-end. We add a test that simulates the full flow.

- [ ] **Step 12.1: Write the failing test**

Append to `tests/test_webgui_edit_routes.py`:

```python
def test_post_edit_save_continue_triggers_meta_phase(client, populated_run, monkeypatch):
    """POST with action=save-continue should redirect (307) to
    /runs/{stem}/phase/meta/start, which then spawns the pipeline."""
    from webgui import app as app_mod
    calls = []

    def fake_spawn_pipeline(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        class FakeJob: pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    form = {
        "segment_text_0": "Changed.",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-continue",
    }
    r = client.post(f"/runs/ep01/edit", data=form, follow_redirects=True)
    # follow_redirects=True traverses 307 → phase/meta/start → 303 → /runs/ep01
    assert r.status_code == 200
    # spawn_pipeline was called for the meta phase
    assert len(calls) == 1
    cmd_str = " ".join(calls[0]["cmd"])
    # Meta phase runs ⇒ --skip-meta is NOT in the cmd; other skips ARE
    assert "--skip-meta" not in cmd_str
    assert "--skip-transcribe" in cmd_str
    assert "--skip-render" in cmd_str
    assert "--skip-upload" in cmd_str
```

- [ ] **Step 12.2: Run the test to verify it passes (or surfaces a bug)**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_edit_routes.py::test_post_edit_save_continue_triggers_meta_phase -v
```

Expected: PASS — the route logic from Task 11 already covers this. If it fails because of routing issues (e.g. 307 doesn't preserve form body), debug the redirect-status-code choice (307 vs 303). Phase-start route does NOT need form data — the URL is enough.

If it fails, switch the redirect in Task 11 from 307 to 303:

```python
        return RedirectResponse(
            url=f"/runs/{stem}/phase/meta/start",
            status_code=303,  # GET-safe — phase-start accepts POST but TestClient may convert
        )
```

Wait — `/runs/{stem}/phase/{phase}/start` accepts POST only. A 303 turns POST into GET, which will 405. So we keep 307 (preserves POST). If the test still fails, debug with verbose logging:

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_edit_routes.py::test_post_edit_save_continue_triggers_meta_phase -v -s
```

- [ ] **Step 12.3: Commit**

```bash
git add tests/test_webgui_edit_routes.py
git commit -m "$(cat <<'EOF'
test(transcript-editor): Save & Continue triggers meta-phase spawn

End-to-end test through 307 → POST /runs/{stem}/phase/meta/start,
verifying the spawned cmd skips transcribe/render/upload as expected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Edit-CTA — partial + integration into run_detail.html

**Files:**
- Create: `webgui/templates/_partials/edit_cta.html`
- Modify: `webgui/templates/run_detail.html`
- Modify: `webgui/app.py` (compute is_paused + edited_any in run_detail context)
- Modify: `tests/test_routes.py` (or a new `tests/test_edit_cta.py`)

- [ ] **Step 13.1: Write the failing tests**

Append to `tests/test_routes.py` (use `populated_output` fixture):

```python
def test_run_detail_shows_edit_cta_when_transcript_exists(client, populated_output, fixtures_dir):
    """Any run with transcribe.status=done and a .whisperx.json should expose the Edit CTA."""
    import shutil
    # Pick one of the existing fixture stems and add a whisperx.json
    target = populated_output / "folge-082"
    target.mkdir(exist_ok=True)
    shutil.copy(fixtures_dir / "sample-transcript.whisperx.json",
                target / "folge-082.whisperx.json")
    # Make sure the fixture's run-state has transcribe.done
    import json as _json
    state_path = target / "run-state.json"
    state = _json.loads(state_path.read_text(encoding="utf-8"))
    state.setdefault("phases", {})["transcribe"] = {"status": "done"}
    state_path.write_text(_json.dumps(state, indent=2), encoding="utf-8")

    r = client.get("/runs/folge-082")
    assert r.status_code == 200
    assert "Edit transcript" in r.text or "edit-transcript" in r.text.lower()


def test_run_detail_no_edit_cta_when_transcript_missing(client, populated_output):
    """Runs without a transcript JSON should not show the Edit CTA."""
    r = client.get("/runs/probefolge")  # aborted run, no transcript
    assert r.status_code == 200
    # If transcribe wasn't done, Edit-CTA must NOT appear
    assert "Edit transcript" not in r.text
```

- [ ] **Step 13.2: Run tests to verify they fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_routes.py -k "edit_cta" -v
```

Expected: FAIL (text not in response).

- [ ] **Step 13.3: Create the partial**

Create `webgui/templates/_partials/edit_cta.html`:

```html
{# Edit-CTA: rendered in run_detail when a transcript exists.
   Three visual modes:
     - paused:    pipeline stopped after Transcribe (config.skip_meta + transcribe.done + meta.pending)
     - editable:  transcribe done, post-hoc edits available
     - hidden:    no transcript JSON yet
#}
{% if transcript_exists %}
  {% if is_paused %}
    <section class="card" data-tone="neutral" style="margin-top: 16px;">
      <header class="card-header">
        <span class="caps">⏸ Pipeline paused after Transcribe</span>
      </header>
      <div class="card-body" style="display:flex; gap:12px; flex-wrap:wrap;">
        <a href="/runs/{{ stem }}/edit" class="btn btn-primary">📝 Edit Transcript</a>
        <form method="post" action="/runs/{{ stem }}/phase/meta/start" style="display:inline;">
          <button type="submit" class="btn">▶ Continue without editing</button>
        </form>
      </div>
    </section>
  {% else %}
    <div style="margin-top: 16px; display:flex; gap:8px; align-items:center;">
      <a href="/runs/{{ stem }}/edit" class="btn btn-ghost">✎ Edit transcript</a>
      {% if edited_any %}<span class="edit-badge mono">★ transcript edited</span>{% endif %}
    </div>
  {% endif %}
{% endif %}
```

- [ ] **Step 13.4: Update runs_detail handler to compute the new context fields**

In `webgui/app.py`, modify the `runs_detail` function. Add this block before `return templates.TemplateResponse(...)`:

```python
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
```

And add them to the context dict:

```python
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
```

- [ ] **Step 13.5: Include the partial in run_detail.html**

In `webgui/templates/run_detail.html`, AFTER `{% include "_partials/phase_indicator.html" %}` and BEFORE the `<div id="progress">` block, add:

```html
{% include "_partials/edit_cta.html" %}
```

- [ ] **Step 13.6: Run tests to verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v
```

Expected: all green (≥87 PASS).

- [ ] **Step 13.7: Commit**

```bash
git add webgui/app.py webgui/templates/run_detail.html webgui/templates/_partials/edit_cta.html tests/test_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor): wire Edit-CTA into run_detail

Three states:
- paused (skip_meta set, transcribe done, no active job) → big CTA
  with "Edit Transcript" + "Continue without editing"
- editable (transcribe done, transcript file exists) → small "Edit"
  link, plus "★ transcript edited" badge if any segment was changed
- hidden (no transcript yet)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Editor CSS (minimal styling)

**Files:**
- Modify: `webgui/static/style.css`

The editor template uses three new CSS hooks: `.edit-form`, `.edit-segment`, `.edit-segment-header`, `.edit-textarea`, `.edit-badge`, `.btn-primary`, `.btn-ghost`. Most exist already (button variants from the upload card and other pages). Verify, then add only what's missing.

- [ ] **Step 14.1: Inspect existing CSS for reusable classes**

```bash
grep -n "\.btn\b\|\.btn-\|\.card-header\|\.muted\|\.mono\|.caps\|\.row\b" webgui/static/style.css | head -50
```

- [ ] **Step 14.2: Add editor-specific styles**

Append to `webgui/static/style.css` (at the END of the file):

```css
/* === Transcript Editor ============================================== */

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 24px;
}

.edit-segment {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 14px;
  border-radius: var(--radius-md, 8px);
  background: color-mix(in oklab, var(--surface, #1a1a1a) 96%, var(--accent, #6ea8fe) 4%);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}

.edit-segment.is-edited {
  border-color: color-mix(in oklab, var(--accent, #6ea8fe) 50%, transparent);
  background: color-mix(in oklab, var(--surface, #1a1a1a) 92%, var(--accent, #6ea8fe) 8%);
}

.edit-segment-header {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 11px;
  color: var(--muted, rgba(255, 255, 255, 0.55));
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.edit-segment-header .time {
  font-variant-numeric: tabular-nums;
}

.edit-segment-header .speaker {
  color: var(--accent, #6ea8fe);
  font-weight: 500;
}

.edit-textarea {
  width: 100%;
  min-height: 2.4em;
  resize: vertical;
  background: var(--input-bg, #0e0e0e);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  color: var(--text, #e8e8e8);
  border-radius: var(--radius-sm, 6px);
  padding: 8px 10px;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.5;
  field-sizing: content;
}

.edit-textarea:focus-visible {
  outline: 2px solid var(--accent, #6ea8fe);
  outline-offset: 1px;
}

.edit-badge {
  display: inline-flex;
  align-items: center;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: color-mix(in oklab, var(--accent, #6ea8fe) 25%, transparent);
  color: var(--accent, #6ea8fe);
  letter-spacing: 0.04em;
}
```

- [ ] **Step 14.3: Verify CSS is served**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_routes.py::test_static_css_served -v
```

Expected: PASS (sanity — file is still valid).

- [ ] **Step 14.4: Commit**

```bash
git add webgui/static/style.css
git commit -m "$(cat <<'EOF'
style(transcript-editor): segment cards + edited-badge tokens

Reuses Kuro Signal Protocol surface/border/accent vars. is-edited
state tints with a subtle accent mix. Textarea uses field-sizing:
content for auto-grow (Safari/Chrome 2024+).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: AGENTS.md update

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 15.1: Update sections**

Open `AGENTS.md`. Make these changes:

1. In **"Architektur-Highlights"** section, add a bullet:

```markdown
- **Transcript-Editor.** `transcript_editor.py` (pure-Python) + `GET`/`POST /runs/{stem}/edit`. Two entry points: (1) opt-in pause-after-transcribe via start-form checkbox, (2) post-hoc edit link in run-detail. Save creates a one-time `<stem>.whisperx.original.json` backup, regenerates SRT + TXT, and resets `meta`/`render` to pending so click-to-restart-phase handles the re-run.
```

2. In **"Was im Repo NICHT existiert (Phase 2 oder später)"**, replace the line `- Transkript-Editor (Korrektur vor Re-Render)` with:

```markdown
- Word-Level-Edits + Speaker-Re-Labelling + Segment-Merge/Split + Diff-View + Undo-Stack (Transkript-Editor Phase 2)
```

3. In **"Wo finde ich was"** table, add rows:

```markdown
| Wo lebt der Editor? | `transcript_editor.py` + `webgui/templates/run_edit.html` |
| Routes für den Editor? | `GET`/`POST /runs/{stem}/edit` in `webgui/app.py` |
| Spec für Transkript-Editor V1? | `docs/superpowers/specs/2026-05-27-transcript-editor-design.md` |
| Plan für Transkript-Editor V1? | `docs/superpowers/plans/2026-05-27-transcript-editor.md` |
```

- [ ] **Step 15.2: Commit**

```bash
git add AGENTS.md
git commit -m "$(cat <<'EOF'
docs(transcript-editor): update AGENTS.md with V1 surface area

Editor entry-points, file paths, and Phase-2 roadmap moved to
"NOT yet implemented" with the V1 line removed.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: End-to-end manual test

Not a unit test — a human-in-the-loop verification.

- [ ] **Step 16.1: Start the webgui**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/python webgui.py
```

Wait for the browser to open at `http://localhost:8765`.

- [ ] **Step 16.2: Run a short test audio with pause enabled**

In the browser:
1. Pick `tests/fixtures/sample.m4a` (or `input/test-30s.wav` if available)
2. Set model to `tiny` (fast)
3. Set diarize to `Off`
4. Tick **`[x] Pause after transcribe for editing`**
5. Tick `[x] Skip upload` (default already)
6. Click Start

Wait until transcribe finishes. Page should land at `/runs/sample` (or equivalent stem) and show the paused-mode Edit-CTA card.

- [ ] **Step 16.3: Edit one segment, save & continue**

1. Click "📝 Edit Transcript"
2. Editor opens. Change one segment's text (e.g. add a typo or fix a name)
3. Click "Save & Continue"
4. You should land on `/runs/{stem}` and see meta + render running

Verify the produced `youtube-meta.json` reflects the edited text.

- [ ] **Step 16.4: Verify backup**

```bash
ls -la output/{stem}/{stem}.whisperx*.json
```

Should see both `{stem}.whisperx.json` AND `{stem}.whisperx.original.json`. Diff them:

```bash
diff <(jq -r '.segments[].text' output/{stem}/{stem}.whisperx.json) \
     <(jq -r '.segments[].text' output/{stem}/{stem}.whisperx.original.json)
```

Should show your edit.

- [ ] **Step 16.5: Test post-hoc edit**

1. Navigate to an old completed run (any from the runs list with transcribe done)
2. Click "✎ Edit transcript"
3. Edit a segment, click "Save & Return"
4. Land back at run-detail
5. Phase indicator should show meta + render as **pending**
6. Click on the meta phase icon to re-trigger the pipeline
7. Verify it re-runs and produces fresh meta + render

- [ ] **Step 16.6: Document any issues**

If anything is broken, capture in a comment block in the PR description and fix. If everything passed, proceed to merge.

---

## Task 17: PR / Merge to main

- [ ] **Step 17.1: Full test sweep**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v
```

All ≥84 tests must pass.

- [ ] **Step 17.2: git status review**

```bash
git status
git log --oneline main..feat/transcript-editor
```

Should show a clean working tree and ~16 commits on the branch.

- [ ] **Step 17.3: Merge or PR**

If the user prefers direct merge to main (per WebGUI shipping pattern):

```bash
git checkout main
git merge --no-ff feat/transcript-editor
git log --oneline -10
```

If a PR is preferred — defer to user (they have the GitHub/Codeberg context).

- [ ] **Step 17.4: Push (only if user explicitly authorizes)**

The "Executing actions with care" guidance applies. Ask before `git push`. The local merge alone is reversible; the push is not.

---

## Self-Review Notes

After writing this plan, verified:
- ✅ Every spec section maps to at least one task (load/save/regenerate/invalidate → Tasks 1-6; pause-flag → 7-9; editor UI → 10-12; CTA → 13; styling → 14; docs → 15; E2E → 16-17)
- ✅ No `TODO`, `TBD`, or "implement appropriate X" placeholders
- ✅ Type names consistent: `load_segments`, `save_edits`, `regenerate_srt_txt`, `invalidate_downstream`, `has_been_edited` — all used consistently across plan
- ✅ File paths absolute and correct (verified against current repo state)
- ✅ TDD discipline: red → minimal impl → green → commit, every task
- ✅ Bite-sized: each step is ~2-5 min of work, no step bundles "implement everything"
