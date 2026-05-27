"""Tests for pause-after-transcribe behavior in /api/runs."""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from webgui.app import app
    return TestClient(app)


def test_run_request_accepts_pause_field(client, fixtures_dir, monkeypatch):
    """POST /api/runs with pause_after_transcribe=true should not 422."""
    # Block actual subprocess spawn — we only care about request validation
    from webgui import app as app_mod
    calls = []

    def fake_spawn_pipeline(**kwargs):
        calls.append(kwargs)
        class FakeJob:
            pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    r = client.post("/api/runs", json={
        "audio": str(fixtures_dir / "sample.m4a"),
        "viz": "dialogue", "language": "auto", "model": "tiny",
        "diarize": "off", "episode": "EP TEST", "show_name": "Signal",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": True,
        "pause_after_transcribe": True,
    }, follow_redirects=False)
    assert r.status_code in (303, 200), r.text
    # spawn_pipeline was called
    assert len(calls) == 1


def test_pause_flag_forces_skip_meta_render_upload(client, fixtures_dir, monkeypatch):
    """When pause=true, the spawned command must include skip flags."""
    from webgui import app as app_mod
    captured_cmd = []

    def fake_spawn_pipeline(cmd, **kwargs):
        captured_cmd.append(cmd)
        class FakeJob: pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    client.post("/api/runs", json={
        "audio": str(fixtures_dir / "sample.m4a"),
        "viz": "dialogue", "language": "auto", "model": "tiny",
        "diarize": "off", "episode": "EP TEST", "show_name": "Signal",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": False,
        "pause_after_transcribe": True,
    }, follow_redirects=False)
    assert len(captured_cmd) == 1
    cmd = captured_cmd[0]
    cmd_str = " ".join(cmd)
    assert "--skip-meta" in cmd_str
    assert "--skip-render" in cmd_str
    assert "--skip-upload" in cmd_str


def test_pause_flag_default_false_does_not_inject_skips(client, fixtures_dir, monkeypatch):
    """Without pause flag, skip flags follow the explicit request fields only."""
    from webgui import app as app_mod
    captured_cmd = []

    def fake_spawn_pipeline(cmd, **kwargs):
        captured_cmd.append(cmd)
        class FakeJob: pass
        return FakeJob()

    monkeypatch.setattr(app_mod, "spawn_pipeline", fake_spawn_pipeline)
    monkeypatch.setattr(app_mod.registry, "_slot", None)

    client.post("/api/runs", json={
        "audio": str(fixtures_dir / "sample.m4a"),
        "viz": "dialogue", "language": "auto", "model": "tiny",
        "diarize": "off", "episode": "EP TEST", "show_name": "Signal",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": False,
        "pause_after_transcribe": False,
    }, follow_redirects=False)
    cmd_str = " ".join(captured_cmd[0])
    assert "--skip-meta" not in cmd_str
    assert "--skip-render" not in cmd_str
    # skip_upload was False → no flag injected
    assert "--skip-upload" not in cmd_str
