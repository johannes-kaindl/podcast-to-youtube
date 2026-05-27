# Transkript-Editor Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the V1 transcript editor with Speaker-Re-Labelling, Merge/Split-Segments, Word-Level-Edits, Diff-View, and an Undo-Stack.

**Architecture:** Four new pure-Python modules (`transcript_segment_ops.py`, `transcript_word_ops.py`, `transcript_history.py`, `transcript_diff.py`) extend the existing `transcript_editor.py`. The WebGUI grows by ~8 routes (HTMX endpoints returning segment partials) and 3 templates. Every mutating route triggers `snapshot()` first, so all changes are undoable. SRT/TXT siblings are regenerated on every save; meta+render phases are invalidated downstream.

**Tech Stack:** Python 3.12, FastAPI/Starlette 1.0+, Jinja2, HTMX, pytest, uv-managed venv at `.venv/`, difflib (stdlib) for diff-view.

---

## File Structure

**Create:**
- `transcript_segment_ops.py` — `merge_segment`, `split_segment`, `change_speaker`, `bulk_rename_speaker`
- `transcript_word_ops.py` — `load_words_flat`, `save_word_edits`
- `transcript_history.py` — `snapshot`, `undo_last`, `list_history`, `cleanup_snapshots`, `SNAPSHOT_CAP = 20`
- `transcript_diff.py` — `compute_segment_diff` (word-level via `difflib.SequenceMatcher`)
- `webgui/templates/run_edit_words.html` — per-word editor
- `webgui/templates/run_diff.html` — diff view
- `webgui/templates/_partials/segment_editor.html` — HTMX target for re-renders
- `webgui/templates/_partials/history_dropdown.html` — undo + history list
- `webgui/templates/_partials/speaker_bulk_form.html` — bulk-rename form
- `tests/test_transcript_segment_ops.py` (~13 tests)
- `tests/test_transcript_word_ops.py` (~6)
- `tests/test_transcript_history.py` (~8)
- `tests/test_transcript_diff.py` (~5)
- `tests/test_webgui_phase2_routes.py` (~12)
- `tests/fixtures/sample-transcript-edited.whisperx.json` — fixture for diff tests (has `_edited`, `_speaker_edited`, `_merged_from`, history entries)

**Modify:**
- `webgui/app.py` — add imports + 8 new routes
- `webgui/templates/run_edit.html` — add top-bar (Diff/Words/Undo links), bulk-rename form, replace segment-block markup with `{% include "_partials/segment_editor.html" %}`
- `AGENTS.md` — document Phase 2 surface area

**Do not modify:**
- `transcript_editor.py` (V1 functions stay; new code goes in new modules)
- `pipeline.py`, `transcribe.py`, anything in the pipeline-execution layer

---

## Conventions Reminder

- **TemplateResponse:** Starlette 1.0+ signature → `templates.TemplateResponse(request, name, context)` (request as first positional)
- **Tests:** `VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v`
- **Encoding:** UTF-8, JSON with `ensure_ascii=False`
- **Commits:** Conventional (`feat(transcript-editor-phase2): …`), Co-Authored-By footer
- **Style:** Module docstring at top; type hints throughout

---

## Setup

- [ ] **Step 0.1: Verify baseline**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: `97 passed`. If lower, stop and report.

- [ ] **Step 0.2: Ensure feature branch**

```bash
git status
git branch --show-current
```

Expected: clean working tree, on `feat/transcript-editor-phase2` branch. If not, switch:

```bash
git checkout feat/transcript-editor-phase2
```

---

## Task 1: change_speaker

**Files:**
- Create: `transcript_segment_ops.py`
- Create: `tests/test_transcript_segment_ops.py`

- [ ] **Step 1.1: Write failing test**

Create `tests/test_transcript_segment_ops.py`:

```python
"""Tests for transcript_segment_ops — merge, split, speaker change, bulk rename."""
import json
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def sample_run(tmp_path, fixtures_dir):
    """Copy sample-transcript.whisperx.json into a fresh output dir."""
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    src = fixtures_dir / "sample-transcript.whisperx.json"
    dst = run_dir / f"{stem}.whisperx.json"
    shutil.copy(src, dst)
    return {"dir": run_dir, "stem": stem, "json_path": dst}


def test_change_speaker_updates_segment(sample_run):
    from transcript_segment_ops import change_speaker
    change_speaker(str(sample_run["json_path"]), 0, "Anna")
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["speaker"] == "Anna"
    assert data["segments"][0]["_speaker_edited"] is True


def test_change_speaker_noop_when_same(sample_run):
    from transcript_segment_ops import change_speaker
    original = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    original_speaker = original["segments"][1]["speaker"]
    change_speaker(str(sample_run["json_path"]), 1, original_speaker)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # _speaker_edited should NOT be set when value is unchanged
    assert data["segments"][1].get("_speaker_edited", False) is False


def test_change_speaker_raises_on_empty(sample_run):
    from transcript_segment_ops import change_speaker
    with pytest.raises(ValueError, match="speaker"):
        change_speaker(str(sample_run["json_path"]), 0, "")
```

- [ ] **Step 1.2: Run, verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 3 FAIL (ImportError).

- [ ] **Step 1.3: Implement**

Create `transcript_segment_ops.py`:

```python
"""Segment-level operations: merge, split, change_speaker, bulk_rename_speaker.

All operations work on the WhisperX JSON in-place and regenerate SRT/TXT
siblings via transcript_editor.regenerate_srt_txt.
"""
import json
from pathlib import Path

from transcript_editor import regenerate_srt_txt


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _save(json_path: str, data: dict) -> None:
    Path(json_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def change_speaker(json_path: str, segment_index: int, new_speaker: str) -> None:
    """Change segment speaker; sets _speaker_edited flag if value changed.

    Raises ValueError on empty new_speaker or out-of-range index.
    """
    if not new_speaker or not new_speaker.strip():
        raise ValueError("speaker name must be non-empty")
    if len(new_speaker) > 64:
        raise ValueError("speaker name too long (max 64 chars)")
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments):
        raise ValueError(f"segment_index {segment_index} out of range")
    seg = segments[segment_index]
    if seg.get("speaker") == new_speaker:
        return  # no-op
    seg["speaker"] = new_speaker
    seg["_speaker_edited"] = True
    _save(json_path, data)
    regenerate_srt_txt(json_path)
```

- [ ] **Step 1.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 3 PASS.

- [ ] **Step 1.5: Commit**

```bash
git add transcript_segment_ops.py tests/test_transcript_segment_ops.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add change_speaker — per-segment + flag

Sets _speaker_edited only when the value actually changes. Empty names
and >64 chars raise ValueError. SRT/TXT regenerated after change.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: bulk_rename_speaker

**Files:**
- Modify: `transcript_segment_ops.py`
- Modify: `tests/test_transcript_segment_ops.py`

- [ ] **Step 2.1: Write failing tests**

Append:

```python
def test_bulk_rename_speaker_renames_all_matching(sample_run):
    from transcript_segment_ops import bulk_rename_speaker
    # Fixture has SPEAKER_00 (segs 0, 2) and SPEAKER_01 (seg 1)
    count = bulk_rename_speaker(str(sample_run["json_path"]), "SPEAKER_00", "Anna")
    assert count == 2
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["speaker"] == "Anna"
    assert data["segments"][1]["speaker"] == "SPEAKER_01"
    assert data["segments"][2]["speaker"] == "Anna"


def test_bulk_rename_speaker_does_not_set_flag(sample_run):
    from transcript_segment_ops import bulk_rename_speaker
    bulk_rename_speaker(str(sample_run["json_path"]), "SPEAKER_00", "Anna")
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # Bulk-rename is a display change, not a diarization fix → no _speaker_edited
    for seg in data["segments"]:
        if seg["speaker"] == "Anna":
            assert seg.get("_speaker_edited", False) is False


def test_bulk_rename_speaker_raises_on_same_names(sample_run):
    from transcript_segment_ops import bulk_rename_speaker
    with pytest.raises(ValueError, match="differ"):
        bulk_rename_speaker(str(sample_run["json_path"]), "SPEAKER_00", "SPEAKER_00")


def test_bulk_rename_speaker_returns_zero_when_no_match(sample_run):
    from transcript_segment_ops import bulk_rename_speaker
    count = bulk_rename_speaker(str(sample_run["json_path"]), "SPEAKER_99", "Whoever")
    assert count == 0
```

- [ ] **Step 2.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 4 FAIL.

- [ ] **Step 2.3: Implement**

Append to `transcript_segment_ops.py`:

```python
def bulk_rename_speaker(json_path: str, old_name: str, new_name: str) -> int:
    """Rename every segment whose speaker == old_name to new_name.

    Does NOT set _speaker_edited (this is a display rename, not a diarization fix).
    Returns the count of renamed segments.
    """
    if not old_name or not new_name:
        raise ValueError("both names must be non-empty")
    if old_name == new_name:
        raise ValueError("old and new names must differ")
    if len(new_name) > 64:
        raise ValueError("new name too long (max 64 chars)")
    data = _load(json_path)
    count = 0
    for seg in data.get("segments", []):
        if seg.get("speaker") == old_name:
            seg["speaker"] = new_name
            count += 1
    if count > 0:
        _save(json_path, data)
        regenerate_srt_txt(json_path)
    return count
```

- [ ] **Step 2.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 7 PASS.

- [ ] **Step 2.5: Commit**

```bash
git add transcript_segment_ops.py tests/test_transcript_segment_ops.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add bulk_rename_speaker

Renames all segments matching old_name → new_name. Returns count.
Intentionally does NOT set _speaker_edited (display-rename only,
not a diarization correction).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: merge_segment

**Files:**
- Modify: `transcript_segment_ops.py`
- Modify: `tests/test_transcript_segment_ops.py`

- [ ] **Step 3.1: Write failing tests**

Append:

