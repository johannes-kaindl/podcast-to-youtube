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


def test_phases_fragment_renders(client, populated_output):
    """GET /runs/{stem}/phases renders the phase-indicator partial with status."""
    r = client.get("/runs/done/phases")
    assert r.status_code == 200
    # "done" fixture has all four phases done
    assert 'data-status="done"' in r.text
    assert 'Transcribe' in r.text


def test_progress_fragment_renders(client):
    r = client.get("/runs/anything/progress?value=42&label=Rendering+45%25")
    assert r.status_code == 200
    assert "42" in r.text


def test_runs_detail_running_variant(client, populated_output):
    """Running state shows live-log section."""
    r = client.get("/runs/running")
    assert r.status_code == 200
    # Running state should include the log panel
    assert "stdout" in r.text.lower() or "log" in r.text.lower()


def test_runs_detail_done_variant(client, populated_output):
    """Done state shows YouTube URL."""
    r = client.get("/runs/done")
    assert r.status_code == 200
    assert "youtu.be" in r.text or "youtube" in r.text.lower()


def test_runs_detail_aborted_variant(client, populated_output):
    """Aborted state shows error message."""
    r = client.get("/runs/aborted")
    assert r.status_code == 200
    assert "aborted" in r.text.lower() or "error" in r.text.lower()


def test_runs_detail_404_unknown_stem(client, populated_output):
    r = client.get("/runs/does-not-exist")
    assert r.status_code == 404


def test_resume_banner_aborted_variant(client, populated_output):
    r = client.get("/runs/aborted/resume-banner")
    assert r.status_code == 200
    assert "aborted" in r.text.lower()


def test_resume_banner_complete_variant(client, populated_output):
    r = client.get("/runs/done/resume-banner")
    assert r.status_code == 200
    assert "complete" in r.text.lower() or "loop closed" in r.text.lower()


def test_preview_mp4_404_when_missing(client, tmp_path, monkeypatch):
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    r = client.get("/runs/no-such-run/preview.mp4")
    assert r.status_code == 404


def test_preview_mp4_serves_file(client, tmp_path, monkeypatch):
    from webgui import app as app_mod
    output = tmp_path / "output" / "stem-1"
    output.mkdir(parents=True)
    mp4 = output / "stem-1-dialogue.mp4"
    mp4.write_bytes(b"\x00\x00\x00\x20ftypmp42" + b"\x00" * 1000)
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    r = client.get("/runs/stem-1/preview.mp4")
    assert r.status_code == 200
    assert r.headers["content-type"] == "video/mp4"
    assert len(r.content) > 1000


def test_preview_mp4_range_request(client, tmp_path, monkeypatch):
    from webgui import app as app_mod
    output = tmp_path / "output" / "stem-2"
    output.mkdir(parents=True)
    mp4 = output / "stem-2-dialogue.mp4"
    content = bytes(range(256)) * 4  # 1024 deterministic bytes
    mp4.write_bytes(content)
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    r = client.get("/runs/stem-2/preview.mp4", headers={"Range": "bytes=100-199"})
    assert r.status_code == 206
    assert r.headers["content-range"] == "bytes 100-199/1024"
    assert r.content == content[100:200]


def test_find_mp4_prefers_run_state_output(tmp_path, monkeypatch):
    """With several .mp4 variants present, the one named in run-state wins."""
    import json
    from webgui import app as app_mod
    output = tmp_path / "output" / "stem-m"
    output.mkdir(parents=True)
    # Alphabetically `waveform` sorts last — the old sorted()[-1] picked it.
    (output / "stem-m-monologue.mp4").write_bytes(b"mono")
    (output / "stem-m-waveform.mp4").write_bytes(b"wave")
    (output / "run-state.json").write_text(json.dumps(
        {"phases": {"render": {"status": "done", "output": "stem-m-monologue.mp4"}}}
    ))
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    assert app_mod._find_mp4("stem-m").name == "stem-m-monologue.mp4"


def test_find_mp4_falls_back_to_newest(tmp_path, monkeypatch):
    """Without a run-state render output, the newest .mp4 by mtime wins."""
    import os
    import time
    from webgui import app as app_mod
    output = tmp_path / "output" / "stem-n"
    output.mkdir(parents=True)
    older = output / "stem-n-waveform.mp4"
    older.write_bytes(b"old")
    newer = output / "stem-n-dialogue.mp4"  # sorts before waveform alphabetically
    newer.write_bytes(b"new")
    past = time.time() - 100
    os.utime(older, (past, past))
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    assert app_mod._find_mp4("stem-n").name == "stem-n-dialogue.mp4"


def test_upload_returns_404_if_no_mp4(client, tmp_path, monkeypatch):
    from webgui import app as app_mod, runner
    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    (tmp_path / "output" / "stem-z").mkdir(parents=True)
    r = client.post("/runs/stem-z/upload", json={"privacy": "private"})
    assert r.status_code == 404


