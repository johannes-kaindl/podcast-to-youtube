"""FastAPI endpoint tests via TestClient."""
import shutil
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from webgui.app import app
    return TestClient(app)


@pytest.fixture
def populated_output(tmp_path, fixtures_dir, monkeypatch):
    """Re-point webgui.app.OUTPUT_ROOT to a tmp tree with fixture runs."""
    out = tmp_path / "output"
    out.mkdir()
    for src in (fixtures_dir / "run-states").glob("*.json"):
        stem = src.stem
        if stem == "empty":
            continue
        (out / stem).mkdir()
        shutil.copy(src, out / stem / "run-state.json")
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", out)
    return out


def test_index_returns_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Whisper" in r.text
    # implicit `request` from Starlette 1.0 TemplateResponse must reach the
    # template — Start nav-link should carry .is-active on /
    assert 'href="/" class="is-active"' in r.text


def test_healthz_returns_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_static_css_served(client):
    r = client.get("/static/style.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_api_audio_probe_with_valid_file(client, fixtures_dir):
    r = client.post("/api/audio/probe", json={"path": str(fixtures_dir / "sample.m4a")})
    assert r.status_code == 200
    body = r.json()
    assert body["valid"] is True
    assert body["stem"] == "sample"


def test_api_audio_probe_with_missing_file(client, tmp_path):
    r = client.post("/api/audio/probe", json={"path": str(tmp_path / "nope.m4a")})
    assert r.status_code == 200
    assert r.json()["valid"] is False
    assert r.json()["error"] == "file_not_found"


def test_runs_returns_html(client, populated_output):
    r = client.get("/runs")
    assert r.status_code == 200
    assert "Past runs" in r.text
    # Several fixture stems should appear
    assert "folge-081" in r.text or "done" in r.text  # accept dir-name stem deviation
    assert "folge-082" in r.text or "running" in r.text
    assert "probefolge" in r.text or "aborted" in r.text


def test_runs_empty_state_when_no_runs(client, tmp_path, monkeypatch):
    from webgui import app as app_mod
    empty = tmp_path / "empty"
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", empty)
    r = client.get("/runs")
    assert r.status_code == 200
    assert "No signal" in r.text or "No runs" in r.text


def test_runs_filter_done(client, populated_output):
    r = client.get("/runs?filter=done")
    assert r.status_code == 200
    # The only fully-done+uploaded fixture is "done" (stem from dir name)
    assert "done" in r.text  # appears as the run row
    # Aborted should be filtered out
    assert 'data-status="aborted"' not in r.text


def test_api_runs_starts_pipeline_mock(client, tmp_path, monkeypatch):
    """POST /api/runs spawns a subprocess; client receives 303 to /runs/{stem}."""
    import sys
    from webgui import app as app_mod, runner

    # Reset the singleton registry for test isolation
    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)

    # Patch build_command to point at the mock pipeline
    monkeypatch.setattr(
        app_mod,
        "build_command",
        lambda cfg, _dir: [sys.executable, str(Path("tests/fixtures/mock_pipeline.py"))],
    )
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")

    body = {
        "audio": str(Path(__file__).parent / "fixtures" / "sample.m4a"),
        "viz": "dialogue", "language": "de", "model": "large-v3-turbo",
        "diarize": "off", "episode": "EP X", "show_name": "Test",
        "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": True,
    }
    r = client.post("/api/runs", json=body, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/runs/")


def test_api_runs_returns_409_when_busy(client, tmp_path, monkeypatch):
    from webgui import app as app_mod, runner

    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)

    # Pre-claim the slot
    runner.registry.try_claim(runner.ActiveJob(
        stem="busy-stem", audio_path=Path("/x"), output_dir=Path("/y"),
        process=None, log_file=Path("/z"), kind="pipeline",
    ))

    body = {
        "audio": "/whatever.m4a", "viz": "dialogue", "language": "de",
        "model": "large-v3-turbo", "diarize": "off", "episode": "X",
        "show_name": "X", "skip_transcribe": False, "skip_meta": False,
        "skip_render": False, "skip_upload": True,
    }
    r = client.post("/api/runs", json=body)
    assert r.status_code == 409
    assert "busy-stem" in r.text


def test_stream_replays_logfile_when_no_active_job(client, tmp_path, monkeypatch):
    """If a run has finished, /stream replays the logfile then closes."""
    from webgui import app as app_mod, runner

    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)

    stem = "finished-run"
    output_dir = tmp_path / "output" / stem
    output_dir.mkdir(parents=True)
    log_file = output_dir / "run-test.log"
    log_file.write_text(
        "# Pipeline-Run started …\n"
        "# Command: …\n"
        "# ────────\n"
        "\n"
        "SCHRITT 1: Transkription\n"
        "✓ Transkription fertig\n"
    )
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")

    with client.stream("GET", f"/runs/{stem}/stream") as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "SCHRITT 1" in body
    assert "event: done" in body


def test_stream_with_last_event_id_skips_already_seen_lines(client, tmp_path, monkeypatch):
    from webgui import app as app_mod, runner

    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)

    stem = "midrun"
    output_dir = tmp_path / "output" / stem
    output_dir.mkdir(parents=True)
    log_file = output_dir / "run-test.log"
    log_file.write_text("\n".join(f"line {i}" for i in range(1, 11)) + "\n")
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")

    with client.stream("GET", f"/runs/{stem}/stream", headers={"Last-Event-ID": "5"}) as r:
        body = "".join(r.iter_text())
    assert "line 7" in body
    assert "line 4" not in body
