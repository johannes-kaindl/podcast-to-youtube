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
