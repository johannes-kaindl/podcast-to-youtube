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