```python
def test_merge_segment_combines_text_and_words(sample_run):
    from transcript_segment_ops import merge_segment
    original = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    original_text_0 = original["segments"][0]["text"]
    original_text_1 = original["segments"][1]["text"]
    words_0_len = len(original["segments"][0]["words"])
    words_1_len = len(original["segments"][1]["words"])

    merge_segment(str(sample_run["json_path"]), 0)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert len(data["segments"]) == 2  # was 3
    assert data["segments"][0]["text"] == original_text_0 + " " + original_text_1
    assert len(data["segments"][0]["words"]) == words_0_len + words_1_len


def test_merge_segment_extends_end_time(sample_run):
    from transcript_segment_ops import merge_segment
    original = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    original_start_0 = original["segments"][0]["start"]
    original_end_1 = original["segments"][1]["end"]

    merge_segment(str(sample_run["json_path"]), 0)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["start"] == original_start_0
    assert data["segments"][0]["end"] == original_end_1


def test_merge_segment_sets_merged_from_flag(sample_run):
    from transcript_segment_ops import merge_segment
    merge_segment(str(sample_run["json_path"]), 0)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["_merged_from"] == [0, 1]


def test_merge_segment_raises_when_no_next(sample_run):
    from transcript_segment_ops import merge_segment
    # last segment (index 2) has no successor
    with pytest.raises(ValueError, match="no next"):
        merge_segment(str(sample_run["json_path"]), 2)
```

- [ ] **Step 3.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 4 FAIL.

- [ ] **Step 3.3: Implement**

Append to `transcript_segment_ops.py`:

```python
def merge_segment(json_path: str, segment_index: int) -> None:
    """Merge segments[index] with segments[index+1] in-place.

    The combined text uses single-space join. words are concatenated.
    Resulting segment has start=current.start, end=next.end,
    speaker=current.speaker. Sets _merged_from = [index, index+1].
    Clears _split_from (mutually exclusive with merged_from).

    Raises ValueError if index has no successor.
    """
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments) - 1:
        raise ValueError(f"segment {segment_index}: no next segment to merge with")
    curr = segments[segment_index]
    nxt = segments[segment_index + 1]
    merged = {
        "start": curr["start"],
        "end": nxt["end"],
        "text": curr["text"] + " " + nxt["text"],
        "speaker": curr.get("speaker", "SPEAKER_00"),
        "words": curr.get("words", []) + nxt.get("words", []),
        "_merged_from": [segment_index, segment_index + 1],
    }
    # Carry over edit flags from curr (preserves "user touched this" history)
    for flag in ("_edited", "_speaker_edited"):
        if curr.get(flag):
            merged[flag] = True
    segments[segment_index:segment_index + 2] = [merged]
    _save(json_path, data)
    regenerate_srt_txt(json_path)
```

- [ ] **Step 3.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 11 PASS.

- [ ] **Step 3.5: Commit**

```bash
git add transcript_segment_ops.py tests/test_transcript_segment_ops.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add merge_segment

Combines segments[i] and segments[i+1]. Single-space text join, word
list concatenation, time extension to next.end. _merged_from is a
list of the two original indices (pre-merge). Carries over _edited
and _speaker_edited from the current segment.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: split_segment

**Files:**
- Modify: `transcript_segment_ops.py`
- Modify: `tests/test_transcript_segment_ops.py`

- [ ] **Step 4.1: Write failing tests**

Append:

```python
def test_split_segment_creates_two_segments(sample_run):
    from transcript_segment_ops import split_segment
    # Segment 1 text: "Let's dive into this autopoiesis thing."
    # Split at position 16 (after "Let's dive into ")
    split_segment(str(sample_run["json_path"]), 1, 16)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert len(data["segments"]) == 4  # was 3
    assert data["segments"][1]["text"].strip() == "Let's dive into"
    assert data["segments"][2]["text"].strip() == "this autopoiesis thing."


def test_split_segment_interpolates_times(sample_run):
    from transcript_segment_ops import split_segment
    original = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    seg_1 = original["segments"][1]
    original_start = seg_1["start"]
    original_end = seg_1["end"]
    # Split at char position equal to half the text length (no words to refine to)
    text_len = len(seg_1["text"])
    split_segment(str(sample_run["json_path"]), 1, text_len // 2)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # The two new segments' boundary should be somewhere between original start and end
    assert data["segments"][1]["start"] == original_start
    assert data["segments"][2]["end"] == original_end
    assert data["segments"][1]["end"] == data["segments"][2]["start"]
    assert original_start < data["segments"][1]["end"] < original_end


def test_split_segment_sets_split_from_flag(sample_run):
    from transcript_segment_ops import split_segment
    split_segment(str(sample_run["json_path"]), 1, 16)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][1]["_split_from"] == 1
    assert data["segments"][2]["_split_from"] == 1


def test_split_segment_raises_at_text_boundary_zero(sample_run):
    from transcript_segment_ops import split_segment
    with pytest.raises(ValueError, match="position"):
        split_segment(str(sample_run["json_path"]), 1, 0)


def test_split_segment_raises_at_text_boundary_end(sample_run):
    from transcript_segment_ops import split_segment
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    text_len = len(data["segments"][1]["text"])
    with pytest.raises(ValueError, match="position"):
        split_segment(str(sample_run["json_path"]), 1, text_len)


def test_split_segment_splits_words_by_time(sample_run):
    from transcript_segment_ops import split_segment
    # Segment 0 has words [All(0.04-0.1), right.(0.12-0.24)]
    # Split at position 4 (after "All ")
    split_segment(str(sample_run["json_path"]), 0, 4)
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # First new segment should have only the first word
    assert len(data["segments"][0]["words"]) == 1
    assert data["segments"][0]["words"][0]["word"] == "All"
    # Second new segment should have the second word
    assert len(data["segments"][1]["words"]) == 1
    assert data["segments"][1]["words"][0]["word"] == "right."
```

- [ ] **Step 4.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 6 FAIL.

- [ ] **Step 4.3: Implement**

Append to `transcript_segment_ops.py`:

```python
def split_segment(json_path: str, segment_index: int, char_position: int) -> None:
    """Split segments[index] into two at char_position.

    text_left = text[:char_position].rstrip()
    text_right = text[char_position:].lstrip()
    Both must be non-empty → ValueError otherwise.

    Time split: linear interpolation by char_position / len(text).
    If words list is present, refine split-time to the start of the first
    word whose start >= interpolated time (avoids splitting mid-word).

    Both new segments inherit _split_from = original_index.
    """
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments):
        raise ValueError(f"segment_index {segment_index} out of range")
    seg = segments[segment_index]
    text = seg["text"]
    if char_position <= 0 or char_position >= len(text):
        raise ValueError(
            f"char_position {char_position} must be between 1 and {len(text) - 1}"
        )
    text_left = text[:char_position].rstrip()
    text_right = text[char_position:].lstrip()
    if not text_left or not text_right:
        raise ValueError(
            "split position would create empty segment after whitespace trim"
        )

    start = seg["start"]
    end = seg["end"]
    # Linear interpolation by char-position ratio
    split_time = start + (end - start) * (char_position / len(text))
    # Word-aware refinement if words exist
    words = seg.get("words", [])
    if words:
        # First word whose start >= split_time becomes the right segment's first word
        for w in words:
            if w.get("start", start) >= split_time:
                split_time = w["start"]
                break
    words_left = [w for w in words if w.get("start", start) < split_time]
    words_right = [w for w in words if w.get("start", start) >= split_time]

    left = {
        "start": start, "end": split_time, "text": text_left,
        "speaker": seg.get("speaker", "SPEAKER_00"),
        "words": words_left,
        "_split_from": segment_index,
    }
    right = {
        "start": split_time, "end": end, "text": text_right,
        "speaker": seg.get("speaker", "SPEAKER_00"),
        "words": words_right,
        "_split_from": segment_index,
    }
    # Carry edit flags onto the left half (preserves "I edited this" history)
    for flag in ("_edited", "_speaker_edited"):
        if seg.get(flag):
            left[flag] = True

    segments[segment_index:segment_index + 1] = [left, right]
    _save(json_path, data)
    regenerate_srt_txt(json_path)
```

- [ ] **Step 4.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_segment_ops.py -v
```

Expected: 17 PASS.

- [ ] **Step 4.5: Sanity-check existing tests**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: 114 PASS (97 existing + 17 new).

- [ ] **Step 4.6: Commit**

```bash
git add transcript_segment_ops.py tests/test_transcript_segment_ops.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add split_segment

Splits a segment at a char position. Time is linearly interpolated and
refined to a word boundary when words[] is present. Both halves get
_split_from = original_index. Empty halves after whitespace trim raise
ValueError.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: snapshot + cleanup_snapshots

**Files:**
- Create: `transcript_history.py`
- Create: `tests/test_transcript_history.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_transcript_history.py`:

```python
"""Tests for transcript_history — snapshot, undo_last, cleanup."""
import json
import shutil
import time
from pathlib import Path
import pytest


@pytest.fixture
def sample_run(tmp_path, fixtures_dir):
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    src = fixtures_dir / "sample-transcript.whisperx.json"
    dst = run_dir / f"{stem}.whisperx.json"
    shutil.copy(src, dst)
    return {"dir": run_dir, "stem": stem, "json_path": dst}


def test_snapshot_creates_file(sample_run):
    from transcript_history import snapshot
    snap_path = snapshot(str(sample_run["json_path"]), action="edit_text", metric="1 segment edited")
    assert Path(snap_path).exists()
    # File should be a sibling under snapshots/
    assert "snapshots" in str(snap_path)


def test_snapshot_content_matches_pre_mutation(sample_run):
    from transcript_history import snapshot
    pre_content = sample_run["json_path"].read_text(encoding="utf-8")
    snap_path = snapshot(str(sample_run["json_path"]), action="edit_text", metric="x")
    # Snapshot file must contain the PRE-mutation state (caller hasn't mutated yet)
    assert Path(snap_path).read_text(encoding="utf-8") == pre_content


def test_snapshot_appends_history_entry(sample_run):
    from transcript_history import snapshot
    snapshot(str(sample_run["json_path"]), action="edit_text", metric="1 segment edited")
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    history = data.get("_history", [])
    assert len(history) == 1
    assert history[0]["action"] == "edit_text"
    assert history[0]["metric"] == "1 segment edited"
    assert "ts" in history[0]
    assert "snapshot" in history[0]


def test_snapshot_history_path_is_relative(sample_run):
    from transcript_history import snapshot
    snap_path = snapshot(str(sample_run["json_path"]), action="merge", metric="0+1")
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # Stored path should be relative to output dir: "snapshots/<ts>.json"
    rel = data["_history"][-1]["snapshot"]
    assert rel.startswith("snapshots/")
    assert rel.endswith(".json")


