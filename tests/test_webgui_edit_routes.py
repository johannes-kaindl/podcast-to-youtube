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


def test_post_edit_save_updates_json_and_redirects(client, populated_run):
    json_path = populated_run / "ep01" / "ep01.whisperx.json"
    form = {
        "segment_text_0": "All right!!",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-return",
    }
    r = client.post(f"/runs/ep01/edit", data=form, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/runs/ep01"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["segments"][0]["text"] == "All right!!"
    assert data["segments"][0].get("_edited") is True


def test_post_edit_save_invalidates_downstream(client, populated_run):
    state_path = populated_run / "ep01" / "run-state.json"
    form = {
        "segment_text_0": "Changed.",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-return",
    }
    client.post(f"/runs/ep01/edit", data=form, follow_redirects=False)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["phases"]["meta"]["status"] == "pending"
    assert state["phases"]["render"]["status"] == "pending"
    assert state["phases"]["transcribe"]["status"] == "done"


def test_post_edit_404_when_transcribe_missing(client, tmp_path, monkeypatch):
    out = tmp_path / "output"
    (out / "ghost").mkdir(parents=True)
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    r = client.post("/runs/ghost/edit", data={"action": "save-return"},
                    follow_redirects=False)
    assert r.status_code == 404


def test_post_edit_save_continue_triggers_meta_phase(client, populated_run, monkeypatch):
    """POST with action=save-continue should redirect (307) to
    /runs/{stem}/phase/meta/start, which then spawns the pipeline."""
    from webgui import app as app_mod
    calls = []

    def fake_spawn_pipeline(cmd, **kwargs):
        calls.append({"cmd": cmd, **kwargs})
        class FakeJob: pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    form = {
        "segment_text_0": "Changed.",
        "original_text_0": " All right.",
        "segment_text_1": "Let's dive into this autopoiesis thing.",
        "original_text_1": "Let's dive into this autopoiesis thing.",
        "segment_text_2": "Sounds good to me.",
        "original_text_2": "Sounds good to me.",
        "action": "save-continue",
    }
    r = client.post(f"/runs/ep01/edit", data=form, follow_redirects=True)
    # follow_redirects=True traverses 307 -> phase/meta/start -> 303 -> /runs/ep01
    assert r.status_code == 200
    # spawn_pipeline was called for the meta phase
    assert len(calls) == 1
    cmd_str = " ".join(calls[0]["cmd"])
    # Meta phase runs => --skip-meta is NOT in the cmd; other skips ARE
    assert "--skip-meta" not in cmd_str
    assert "--skip-transcribe" in cmd_str
    assert "--skip-render" in cmd_str
    assert "--skip-upload" in cmd_str
