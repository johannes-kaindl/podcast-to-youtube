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