def test_cleanup_snapshots_keeps_cap(sample_run, monkeypatch):
    from transcript_history import snapshot, cleanup_snapshots, SNAPSHOT_CAP
    # Force a small cap for the test
    monkeypatch.setattr("transcript_history.SNAPSHOT_CAP", 3)
    for i in range(5):
        snapshot(str(sample_run["json_path"]), action="x", metric=f"{i}")
        time.sleep(0.01)  # ensure ts ordering
    cleanup_snapshots(str(sample_run["json_path"]))
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # Only 3 history entries should remain
    assert len(data["_history"]) == 3
    # Corresponding snapshot files: also 3
    snap_dir = sample_run["dir"] / "snapshots"
    assert len(list(snap_dir.glob("*.json"))) == 3
```

- [ ] **Step 5.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_history.py -v
```

Expected: 5 FAIL.

- [ ] **Step 5.3: Implement**

Create `transcript_history.py`:

```python
"""Snapshots + undo stack for transcript edits.

Each mutating operation calls snapshot() BEFORE the mutation, capturing
the pre-mutation JSON. _history[] in the main JSON references each
snapshot. cleanup_snapshots enforces SNAPSHOT_CAP.
"""
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_CAP = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _save(json_path: str, data: dict) -> None:
    Path(json_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def snapshot(json_path: str, action: str, metric: str) -> str:
    """Save a pre-mutation snapshot and append a _history entry.

    Returns absolute path to the snapshot file.
    Snapshot is written BEFORE the caller mutates json_path, so it reflects
    the state to revert TO if undone.
    """
    path = Path(json_path)
    snap_dir = path.parent / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    # Use nanosecond-precision timestamp so rapid successive snapshots don't collide
    ts = int(time.time() * 1000)
    snap_file = snap_dir / f"{ts}.json"
    # Ensure unique filename if same ms-tick
    while snap_file.exists():
        ts += 1
        snap_file = snap_dir / f"{ts}.json"
    shutil.copy2(path, snap_file)

    data = _load(json_path)
    data.setdefault("_history", []).append({
        "ts": _now_iso(),
        "action": action,
        "metric": metric,
        "snapshot": f"snapshots/{snap_file.name}",
    })
    _save(json_path, data)
    return str(snap_file)


def cleanup_snapshots(json_path: str) -> int:
    """Delete oldest snapshots beyond SNAPSHOT_CAP. Returns count deleted."""
    data = _load(json_path)
    history = data.get("_history", [])
    if len(history) <= SNAPSHOT_CAP:
        return 0
    excess = len(history) - SNAPSHOT_CAP
    to_remove = history[:excess]
    parent = Path(json_path).parent
    deleted = 0
    for entry in to_remove:
        snap_rel = entry.get("snapshot", "")
        if snap_rel:
            snap_path = parent / snap_rel
            if snap_path.exists():
                snap_path.unlink()
                deleted += 1
    data["_history"] = history[excess:]
    _save(json_path, data)
    return deleted
```

- [ ] **Step 5.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_history.py -v
```

Expected: 5 PASS.

- [ ] **Step 5.5: Commit**

```bash
git add transcript_history.py tests/test_transcript_history.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add snapshot + cleanup_snapshots

Each snapshot copies the pre-mutation JSON to output/{stem}/snapshots/
and appends a _history entry with action, metric, ts, snapshot path.
cleanup_snapshots enforces SNAPSHOT_CAP=20 by deleting oldest first.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: undo_last + list_history

**Files:**
- Modify: `transcript_history.py`
- Modify: `tests/test_transcript_history.py`

- [ ] **Step 6.1: Write failing tests**

Append:

```python
def test_undo_last_restores_pre_mutation_state(sample_run):
    from transcript_history import snapshot, undo_last
    pre_content = sample_run["json_path"].read_text(encoding="utf-8")
    snapshot(str(sample_run["json_path"]), action="edit_text", metric="1 changed")
    # Simulate a mutation: alter segment 0's text
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    data["segments"][0]["text"] = "CHANGED."
    sample_run["json_path"].write_text(json.dumps(data, indent=2), encoding="utf-8")

    entry = undo_last(str(sample_run["json_path"]))
    assert entry is not None
    assert entry["action"] == "edit_text"
    # Content should match pre-snapshot state
    restored = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert restored["segments"][0]["text"] != "CHANGED."


def test_undo_last_deletes_snapshot_file(sample_run):
    from transcript_history import snapshot, undo_last
    snap_path = snapshot(str(sample_run["json_path"]), action="x", metric="y")
    assert Path(snap_path).exists()
    undo_last(str(sample_run["json_path"]))
    assert not Path(snap_path).exists()


def test_undo_last_returns_none_when_empty(sample_run):
    from transcript_history import undo_last
    entry = undo_last(str(sample_run["json_path"]))
    assert entry is None


def test_list_history_returns_entries_newest_last(sample_run):
    from transcript_history import snapshot, list_history
    snapshot(str(sample_run["json_path"]), action="a", metric="1")
    time.sleep(0.01)
    snapshot(str(sample_run["json_path"]), action="b", metric="2")
    entries = list_history(str(sample_run["json_path"]))
    assert len(entries) == 2
    assert entries[0]["action"] == "a"
    assert entries[1]["action"] == "b"
```

- [ ] **Step 6.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_history.py -v
```

Expected: 4 FAIL.

- [ ] **Step 6.3: Implement**

Append to `transcript_history.py`:

```python
def undo_last(json_path: str) -> dict | None:
    """Restore the latest snapshot and pop the matching _history entry.

    Returns the popped history entry, or None if _history is empty.
    Snapshot file is deleted after restoration.
    """
    data = _load(json_path)
    history = data.get("_history", [])
    if not history:
        return None
    entry = history[-1]
    parent = Path(json_path).parent
    snap_rel = entry.get("snapshot", "")
    if not snap_rel:
        # Defensive: history without snapshot can't be undone — pop anyway
        history.pop()
        _save(json_path, data)
        return entry
    snap_path = parent / snap_rel
    if snap_path.exists():
        # Restore: copy snapshot content over current file
        shutil.copy2(snap_path, json_path)
        snap_path.unlink()
    # Reload (file was just overwritten by snapshot content) and pop history
    data = _load(json_path)
    if data.get("_history"):
        data["_history"].pop()
    _save(json_path, data)
    return entry


def list_history(json_path: str) -> list[dict]:
    """Return _history entries (oldest first). Empty list if absent."""
    if not Path(json_path).exists():
        return []
    data = _load(json_path)
    return list(data.get("_history", []))
```

- [ ] **Step 6.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_history.py -v
```

Expected: 9 PASS.

**Note:** After `undo_last` restores from snapshot, the snapshot file's _history is the same as what was just popped — we must not double-pop. The implementation above reloads then pops. Verify that test 1 still passes (it should — the snapshot reflects the state BEFORE the snapshot+_history append, so the popped state has no history entry to pop).

Actually re-read: `snapshot()` writes the snapshot file with `copy2(path, snap_file)` BEFORE appending to _history. So the snapshot file content lacks the new _history entry. After undo restores from snapshot, _history doesn't include the just-popped entry. So `data["_history"].pop()` on the restored content would pop an EARLIER entry — wrong!

Fix the implementation: after restoring snapshot content, do NOT pop again. The snapshot file already reflects the pre-edit state which lacks the corresponding history entry.

Replace `undo_last` body with:

```python
def undo_last(json_path: str) -> dict | None:
    """Restore the latest snapshot and pop the matching _history entry.

    Returns the popped history entry, or None if _history is empty.
    Snapshot file is deleted after restoration.

    Note on history bookkeeping: snapshot() writes the file BEFORE appending
    to _history. So the snapshot content lacks the just-appended history
    entry. After restoring from snapshot, no further pop is needed.
    """
    data = _load(json_path)
    history = data.get("_history", [])
    if not history:
        return None
    entry = history[-1]
    parent = Path(json_path).parent
    snap_rel = entry.get("snapshot", "")
    if not snap_rel:
        history.pop()
        _save(json_path, data)
        return entry
    snap_path = parent / snap_rel
    if snap_path.exists():
        shutil.copy2(snap_path, json_path)  # restores pre-mutation state
        snap_path.unlink()
    else:
        # Snapshot missing — fall back to popping history entry only
        history.pop()
        _save(json_path, data)
    return entry
```

- [ ] **Step 6.5: Re-run tests**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_history.py -v
```

Expected: 9 PASS. If `test_undo_last_restores_pre_mutation_state` fails, debug the snapshot-vs-history ordering (see note above).

- [ ] **Step 6.6: Commit**

```bash
git add transcript_history.py tests/test_transcript_history.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add undo_last + list_history

undo_last restores the snapshot file (which captures pre-mutation
state) and deletes it; no extra _history pop needed because the
snapshot was written before the corresponding append. list_history
exposes the entries for the UI dropdown.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: load_words_flat + save_word_edits

**Files:**
- Create: `transcript_word_ops.py`
- Create: `tests/test_transcript_word_ops.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_transcript_word_ops.py`:

```python
"""Tests for transcript_word_ops — load_words_flat + save_word_edits."""
import json
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def sample_run(tmp_path, fixtures_dir):
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    src = fixtures_dir / "sample-transcript.whisperx.json"
    dst = run_dir / f"{stem}.whisperx.json"
    shutil.copy(src, dst)
    return {"json_path": dst}


def test_load_words_flat_returns_list_with_segment_index(sample_run):
    from transcript_word_ops import load_words_flat
    flat = load_words_flat(str(sample_run["json_path"]))
    # Sample fixture has words in seg 0 (2 words), seg 1 (1 word), seg 2 (0 words)
    # Total: 3 word entries
    assert len(flat) == 3
    assert flat[0]["word"] == "All"
    assert flat[0]["segment_index"] == 0
    assert flat[2]["segment_index"] == 1


def test_load_words_flat_for_specific_segment(sample_run):
    from transcript_word_ops import load_words_flat
    flat = load_words_flat(str(sample_run["json_path"]), segment_index=0)
    assert len(flat) == 2
    assert all(w["segment_index"] == 0 for w in flat)


def test_save_word_edits_updates_word_strings(sample_run):
    from transcript_word_ops import save_word_edits
    # Seg 0 has 2 words: "All", "right."
    save_word_edits(str(sample_run["json_path"]), segment_index=0,
                    new_words=["Alle", "richtig."])
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    words = data["segments"][0]["words"]
    assert words[0]["word"] == "Alle"
    assert words[1]["word"] == "richtig."


def test_save_word_edits_sets_word_edited_flag(sample_run):
    from transcript_word_ops import save_word_edits
    save_word_edits(str(sample_run["json_path"]), segment_index=0,
                    new_words=["Alle", "right."])  # only first word changed
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    words = data["segments"][0]["words"]
    assert words[0]["_edited"] is True
    assert words[1].get("_edited", False) is False


def test_save_word_edits_rebuilds_segment_text(sample_run):
    from transcript_word_ops import save_word_edits
    save_word_edits(str(sample_run["json_path"]), segment_index=0,
                    new_words=["Alle", "richtig."])
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert data["segments"][0]["text"] == "Alle richtig."


def test_save_word_edits_does_not_set_segment_edited(sample_run):
    from transcript_word_ops import save_word_edits
    save_word_edits(str(sample_run["json_path"]), segment_index=0,
                    new_words=["Alle", "richtig."])
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # Word-level edits don't set segment._edited (separate tracking)
    assert data["segments"][0].get("_edited", False) is False


def test_save_word_edits_raises_on_length_mismatch(sample_run):
    from transcript_word_ops import save_word_edits
    with pytest.raises(ValueError, match="length"):
        save_word_edits(str(sample_run["json_path"]), segment_index=0,
                        new_words=["only one"])
```

