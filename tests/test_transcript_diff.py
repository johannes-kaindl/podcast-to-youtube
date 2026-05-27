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
