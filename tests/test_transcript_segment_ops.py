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