- [ ] **Step 7.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_word_ops.py -v
```

Expected: 7 FAIL.

- [ ] **Step 7.3: Implement**

Create `transcript_word_ops.py`:

```python
"""Word-level edit operations.

V1 does not re-align word timings against audio. After a word edit, the
word's start/end remain at the pre-edit values; segment.text is
rebuilt from the (possibly updated) word list.
"""
import json
from pathlib import Path

from transcript_editor import regenerate_srt_txt


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _save(json_path: str, data: dict) -> None:
    Path(json_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_words_flat(json_path: str, segment_index: int | None = None) -> list[dict]:
    """Return a flat list of {word, start, end, score, _edited, segment_index, word_index}.

    If segment_index is given, returns only words for that segment.
    """
    data = _load(json_path)
    out: list[dict] = []
    for seg_i, seg in enumerate(data.get("segments", [])):
        if segment_index is not None and seg_i != segment_index:
            continue
        for word_i, w in enumerate(seg.get("words", [])):
            out.append({
                **w,
                "segment_index": seg_i,
                "word_index": word_i,
            })
    return out


def save_word_edits(json_path: str, segment_index: int, new_words: list[str]) -> dict:
    """Update word strings within a single segment.

    Sets _edited: true on each word whose string changed. Rebuilds the
    segment.text via " ".join(words). Does NOT set segment._edited
    (word-level tracking is separate).

    Returns: {"edited_count": int, "total_words": int}.
    Raises ValueError on length mismatch or out-of-range index.
    """
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments):
        raise ValueError(f"segment_index {segment_index} out of range")
    seg = segments[segment_index]
    words = seg.get("words", [])
    if len(new_words) != len(words):
        raise ValueError(
            f"new_words length {len(new_words)} != words length {len(words)}"
        )
    edited_count = 0
    for word, new_str in zip(words, new_words):
        if word.get("word") != new_str:
            word["word"] = new_str
            word["_edited"] = True
            edited_count += 1
    if edited_count > 0:
        # Rebuild segment.text from words
        seg["text"] = " ".join(w.get("word", "") for w in words)
    _save(json_path, data)
    if edited_count > 0:
        regenerate_srt_txt(json_path)
    return {"edited_count": edited_count, "total_words": len(words)}
```

- [ ] **Step 7.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_word_ops.py -v
```

Expected: 7 PASS.

- [ ] **Step 7.5: Commit**

```bash
git add transcript_word_ops.py tests/test_transcript_word_ops.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add word-level edits (no re-align)

load_words_flat exposes per-word rows for the UI. save_word_edits
updates word strings, sets per-word _edited flags, and rebuilds the
parent segment.text. Word timings are not re-aligned — users who
want fresh timings can re-run the Transcribe phase.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: compute_segment_diff

**Files:**
- Create: `transcript_diff.py`
- Create: `tests/test_transcript_diff.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/test_transcript_diff.py`:

```python
"""Tests for transcript_diff — segment-level diff vs .original.json."""
import json
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def edited_run(tmp_path, fixtures_dir):
    """A run dir with both .whisperx.json (edited) and .whisperx.original.json."""
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    src = fixtures_dir / "sample-transcript.whisperx.json"
    # Original copy
    shutil.copy(src, run_dir / f"{stem}.whisperx.original.json")
    # Current copy (will be mutated below)
    dst = run_dir / f"{stem}.whisperx.json"
    shutil.copy(src, dst)
    return {"json_path": dst, "original_path": run_dir / f"{stem}.whisperx.original.json"}


@pytest.fixture
def unedited_run(tmp_path, fixtures_dir):
    """A run dir with .whisperx.json only (no .original.json)."""
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    shutil.copy(fixtures_dir / "sample-transcript.whisperx.json",
                run_dir / f"{stem}.whisperx.json")
    return {"json_path": run_dir / f"{stem}.whisperx.json"}


def test_compute_segment_diff_returns_empty_when_no_original(unedited_run):
    from transcript_diff import compute_segment_diff
    diffs = compute_segment_diff(str(unedited_run["json_path"]))
    assert diffs == []


def test_compute_segment_diff_marks_text_changes(edited_run):
    from transcript_diff import compute_segment_diff
    # Mutate current: change segment 0 text
    data = json.loads(edited_run["json_path"].read_text(encoding="utf-8"))
    data["segments"][0]["text"] = "Hello and good morning."
    data["segments"][0]["_edited"] = True
    edited_run["json_path"].write_text(json.dumps(data, indent=2), encoding="utf-8")

    diffs = compute_segment_diff(str(edited_run["json_path"]))
    # Diff entries for ALL segments (or at least segment 0)
    assert len(diffs) >= 1
    seg_0 = [d for d in diffs if d["current_index"] == 0][0]
    assert seg_0["text_changed"] is True
    assert "text_diff" in seg_0


def test_compute_segment_diff_detects_speaker_change(edited_run):
    from transcript_diff import compute_segment_diff
    data = json.loads(edited_run["json_path"].read_text(encoding="utf-8"))
    data["segments"][0]["speaker"] = "Anna"
    data["segments"][0]["_speaker_edited"] = True
    edited_run["json_path"].write_text(json.dumps(data, indent=2), encoding="utf-8")

    diffs = compute_segment_diff(str(edited_run["json_path"]))
    seg_0 = [d for d in diffs if d["current_index"] == 0][0]
    assert seg_0["speaker_changed"] is True
    assert seg_0["original_speaker"] == "SPEAKER_00"
    assert seg_0["current_speaker"] == "Anna"


def test_compute_segment_diff_handles_merged_segments(edited_run):
    from transcript_diff import compute_segment_diff
    data = json.loads(edited_run["json_path"].read_text(encoding="utf-8"))
    # Simulate merge of segments 0+1 → produces 2 segments instead of 3
    seg_0 = data["segments"][0]
    seg_1 = data["segments"][1]
    merged = {
        "start": seg_0["start"],
        "end": seg_1["end"],
        "text": seg_0["text"] + " " + seg_1["text"],
        "speaker": seg_0["speaker"],
        "words": seg_0["words"] + seg_1["words"],
        "_merged_from": [0, 1],
    }
    data["segments"] = [merged] + data["segments"][2:]
    edited_run["json_path"].write_text(json.dumps(data, indent=2), encoding="utf-8")

    diffs = compute_segment_diff(str(edited_run["json_path"]))
    merged_entry = [d for d in diffs if d["current_index"] == 0][0]
    assert merged_entry["original_indices"] == [0, 1]
    assert merged_entry["merge_or_split"] == "merged"


def test_compute_segment_diff_handles_split_segments(edited_run):
    from transcript_diff import compute_segment_diff
    data = json.loads(edited_run["json_path"].read_text(encoding="utf-8"))
    # Simulate split of segment 1 → into two halves, both _split_from=1
    seg_1 = data["segments"][1]
    mid = (seg_1["start"] + seg_1["end"]) / 2
    left = {"start": seg_1["start"], "end": mid, "text": "Left half.",
            "speaker": seg_1["speaker"], "words": [], "_split_from": 1}
    right = {"start": mid, "end": seg_1["end"], "text": "Right half.",
             "speaker": seg_1["speaker"], "words": [], "_split_from": 1}
    data["segments"] = [data["segments"][0], left, right, data["segments"][2]]
    edited_run["json_path"].write_text(json.dumps(data, indent=2), encoding="utf-8")

    diffs = compute_segment_diff(str(edited_run["json_path"]))
    split_entries = [d for d in diffs if d.get("merge_or_split") == "split"]
    assert len(split_entries) == 2
    assert all(s["original_indices"] == [1] for s in split_entries)
```

- [ ] **Step 8.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_diff.py -v
```

Expected: 5 FAIL.

- [ ] **Step 8.3: Implement**

Create `transcript_diff.py`:

