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
