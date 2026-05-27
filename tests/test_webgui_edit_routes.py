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