```python
"""Diff transcript vs. .original.json snapshot.

Pure function — read-only. Produces a per-current-segment list with
text-diff tags, speaker-change flag, and merge/split origin metadata.
"""
import difflib
import json
from pathlib import Path


def _backup_path_for(json_path: Path) -> Path:
    return json_path.with_name(json_path.stem + ".original.json")


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def compute_segment_diff(json_path: str) -> list[dict]:
    """Return per-current-segment diff entries.

    If .original.json doesn't exist, returns []. Otherwise each entry has:
      - current_index: int
      - original_indices: list[int] — derived from _split_from / _merged_from
            or [current_index] when no metadata is present
      - text_changed: bool
      - text_diff: list[tuple(tag, original_word, current_word)]  # via SequenceMatcher
      - speaker_changed: bool
      - original_speaker: str
      - current_speaker: str
      - merge_or_split: "merged" | "split" | None
    """
    cur_path = Path(json_path)
    orig_path = _backup_path_for(cur_path)
    if not orig_path.exists():
        return []
    current = _load(json_path)
    original = _load(str(orig_path))
    cur_segs = current.get("segments", [])
    orig_segs = original.get("segments", [])

    out: list[dict] = []
    for i, seg in enumerate(cur_segs):
        if "_merged_from" in seg:
            orig_indices = list(seg["_merged_from"])
            merge_or_split = "merged"
        elif "_split_from" in seg:
            orig_indices = [int(seg["_split_from"])]
            merge_or_split = "split"
        else:
            orig_indices = [i] if i < len(orig_segs) else []
            merge_or_split = None

        # Concat original text(s) for comparison
        original_text = " ".join(
            orig_segs[oi]["text"] for oi in orig_indices if 0 <= oi < len(orig_segs)
        ).strip()
        current_text = seg.get("text", "").strip()
        text_changed = original_text != current_text
        # Word-level diff via SequenceMatcher
        orig_words = original_text.split()
        cur_words = current_text.split()
        matcher = difflib.SequenceMatcher(a=orig_words, b=cur_words)
        text_diff: list[tuple] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            text_diff.append((tag, " ".join(orig_words[i1:i2]), " ".join(cur_words[j1:j2])))

        # Speaker compare
        original_speaker = (
            orig_segs[orig_indices[0]].get("speaker", "")
            if orig_indices and 0 <= orig_indices[0] < len(orig_segs)
            else ""
        )
        current_speaker = seg.get("speaker", "")
        speaker_changed = original_speaker != current_speaker

        out.append({
            "current_index": i,
            "original_indices": orig_indices,
            "text_changed": text_changed,
            "text_diff": text_diff,
            "speaker_changed": speaker_changed,
            "original_speaker": original_speaker,
            "current_speaker": current_speaker,
            "merge_or_split": merge_or_split,
        })
    return out
```

- [ ] **Step 8.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_transcript_diff.py -v
```

Expected: 5 PASS.

- [ ] **Step 8.5: Full sweep**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: 135 PASS (97 + 17 segment ops + 9 history + 7 word + 5 diff).

- [ ] **Step 8.6: Commit**

```bash
git add transcript_diff.py tests/test_transcript_diff.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): add compute_segment_diff

Per-current-segment diff vs .original.json. Uses _merged_from /
_split_from to match against original indices. Word-level diff via
difflib.SequenceMatcher. Empty list when no .original.json exists.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Route — POST /runs/{stem}/edit/speaker

**Files:**
- Modify: `webgui/app.py`
- Create: `tests/test_webgui_phase2_routes.py`
- Create: `webgui/templates/_partials/segment_editor.html`

- [ ] **Step 9.1: Write failing tests**

Create `tests/test_webgui_phase2_routes.py`:

```python
"""Phase 2 route tests — speaker, bulk-rename, merge, split, undo, words, diff."""
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
    """One stem 'ep01' with transcript JSON + minimal run-state."""
    out = tmp_path / "output"
    ep_dir = out / "ep01"
    ep_dir.mkdir(parents=True)
    shutil.copy(fixtures_dir / "sample-transcript.whisperx.json",
                ep_dir / "ep01.whisperx.json")
    state = {
        "schema_version": 1, "stem": "ep01",
        "audio": str(fixtures_dir / "sample.m4a"),
        "phases": {
            "transcribe": {"status": "done"}, "meta": {"status": "done"},
            "render": {"status": "done"}, "upload": {"status": "skipped"},
        },
        "config": {},
    }
    (ep_dir / "run-state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    return out


def test_post_speaker_change_updates_segment(client, populated_run):
    r = client.post("/runs/ep01/edit/speaker",
                    data={"segment_index": "0", "speaker": "Anna"})
    assert r.status_code == 200
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["segments"][0]["speaker"] == "Anna"
    assert data["segments"][0]["_speaker_edited"] is True


def test_post_speaker_change_returns_segment_partial(client, populated_run):
    r = client.post("/runs/ep01/edit/speaker",
                    data={"segment_index": "0", "speaker": "Anna"})
    assert r.status_code == 200
    # Returns HTML partial — should contain the segment textarea + speaker dropdown
    assert "segment_text_0" in r.text
    assert "Anna" in r.text
```

- [ ] **Step 9.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 2 FAIL.

- [ ] **Step 9.3: Create the segment_editor.html partial**

Create `webgui/templates/_partials/segment_editor.html`:

```html
{# Re-rendered after every HTMX edit. Receives: seg, loop_index, speakers (distinct list) #}
<div class="edit-segment {% if seg.get('_edited') %}is-edited{% endif %}"
     id="segment-{{ loop_index }}">
  <div class="edit-segment-header mono">
    <span class="time">{{ "%02d:%02d"|format((seg.start|int)//60, (seg.start|int)%60) }}</span>
    <form hx-post="/runs/{{ stem }}/edit/speaker"
          hx-target="#segment-{{ loop_index }}"
          hx-swap="outerHTML"
          style="display:inline;">
      <input type="hidden" name="segment_index" value="{{ loop_index }}">
      <select name="speaker" class="speaker-select" onchange="this.form.requestSubmit()">
        {% for spk in speakers %}
          <option value="{{ spk }}" {% if spk == seg.speaker %}selected{% endif %}>{{ spk }}</option>
        {% endfor %}
        <option value="{{ seg.speaker }}" {% if seg.speaker not in speakers %}selected{% endif %}>{{ seg.speaker }}</option>
      </select>
    </form>
    {% if seg.get('_edited') %}<span class="edit-badge">★ edited</span>{% endif %}
    {% if seg.get('_speaker_edited') %}<span class="edit-badge">☆ speaker</span>{% endif %}
    {% if seg.get('_merged_from') %}<span class="edit-badge">⇄ merged</span>{% endif %}
    {% if seg.get('_split_from') is not none %}<span class="edit-badge">⇋ split</span>{% endif %}
  </div>
  <textarea name="segment_text_{{ loop_index }}" class="edit-textarea" rows="2">{{ seg.text }}</textarea>
  <input type="hidden" name="original_text_{{ loop_index }}" value="{{ seg.text }}">
  <div class="row" style="gap:8px; margin-top:6px;">
    <form hx-post="/runs/{{ stem }}/edit/merge"
          hx-target="#edit-form-segments"
          hx-swap="innerHTML"
          style="display:inline;">
      <input type="hidden" name="segment_index" value="{{ loop_index }}">
      <button type="submit" class="btn btn-ghost btn-sm">⇄ Merge with next</button>
    </form>
    <form hx-post="/runs/{{ stem }}/edit/split"
          hx-target="#edit-form-segments"
          hx-swap="innerHTML"
          style="display:inline;"
          onsubmit="this.querySelector('[name=char_position]').value = document.querySelector('[name=segment_text_{{ loop_index }}]').selectionStart;">
      <input type="hidden" name="segment_index" value="{{ loop_index }}">
      <input type="hidden" name="char_position" value="0">
      <button type="submit" class="btn btn-ghost btn-sm">⇋ Split at cursor</button>
    </form>
  </div>
</div>
```

- [ ] **Step 9.4: Add the route**

In `webgui/app.py`, add imports near the top:

```python
from transcript_editor import load_segments, save_edits, invalidate_downstream, has_been_edited
from transcript_segment_ops import change_speaker, bulk_rename_speaker, merge_segment, split_segment
from transcript_word_ops import load_words_flat, save_word_edits
from transcript_history import snapshot, undo_last, list_history, cleanup_snapshots
from transcript_diff import compute_segment_diff
```

(Only the first line was V1; replace it with the full block above.)

Add helper just below the existing helpers:

```python
def _distinct_speakers(json_path: Path) -> list[str]:
    if not json_path.exists():
        return []
    data = json.loads(json_path.read_text(encoding="utf-8"))
    return sorted({seg.get("speaker", "") for seg in data.get("segments", []) if seg.get("speaker")})
```

Add the speaker-change route:

```python
@app.post("/runs/{stem}/edit/speaker", response_class=HTMLResponse)
async def run_edit_speaker(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    form = await request.form()
    try:
        segment_index = int(form.get("segment_index", "-1"))
    except ValueError:
        raise HTTPException(status_code=400, detail="segment_index must be int")
    new_speaker = form.get("speaker", "").strip()
    if not new_speaker:
        raise HTTPException(status_code=400, detail="speaker required")
    snapshot(str(json_path), action="edit_speaker", metric=f"segment {segment_index} → {new_speaker}")
    try:
        change_speaker(str(json_path), segment_index, new_speaker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    invalidate_downstream(str(OUTPUT_ROOT / stem / "run-state.json"))
    cleanup_snapshots(str(json_path))

    segments = load_segments(str(json_path))
    speakers = _distinct_speakers(json_path)
    seg = segments[segment_index]
    return templates.TemplateResponse(
        request, "_partials/segment_editor.html",
        {"stem": stem, "seg": seg, "loop_index": segment_index, "speakers": speakers},
    )
```

- [ ] **Step 9.5: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 2 PASS.

- [ ] **Step 9.6: Commit**

```bash
git add webgui/app.py webgui/templates/_partials/segment_editor.html tests/test_webgui_phase2_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): POST /runs/{stem}/edit/speaker

HTMX endpoint: changes one segment's speaker, snapshots first,
invalidates downstream phases, and re-renders the segment partial.
segment_editor.html is the canonical HTMX target for segment changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Route — POST /runs/{stem}/edit/bulk-rename

**Files:**
- Modify: `webgui/app.py`
- Modify: `tests/test_webgui_phase2_routes.py`

- [ ] **Step 10.1: Write failing tests**

Append:

```python
def test_post_bulk_rename_renames_all_matching(client, populated_run):
    r = client.post("/runs/ep01/edit/bulk-rename",
                    data={"old_name": "SPEAKER_00", "new_name": "Anna"},
                    follow_redirects=False)
    assert r.status_code == 303
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    speakers = [s["speaker"] for s in data["segments"]]
    assert "Anna" in speakers
    assert "SPEAKER_00" not in speakers


def test_post_bulk_rename_400_on_same_names(client, populated_run):
    r = client.post("/runs/ep01/edit/bulk-rename",
                    data={"old_name": "SPEAKER_00", "new_name": "SPEAKER_00"})
    assert r.status_code == 400
```

- [ ] **Step 10.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 2 FAIL.

- [ ] **Step 10.3: Implement**

Add to `webgui/app.py`:

```python
@app.post("/runs/{stem}/edit/bulk-rename")
async def run_edit_bulk_rename(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    form = await request.form()
    old_name = (form.get("old_name") or "").strip()
    new_name = (form.get("new_name") or "").strip()
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="old_name and new_name required")
    snapshot(str(json_path), action="bulk_rename",
             metric=f"{old_name} → {new_name}")
    try:
        count = bulk_rename_speaker(str(json_path), old_name, new_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    invalidate_downstream(str(OUTPUT_ROOT / stem / "run-state.json"))
    cleanup_snapshots(str(json_path))
    return RedirectResponse(url=f"/runs/{stem}/edit", status_code=303)
```

- [ ] **Step 10.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 4 PASS.

- [ ] **Step 10.5: Commit**

```bash
git add webgui/app.py tests/test_webgui_phase2_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): POST /edit/bulk-rename