def test_upload_rejects_public_privacy(client, tmp_path, monkeypatch):
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    (tmp_path / "output" / "stem-q").mkdir(parents=True)
    (tmp_path / "output" / "stem-q" / "stem-q-dialogue.mp4").write_bytes(b"x")
    r = client.post("/runs/stem-q/upload", json={"privacy": "public"})
    assert r.status_code == 400


def test_skip_upload_marks_state(client, tmp_path, monkeypatch):
    import json as _json
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    output = tmp_path / "output" / "stem-r"
    output.mkdir(parents=True)
    state = {
        "schema_version": 1, "stem": "stem-r", "audio": "/x",
        "started_at": "2026-05-20T10:00:00Z", "updated_at": "2026-05-20T10:30:00Z",
        "phases": {"transcribe": {"status":"done"}, "meta": {"status":"done"},
                   "render": {"status":"done"}, "upload": {"status":"pending"}},
    }
    (output / "run-state.json").write_text(_json.dumps(state))
    r = client.post("/runs/stem-r/skip-upload")
    assert r.status_code == 204
    fresh = _json.loads((output / "run-state.json").read_text())
    assert fresh["phases"]["upload"]["status"] == "skipped"


def test_abort_run_sigterms_subprocess(client, tmp_path, monkeypatch):
    import sys, time
    from webgui import app as app_mod, runner

    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")

    output = tmp_path / "output" / "abort-stem"
    output.mkdir(parents=True)
    long_cmd = [sys.executable, "-c", "import time; print('hi', flush=True); time.sleep(30)"]
    runner.spawn_pipeline(
        cmd=long_cmd, stem="abort-stem",
        audio_path=Path("/x"), output_dir=output, log_file=output / "x.log",
        registry=runner.registry,
    )
    time.sleep(0.5)
    r = client.post("/runs/abort-stem/abort")
    assert r.status_code == 204
    time.sleep(0.5)
    assert runner.registry.current is None


def test_abort_unknown_run_returns_404(client, tmp_path, monkeypatch):
    from webgui import app as app_mod, runner
    runner.registry = runner.JobRegistry()
    monkeypatch.setattr(app_mod, "registry", runner.registry)
    r = client.post("/runs/no-such-stem/abort")
    assert r.status_code == 404


def test_open_finder_path_must_be_inside_repo(client, tmp_path, monkeypatch):
    from webgui import app as app_mod
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    r = client.post("/open/finder", json={"path": "/etc/passwd"})
    assert r.status_code == 400


def test_config_form_renders_pause_checkbox(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'name="pause_after_transcribe"' in r.text
    assert "Pause after transcribe" in r.text


def test_run_detail_shows_edit_cta_when_transcript_exists(client, populated_output, fixtures_dir):
    """Any run with transcribe.status=done and a .whisperx.json should expose the Edit CTA."""
    import shutil
    import json as _json
    # Create a fresh stem dir with both a transcript JSON and a run-state file
    target = populated_output / "folge-082"
    target.mkdir(exist_ok=True)
    shutil.copy(fixtures_dir / "sample-transcript.whisperx.json",
                target / "folge-082.whisperx.json")
    state = {
        "schema_version": 1,
        "stem": "folge-082",
        "config": {"show_name": "Test", "episode": "EP 82", "viz_type": "dialogue"},
        "phases": {
            "transcribe": {"status": "done"},
            "meta": {"status": "done"},
            "render": {"status": "pending"},
            "upload": {"status": "pending"},
        },
    }
    (target / "run-state.json").write_text(_json.dumps(state, indent=2), encoding="utf-8")

    r = client.get("/runs/folge-082")
    assert r.status_code == 200
    assert "Edit transcript" in r.text or "edit-transcript" in r.text.lower()


def test_run_detail_no_edit_cta_when_transcript_missing(client, populated_output):
    """Runs without a transcript JSON should not show the Edit CTA."""
    # The 'aborted' fixture dir has a run-state but no .whisperx.json file
    r = client.get("/runs/aborted")
    assert r.status_code == 200
    # If transcript file is missing, Edit-CTA must NOT appear
    assert "Edit transcript" not in r.text


def test_open_finder_calls_open_minus_R(client, tmp_path, monkeypatch):
    import subprocess
    from webgui import app as app_mod
    calls = []
    monkeypatch.setattr(app_mod, "OUTPUT_ROOT", tmp_path / "output")
    (tmp_path / "output" / "stem-a").mkdir(parents=True)
    target = tmp_path / "output" / "stem-a" / "video.mp4"
    target.write_bytes(b"x")

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0)
    monkeypatch.setattr(app_mod.subprocess, "run", fake_run)

    r = client.post("/open/finder", json={"path": str(target)})
    assert r.status_code == 204
    assert calls and calls[0][:2] == ["open", "-R"]
