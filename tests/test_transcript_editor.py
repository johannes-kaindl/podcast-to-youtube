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