Classic form-redirect endpoint (303 → /runs/{stem}/edit). Snapshots
before, invalidates downstream after. Empty or same names → 400.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Routes — POST /edit/merge + POST /edit/split

**Files:**
- Modify: `webgui/app.py`
- Modify: `tests/test_webgui_phase2_routes.py`

- [ ] **Step 11.1: Write failing tests**

Append:

```python
def test_post_merge_combines_segments(client, populated_run):
    r = client.post("/runs/ep01/edit/merge", data={"segment_index": "0"})
    assert r.status_code == 200
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["segments"]) == 2  # was 3


def test_post_merge_returns_all_segments_partial(client, populated_run):
    r = client.post("/runs/ep01/edit/merge", data={"segment_index": "0"})
    # Returns the full segments-list partial so HTMX can swap the whole list
    assert "segment_text_0" in r.text
    assert "segment_text_1" in r.text


def test_post_split_creates_two_segments(client, populated_run):
    r = client.post("/runs/ep01/edit/split",
                    data={"segment_index": "1", "char_position": "16"})
    assert r.status_code == 200
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data["segments"]) == 4  # was 3


def test_post_split_400_on_invalid_position(client, populated_run):
    r = client.post("/runs/ep01/edit/split",
                    data={"segment_index": "1", "char_position": "0"})
    assert r.status_code == 400
```

- [ ] **Step 11.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 4 FAIL.

- [ ] **Step 11.3: Add a helper that renders the full segments-list partial**

In `webgui/app.py`, add helper:

```python
def _render_segments_partial(request: Request, stem: str) -> HTMLResponse:
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    segments = load_segments(str(json_path))
    speakers = _distinct_speakers(json_path)
    return templates.TemplateResponse(
        request, "_partials/segments_list.html",
        {"stem": stem, "segments": segments, "speakers": speakers},
    )
```

Create `webgui/templates/_partials/segments_list.html`:

```html
{% for seg in segments %}
  {% include "_partials/segment_editor.html" %}
{% endfor %}
```

Note: inside the loop, `loop.index0` provides the index — but the partial expects `loop_index`. Add a wrapper `{% with loop_index = loop.index0 %}…{% endwith %}` or pass `loop_index=loop.index0` via `include … with` (Jinja2). The cleanest:

```html
{% for seg in segments %}
  {% set loop_index = loop.index0 %}
  {% include "_partials/segment_editor.html" %}
{% endfor %}
```

`{% set %}` inside a loop has loop-scope by default in Jinja2 — verify in the test pass step.

- [ ] **Step 11.4: Add merge + split routes**

Append to `webgui/app.py`:

```python
@app.post("/runs/{stem}/edit/merge", response_class=HTMLResponse)
async def run_edit_merge(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    form = await request.form()
    try:
        segment_index = int(form.get("segment_index", "-1"))
    except ValueError:
        raise HTTPException(status_code=400, detail="segment_index must be int")
    snapshot(str(json_path), action="merge",
             metric=f"segments {segment_index}+{segment_index + 1}")
    try:
        merge_segment(str(json_path), segment_index)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    invalidate_downstream(str(OUTPUT_ROOT / stem / "run-state.json"))
    cleanup_snapshots(str(json_path))
    return _render_segments_partial(request, stem)


@app.post("/runs/{stem}/edit/split", response_class=HTMLResponse)
async def run_edit_split(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    form = await request.form()
    try:
        segment_index = int(form.get("segment_index", "-1"))
        char_position = int(form.get("char_position", "0"))
    except ValueError:
        raise HTTPException(status_code=400, detail="indices must be int")
    snapshot(str(json_path), action="split",
             metric=f"segment {segment_index} at char {char_position}")
    try:
        split_segment(str(json_path), segment_index, char_position)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    invalidate_downstream(str(OUTPUT_ROOT / stem / "run-state.json"))
    cleanup_snapshots(str(json_path))
    return _render_segments_partial(request, stem)
```

- [ ] **Step 11.5: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 8 PASS.

- [ ] **Step 11.6: Commit**

```bash
git add webgui/app.py webgui/templates/_partials/segments_list.html tests/test_webgui_phase2_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): POST /edit/merge + /edit/split

Both HTMX endpoints return the full segments_list.html partial since
merge/split change segment count (a single-segment swap wouldn't
suffice). Snapshot → mutate → invalidate downstream → cleanup.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Route — POST /runs/{stem}/edit/undo

**Files:**
- Modify: `webgui/app.py`
- Modify: `tests/test_webgui_phase2_routes.py`

- [ ] **Step 12.1: Write failing tests**

Append:

```python
def test_post_undo_restores_previous_state(client, populated_run):
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    pre = json.loads(json_path.read_text(encoding="utf-8"))
    pre_speaker_0 = pre["segments"][0]["speaker"]
    # Make a change first
    client.post("/runs/ep01/edit/speaker", data={"segment_index": "0", "speaker": "Anna"})
    mid = json.loads(json_path.read_text(encoding="utf-8"))
    assert mid["segments"][0]["speaker"] == "Anna"
    # Now undo
    r = client.post("/runs/ep01/edit/undo", follow_redirects=False)
    assert r.status_code == 303
    post_state = json.loads(json_path.read_text(encoding="utf-8"))
    assert post_state["segments"][0]["speaker"] == pre_speaker_0


def test_post_undo_303_when_history_empty(client, populated_run):
    # No prior edits → no history
    r = client.post("/runs/ep01/edit/undo", follow_redirects=False)
    # Endpoint should still redirect (no-op rather than error)
    assert r.status_code == 303
```

- [ ] **Step 12.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 2 FAIL.

- [ ] **Step 12.3: Implement**

Append to `webgui/app.py`:

```python
@app.post("/runs/{stem}/edit/undo")
async def run_edit_undo(stem: str):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    undo_last(str(json_path))  # no-op if history empty
    # Note: undo restores the pre-snapshot state which already had SRT/TXT
    # in sync at that point. Re-generate to be safe.
    from transcript_editor import regenerate_srt_txt as _regen
    if json_path.exists():
        _regen(str(json_path))
    # Downstream is invalidated anyway on next save; no need to invalidate here.
    return RedirectResponse(url=f"/runs/{stem}/edit", status_code=303)
```

- [ ] **Step 12.4: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 10 PASS.

- [ ] **Step 12.5: Commit**

```bash
git add webgui/app.py tests/test_webgui_phase2_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): POST /edit/undo

303 redirect back to /edit after restoring the latest snapshot.
Empty history is a no-op (still 303). Regenerates SRT/TXT defensively
in case any prior step left them out of sync.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 13: Routes — GET + POST /edit/words

**Files:**
- Modify: `webgui/app.py`
- Modify: `tests/test_webgui_phase2_routes.py`
- Create: `webgui/templates/run_edit_words.html`

- [ ] **Step 13.1: Write failing tests**

Append:

```python
def test_get_words_renders_per_word_rows(client, populated_run):
    r = client.get("/runs/ep01/edit/words?segment_index=0")
    assert r.status_code == 200
    # Sample fixture has 2 words in segment 0: "All" and "right."
    assert 'name="word_0"' in r.text
    assert 'name="word_1"' in r.text
    assert "All" in r.text
    assert "right." in r.text


def test_get_words_404_when_transcribe_missing(client, tmp_path, monkeypatch):
    out = tmp_path / "output"
    (out / "ghost").mkdir(parents=True)
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    r = client.get("/runs/ghost/edit/words?segment_index=0")
    assert r.status_code == 404


def test_post_words_saves_edits(client, populated_run):
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    r = client.post("/runs/ep01/edit/words",
                    data={"segment_index": "0", "word_0": "Alle", "word_1": "richtig."},
                    follow_redirects=False)
    assert r.status_code == 303
    data = json.loads(json_path.read_text(encoding="utf-8"))
    words = data["segments"][0]["words"]
    assert words[0]["word"] == "Alle"
    assert words[1]["word"] == "richtig."
    assert data["segments"][0]["text"] == "Alle richtig."
```

- [ ] **Step 13.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 3 FAIL.

- [ ] **Step 13.3: Add routes**

Append to `webgui/app.py`:

```python
@app.get("/runs/{stem}/edit/words", response_class=HTMLResponse)
async def run_edit_words(stem: str, request: Request, segment_index: int = 0):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    segments = load_segments(str(json_path))
    if segment_index < 0 or segment_index >= len(segments):
        raise HTTPException(status_code=400, detail="segment_index out of range")
    seg = segments[segment_index]
    words = seg.get("words", [])
    return templates.TemplateResponse(
        request, "run_edit_words.html",
        {"stem": stem, "segment_index": segment_index,
         "segment": seg, "words": words,
         "total_segments": len(segments), "page_mood": "neutral"},
    )


@app.post("/runs/{stem}/edit/words")
async def run_edit_words_save(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    form = await request.form()
    try:
        segment_index = int(form.get("segment_index", "-1"))
    except ValueError:
        raise HTTPException(status_code=400, detail="segment_index must be int")
    segments = load_segments(str(json_path))
    if segment_index < 0 or segment_index >= len(segments):
        raise HTTPException(status_code=400, detail="segment_index out of range")
    words = segments[segment_index].get("words", [])
    new_words: list[str] = []
    for i in range(len(words)):
        v = form.get(f"word_{i}")
        if v is None:
            raise HTTPException(status_code=400, detail=f"Missing word_{i}")
        new_words.append(v)
    snapshot(str(json_path), action="edit_words",
             metric=f"segment {segment_index}, {len(new_words)} words")
    try:
        save_word_edits(str(json_path), segment_index, new_words)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    invalidate_downstream(str(OUTPUT_ROOT / stem / "run-state.json"))
    cleanup_snapshots(str(json_path))
    return RedirectResponse(url=f"/runs/{stem}/edit", status_code=303)
```

- [ ] **Step 13.4: Create the template**

Create `webgui/templates/run_edit_words.html`:

```html
{% extends "base.html" %}
{% block title %}Word edit · {{ stem }}{% endblock %}
{% block content %}
<header class="run-header">
  <div class="left">
    <div class="crumbs"><a href="/runs/{{ stem }}/edit">← Back to editor</a></div>
    <h1><span class="accent-mark">⫶</span>Word edits: {{ stem }} / Segment {{ segment_index }}</h1>
    <p class="muted" style="margin-top:8px; font-size: 13px;">
      Edit individual words. Segment text will be rebuilt from these words on save.
      Word timings are not re-aligned (run Transcribe again for fresh timings).
    </p>
  </div>
  <div>
    <form method="get" action="/runs/{{ stem }}/edit/words" style="display:inline;">
      <label>Segment:
        <select name="segment_index" onchange="this.form.submit()">
          {% for i in range(total_segments) %}
            <option value="{{ i }}" {% if i == segment_index %}selected{% endif %}>Segment {{ i }}</option>
          {% endfor %}
        </select>
      </label>
    </form>
  </div>
</header>

<form method="post" action="/runs/{{ stem }}/edit/words" class="words-form">
  <input type="hidden" name="segment_index" value="{{ segment_index }}">
  <table class="words-table">
    <thead>
      <tr><th>Time</th><th>Speaker</th><th>Word</th></tr>
    </thead>
    <tbody>
      {% for w in words %}
        <tr>
          <td class="mono">{{ "%.2f"|format(w.start|default(0)) }}–{{ "%.2f"|format(w.end|default(0)) }}</td>
          <td>{{ segment.speaker | default("SPEAKER_00") }}</td>
          <td><input type="text" name="word_{{ loop.index0 }}" value="{{ w.word | default('') }}" class="input"></td>
        </tr>
      {% endfor %}
    </tbody>
  </table>
  <div class="row" style="gap:12px; margin-top:24px;">
    <button type="submit" class="btn btn-primary">Save words</button>
    <a href="/runs/{{ stem }}/edit" class="btn btn-ghost">Cancel</a>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 13.5: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 13 PASS.

- [ ] **Step 13.6: Commit**

```bash
git add webgui/app.py webgui/templates/run_edit_words.html tests/test_webgui_phase2_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): GET + POST /edit/words

Word-level editor: per-word table with read-only times + speaker
and an editable input per word. Segment-picker dropdown switches
which segment is being edited. Save rebuilds segment.text and
triggers SRT/TXT regeneration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 14: Route — GET /runs/{stem}/diff

**Files:**
- Modify: `webgui/app.py`
- Modify: `tests/test_webgui_phase2_routes.py`
- Create: `webgui/templates/run_diff.html`

- [ ] **Step 14.1: Write failing tests**

Append:

```python
def test_get_diff_empty_state_when_no_original(client, populated_run):
    r = client.get("/runs/ep01/diff")
    assert r.status_code == 200
    # No original.json yet → empty state
    assert "No edits yet" in r.text or "no diff" in r.text.lower()


def test_get_diff_shows_changed_segments(client, populated_run):
    # Make an edit so .original.json is created
    client.post("/runs/ep01/edit/speaker",
                data={"segment_index": "0", "speaker": "Anna"})
    # The speaker change should have triggered save_edits' backup-on-first-save
    # via regenerate paths. To trigger backup creation, run a text edit:
    form = {
        "segment_text_0": "Hello edited.",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-return",
    }
    client.post("/runs/ep01/edit", data=form)
    r = client.get("/runs/ep01/diff")
    assert r.status_code == 200
    assert "Hello edited" in r.text or "edited" in r.text.lower()
```

- [ ] **Step 14.2: Verify fail**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 2 FAIL.

- [ ] **Step 14.3: Add route**

Append to `webgui/app.py`:

```python
@app.get("/runs/{stem}/diff", response_class=HTMLResponse)
async def run_diff_view(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    diffs = compute_segment_diff(str(json_path))
    changed = [d for d in diffs if d["text_changed"] or d["speaker_changed"] or d["merge_or_split"]]
    return templates.TemplateResponse(
        request, "run_diff.html",
        {"stem": stem, "diffs": diffs, "changed_count": len(changed),
         "has_original": (json_path.with_name(json_path.stem + ".original.json").exists()),
         "page_mood": "neutral"},
    )
```

- [ ] **Step 14.4: Create the template**

Create `webgui/templates/run_diff.html`:

```html
{% extends "base.html" %}
{% block title %}Diff · {{ stem }}{% endblock %}
{% block content %}
<header class="run-header">
  <div class="left">
    <div class="crumbs"><a href="/runs/{{ stem }}/edit">← Back to editor</a> · <a href="/runs/{{ stem }}">Run</a></div>
    <h1><span class="accent-mark">≡</span>Diff: {{ stem }}</h1>
    {% if has_original %}
      <p class="muted" style="margin-top:8px;">{{ changed_count }} of {{ diffs|length }} segments changed.</p>
    {% endif %}
  </div>
</header>

{% if not has_original %}
  <section class="card" style="margin-top: 24px;">
    <div class="card-body">
      <p class="muted">No edits yet. The diff view becomes available after the first save in the editor.</p>
    </div>
  </section>
{% else %}
  <div class="diff-list" style="margin-top: 24px;">
    {% for d in diffs %}
      <div class="diff-segment {% if d.text_changed or d.speaker_changed or d.merge_or_split %}is-changed{% endif %}">
        <header class="diff-segment-header">
          Segment {{ d.current_index }}
          {% if d.merge_or_split == "merged" %}
            ⇄ merged from {{ d.original_indices | join(' + ') }}
          {% elif d.merge_or_split == "split" %}
            ⇋ split from {{ d.original_indices[0] }}
          {% endif %}
          {% if d.speaker_changed %}
            ★ speaker {{ d.original_speaker }} → {{ d.current_speaker }}
          {% endif %}
        </header>
        <div class="diff-pair">
          <div class="diff-col diff-col-original">
            <div class="diff-col-label mono">Original</div>
            <div class="diff-text">
              {% for tag, orig, cur in d.text_diff %}
                {% if tag == 'equal' %}{{ orig }} {% endif %}
                {% if tag == 'delete' %}<del>{{ orig }}</del> {% endif %}
                {% if tag == 'replace' %}<del>{{ orig }}</del> {% endif %}
              {% endfor %}
            </div>
          </div>
          <div class="diff-col diff-col-current">
            <div class="diff-col-label mono">Current</div>
            <div class="diff-text">
              {% for tag, orig, cur in d.text_diff %}
                {% if tag == 'equal' %}{{ cur }} {% endif %}
                {% if tag == 'insert' %}<ins>{{ cur }}</ins> {% endif %}
                {% if tag == 'replace' %}<ins>{{ cur }}</ins> {% endif %}
              {% endfor %}
            </div>
          </div>
        </div>
      </div>
    {% endfor %}
  </div>
{% endif %}
{% endblock %}
```

- [ ] **Step 14.5: Verify pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/test_webgui_phase2_routes.py -v
```

Expected: 15 PASS.

- [ ] **Step 14.6: Commit**

```bash
git add webgui/app.py webgui/templates/run_diff.html tests/test_webgui_phase2_routes.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): GET /diff — side-by-side diff view

Reads .original.json via transcript_diff.compute_segment_diff. Empty
state when no .original.json exists. Per-segment markup with merge/
split origin badges and <ins>/<del> word-level highlighting.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 15: Extend run_edit.html — top-bar, bulk-rename form, history dropdown

**Files:**
- Modify: `webgui/templates/run_edit.html`
- Create: `webgui/templates/_partials/history_dropdown.html`
- Create: `webgui/templates/_partials/speaker_bulk_form.html`
- Modify: `webgui/app.py` (extend `run_edit` GET handler to compute speakers + history)

- [ ] **Step 15.1: Inspect current run_edit.html**

```bash
cat webgui/templates/run_edit.html
```

Verify the V1 structure (header + form with `{% for seg in segments %}` loop + action buttons). The Phase 2 changes replace the loop body with `{% include "_partials/segment_editor.html" %}` so the editor uses the same partial that HTMX targets.

- [ ] **Step 15.2: Update run_edit GET handler in webgui/app.py**

Find the `run_edit` GET handler (added in V1). Update it to compute speakers + history:

```python
@app.get("/runs/{stem}/edit", response_class=HTMLResponse)
async def run_edit(stem: str, request: Request):
    json_path = OUTPUT_ROOT / stem / f"{stem}.whisperx.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found")
    segments = load_segments(str(json_path))
    backup_exists = json_path.with_name(json_path.stem + ".original.json").exists()
    edited_any = has_been_edited(str(json_path))
    speakers = _distinct_speakers(json_path)
    history = list_history(str(json_path))
    return templates.TemplateResponse(
        request, "run_edit.html",
        {
            "stem": stem,
            "segments": segments,
            "backup_exists": backup_exists,
            "edited_any": edited_any,
            "speakers": speakers,
            "history": history,
            "page_mood": "neutral",
        },
    )
```

- [ ] **Step 15.3: Create the history dropdown partial**

Create `webgui/templates/_partials/history_dropdown.html`:

```html
<details class="history-dropdown">
  <summary class="btn btn-ghost btn-sm">
    Undo {% if history|length > 0 %}({{ history|length }} entries){% endif %} ▾
  </summary>
  <div class="history-panel">
    {% if not history %}
      <p class="muted">No edit history yet.</p>
    {% else %}
      <form method="post" action="/runs/{{ stem }}/edit/undo" style="margin-bottom:8px;">
        <button type="submit" class="btn btn-primary btn-sm">↶ Undo last action</button>
      </form>
      <ul class="history-list">
        {% for entry in history|reverse %}
          <li>
            <span class="mono">{{ entry.ts }}</span> — {{ entry.action }}: <span class="muted">{{ entry.metric }}</span>
          </li>
        {% endfor %}
      </ul>
    {% endif %}
  </div>
</details>
```

- [ ] **Step 15.4: Create the bulk-rename form partial**

Create `webgui/templates/_partials/speaker_bulk_form.html`:

```html
<form method="post" action="/runs/{{ stem }}/edit/bulk-rename" class="bulk-rename-form">
  <label class="muted" style="font-size:12px;">Bulk rename speaker:</label>
  <select name="old_name">
    {% for spk in speakers %}
      <option value="{{ spk }}">{{ spk }}</option>
    {% endfor %}
  </select>
  →
  <input type="text" name="new_name" placeholder="New name" class="input" style="width:150px;">
  <button type="submit" class="btn btn-sm">Rename</button>
</form>
```

