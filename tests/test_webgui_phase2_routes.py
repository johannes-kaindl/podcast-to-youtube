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