- [ ] **Step 15.5: Rewrite run_edit.html**

Overwrite `webgui/templates/run_edit.html`:

```html
{% extends "base.html" %}
{% block title %}Edit · {{ stem }}{% endblock %}
{% block content %}
<header class="run-header">
  <div class="left">
    <div class="crumbs">
      <a href="/runs/{{ stem }}">← Back to run</a> ·
      <a href="/runs/{{ stem }}/diff">Diff view</a> ·
      <a href="/runs/{{ stem }}/edit/words">Word view</a>
    </div>
    <h1><span class="accent-mark">✎</span>Edit transcript: {{ stem }}</h1>
    <p class="muted" style="margin-top:8px; font-size: 13px;">
      Edit text, change speakers, merge/split segments, or undo any action.
      Saving invalidates Meta + Render — they will need to re-run.
    </p>
    {% if backup_exists %}
      <p class="muted mono" style="font-size: 11px; margin-top:4px;">Original backup: ✓ saved</p>
    {% endif %}
  </div>
  <div class="run-header-controls" style="display:flex; gap:12px; align-items:flex-start;">
    {% include "_partials/history_dropdown.html" %}
  </div>
</header>

<div style="margin-top:16px;">
  {% include "_partials/speaker_bulk_form.html" %}
</div>

<form id="edit-form" method="post" action="/runs/{{ stem }}/edit" class="edit-form">
  <div id="edit-form-segments">
    {% for seg in segments %}
      {% set loop_index = loop.index0 %}
      {% include "_partials/segment_editor.html" %}
    {% endfor %}
  </div>

  <div class="edit-actions" style="margin-top: 24px; display:flex; gap:12px; flex-wrap:wrap;">
    <button type="submit" name="action" value="save-return" class="btn">Save & Return</button>
    <button type="submit" name="action" value="save-continue" class="btn btn-primary">Save & Continue</button>
    <a href="/runs/{{ stem }}" class="btn btn-ghost">Cancel</a>
  </div>
</form>
{% endblock %}
```

- [ ] **Step 15.6: Add CSS for new components**

Append to `webgui/static/style.css`:

```css
/* === Phase 2 — bulk-rename, history dropdown, diff, words table =========== */

.bulk-rename-form {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: color-mix(in oklab, var(--surface, #1a1a1a) 94%, var(--accent, #6ea8fe) 6%);
  border-radius: var(--radius-md, 8px);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}

.history-dropdown summary { cursor: pointer; }
.history-panel {
  position: relative;
  margin-top: 8px;
  padding: 12px;
  background: var(--surface, #1a1a1a);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-md, 8px);
  min-width: 280px;
}
.history-list {
  margin: 0; padding: 0; list-style: none;
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px;
  max-height: 240px; overflow-y: auto;
}

.speaker-select {
  background: transparent;
  border: 1px solid var(--border, rgba(255, 255, 255, 0.08));
  border-radius: var(--radius-sm, 6px);
  color: var(--accent, #6ea8fe);
  font-weight: 500;
  padding: 1px 6px;
  font-family: inherit;
  font-size: 11px;
  cursor: pointer;
}

.diff-segment {
  margin-top: 12px;
  padding: 12px;
  border-radius: var(--radius-md, 8px);
  background: var(--surface, #1a1a1a);
  border: 1px solid var(--border, rgba(255, 255, 255, 0.06));
}
.diff-segment.is-changed {
  border-color: color-mix(in oklab, var(--accent, #6ea8fe) 30%, transparent);
}
.diff-segment-header {
  font-size: 11px;
  color: var(--muted, rgba(255, 255, 255, 0.55));
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}
.diff-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.diff-col-label { font-size: 10px; color: var(--muted, rgba(255, 255, 255, 0.4)); margin-bottom: 4px; }
.diff-text del { background: color-mix(in oklab, #d04050 30%, transparent); text-decoration: line-through; }
.diff-text ins { background: color-mix(in oklab, #50d080 30%, transparent); text-decoration: none; }

.words-table { width: 100%; border-collapse: collapse; margin-top: 16px; }
.words-table th, .words-table td { padding: 6px 8px; text-align: left; border-bottom: 1px solid var(--border, rgba(255, 255, 255, 0.06)); }
.words-table thead th { font-size: 10px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted, rgba(255, 255, 255, 0.55)); }
.words-table input { width: 100%; }

.btn-sm { font-size: 11px; padding: 4px 8px; }
```

- [ ] **Step 15.7: Add HTMX script tag to base.html (if not present)**

Check `webgui/templates/base.html`:

```bash
grep -n "htmx" webgui/templates/base.html webgui/static/
```

If the project already vendored htmx (e.g. `/static/htmx.min.js` mounted, per V1 file structure), confirm it's loaded via a `<script>` tag in `base.html`. If not, add:

```html
<script src="/static/htmx.min.js" defer></script>
```

before the closing `</head>` (or wherever scripts are loaded).

- [ ] **Step 15.8: Verify all tests still pass**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v 2>&1 | tail -5
```

Expected: ≥150 PASS (97 + 17 + 9 + 7 + 5 + 15 = 150).

- [ ] **Step 15.9: Commit**

```bash
git add webgui/templates/ webgui/static/style.css webgui/app.py
git commit -m "$(cat <<'EOF'
feat(transcript-editor-phase2): integrate editor extensions in UI

run_edit.html now uses segment_editor.html partial (HTMX-targetable),
shows the bulk-rename form, history dropdown with undo, and links
to /diff and /edit/words. CSS for new components added.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 16: AGENTS.md update

- [ ] **Step 16.1: Edit AGENTS.md**

In the "Architektur-Highlights" section, replace the Transcript-Editor bullet with a longer description covering Phase 2 features. Add to "Wo finde ich was":

```markdown
| Wo lebt der Editor Phase 2? | `transcript_segment_ops.py` · `transcript_word_ops.py` · `transcript_history.py` · `transcript_diff.py` |
| Routes für Phase-2-Editor? | `POST /edit/speaker` · `POST /edit/bulk-rename` · `POST /edit/merge` · `POST /edit/split` · `POST /edit/undo` · `GET`/`POST /edit/words` · `GET /diff` |
| Spec für Phase 2? | `docs/superpowers/specs/2026-05-27-transcript-editor-phase2-design.md` |
| Plan für Phase 2? | `docs/superpowers/plans/2026-05-27-transcript-editor-phase2.md` |
```

In the "Phase 2 oder später"-Liste, **remove** the line about Phase 2 features and replace with a Phase 3 stub:

```markdown
- Audio-Re-Align nach Word-Edit (Phase 3)
- Visual word-timing editor (Phase 3)
- Multi-Tab Conflict-Resolution (Phase 3)
- Find-and-Replace (Phase 3)
- Spell-Check / LLM-Suggestions (Phase 3)
```

- [ ] **Step 16.2: No commit (AGENTS.md is .gitignored per repo convention)**

This file is local-only. Skip git add.

---

## Task 17: End-to-end manual test

Skip if testing only via automated suite. For thorough verification:

- [ ] **Step 17.1: Start webgui**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/python webgui.py
```

- [ ] **Step 17.2: Run a small audio through the pipeline with pause-after-transcribe enabled**

Editor should open. Try each Phase 2 action:
1. Change a speaker per segment — verify the dropdown updates without page reload (HTMX)
2. Bulk-rename `SPEAKER_00` → `Anna` — verify all segments update on return
3. Merge two segments — verify count drops by 1 and combined text appears
4. Split a segment at a char position — verify count grows by 1
5. Click "Word view" — edit a word, save, verify segment.text rebuilt
6. Open Undo dropdown — verify history list is shown
7. Click "Undo last action" — verify the last change is reverted
8. Open Diff view — verify edits appear with ins/del highlighting
9. Save & Continue — verify Meta + Render run with updated transcript

- [ ] **Step 17.3: Document any issues**

If anything is broken, fix it as a follow-up commit on this branch.

---

## Task 18: Merge to main

- [ ] **Step 18.1: Final sweep**

```bash
VIRTUAL_ENV=/Users/Shared/code/whisper-pipeline/.venv .venv/bin/pytest tests/ -v 2>&1 | tail -5
```

Confirm ≥150 PASS, 0 failures.

- [ ] **Step 18.2: Verify branch state**

```bash
git status
git log --oneline main..feat/transcript-editor-phase2
```

- [ ] **Step 18.3: Merge**

```bash
git checkout main
git merge --no-ff feat/transcript-editor-phase2 -m "Merge branch 'feat/transcript-editor-phase2' — Transkript-Editor Phase 2

Adds Speaker-Re-Labelling (per-segment + bulk), Merge/Split-Segments,
Word-Level-Edits (no audio re-align), Diff-View vs .original.json,
and Undo-Stack via per-mutation snapshots.

4 new modules, 3 new templates, ~50 new tests (150 total, all passing).

Spec: docs/superpowers/specs/2026-05-27-transcript-editor-phase2-design.md
Plan: docs/superpowers/plans/2026-05-27-transcript-editor-phase2.md

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 18.4: Do NOT push to remote without user authorization.**

---

## Self-Review Notes

After writing this plan, verified:
- ✅ Spec → tasks mapping: Speaker (T1, T2, T9, T10) · Merge/Split (T3, T4, T11) · History (T5, T6, T12) · Words (T7, T13) · Diff (T8, T14) · UI integration (T15) · Docs (T16) · E2E + merge (T17-18)
- ✅ No placeholders (TBD, "appropriate", etc.)
- ✅ Type consistency: `change_speaker(json_path, segment_index, new_speaker)`, `bulk_rename_speaker(...) → int`, `merge_segment(json_path, segment_index)`, `split_segment(json_path, segment_index, char_position)`, `snapshot(json_path, action, metric) → str`, `undo_last(json_path) → dict | None` — all used consistently across tasks
- ✅ File paths absolute and matched to current repo structure
- ✅ TDD discipline maintained per task
- ✅ Critical subtlety in Task 6 (undo_last) is called out: snapshot captures pre-history-append state, so no extra pop needed after restore
- ✅ HTMX integration documented (segment_editor.html partial as canonical target; segments_list.html for full-list swaps after merge/split)
- ✅ Plan size aligned with V1 (~2000 lines for similar scope)
