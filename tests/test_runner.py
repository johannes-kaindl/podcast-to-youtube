"""Tests for webgui.runner — JobRegistry + subprocess spawning."""
import asyncio
import sys
from pathlib import Path
import pytest


def test_registry_starts_empty():
    from webgui.runner import JobRegistry
    reg = JobRegistry()
    assert reg.current is None


def test_registry_claim_succeeds_when_empty():
    from webgui.runner import JobRegistry, ActiveJob
    reg = JobRegistry()
    job = ActiveJob(
        stem="folge-082", audio_path=Path("/tmp/a.m4a"),
        output_dir=Path("/tmp/out"), process=None, log_file=Path("/tmp/log"),
        kind="pipeline",
    )
    claimed = reg.try_claim(job)
    assert claimed is True
    assert reg.current is job
    assert reg.current.stem == "folge-082"


def test_registry_claim_fails_when_busy():
    from webgui.runner import JobRegistry, ActiveJob
    reg = JobRegistry()
    first = ActiveJob(stem="first", audio_path=Path("/a"), output_dir=Path("/b"),
                      process=None, log_file=Path("/c"), kind="pipeline")
    second = ActiveJob(stem="second", audio_path=Path("/a"), output_dir=Path("/b"),
                       process=None, log_file=Path("/c"), kind="pipeline")
    reg.try_claim(first)
    assert reg.try_claim(second) is False
    assert reg.current.stem == "first"


def test_registry_release_frees_slot():
    from webgui.runner import JobRegistry, ActiveJob
    reg = JobRegistry()
    job = ActiveJob(stem="x", audio_path=Path("/a"), output_dir=Path("/b"),
                    process=None, log_file=Path("/c"), kind="pipeline")
    reg.try_claim(job)
    reg.release(job)
    assert reg.current is None


def test_registry_release_ignores_wrong_job():
    """Releasing a job that doesn't match current should not free the slot."""
    from webgui.runner import JobRegistry, ActiveJob
    reg = JobRegistry()
    real = ActiveJob(stem="real", audio_path=Path("/a"), output_dir=Path("/b"),
                     process=None, log_file=Path("/c"), kind="pipeline")
    other = ActiveJob(stem="other", audio_path=Path("/a"), output_dir=Path("/b"),
                      process=None, log_file=Path("/c"), kind="pipeline")
    reg.try_claim(real)
    reg.release(other)
    assert reg.current is real


def test_spawn_pipeline_writes_to_logfile_and_releases_slot(tmp_path):
    """End-to-end: spawn mock pipeline, verify log file populated + slot freed after exit."""
    from webgui.runner import spawn_pipeline, JobRegistry
    import time

    reg = JobRegistry()
    output_dir = tmp_path / "stem-x"
    output_dir.mkdir()
    log_file = output_dir / "run-test.log"

    mock_cmd = [sys.executable, str(Path("tests/fixtures/mock_pipeline.py"))]
    job = spawn_pipeline(
        cmd=mock_cmd,
        stem="stem-x",
        audio_path=Path("/tmp/a.m4a"),
        output_dir=output_dir,
        log_file=log_file,
        registry=reg,
    )

    job.process.wait(timeout=10)

    # Wait briefly for reader thread to finish + release
    for _ in range(30):
        if reg.current is None:
            break
        time.sleep(0.1)

    log_contents = log_file.read_text()
    assert "SCHRITT 1" in log_contents
    assert "Rendering 100.0%" in log_contents
    assert reg.current is None


def test_spawn_pipeline_fails_when_slot_busy(tmp_path):
    from webgui.runner import spawn_pipeline, JobRegistry, ActiveJob

    reg = JobRegistry()
    existing = ActiveJob(
        stem="busy", audio_path=Path("/a"), output_dir=Path("/b"),
        process=None, log_file=Path("/c"), kind="pipeline",
    )
    reg.try_claim(existing)

    with pytest.raises(RuntimeError) as exc:
        spawn_pipeline(
            cmd=[sys.executable, "-c", "pass"],
            stem="new", audio_path=Path("/tmp/a.m4a"),
            output_dir=tmp_path, log_file=tmp_path / "x.log",
            registry=reg,
        )
    assert "busy" in str(exc.value).lower() or "slot" in str(exc.value).lower()


def test_spawn_pipeline_releases_slot_when_popen_fails(tmp_path):
    """Critical: if Popen raises (bad binary, OS error), the slot must NOT
    stay claimed — otherwise the singleton registry becomes permanently
    unusable. Regression guard for T6/T7 code-quality review finding."""
    from webgui.runner import spawn_pipeline, JobRegistry

    reg = JobRegistry()
    with pytest.raises(FileNotFoundError):
        spawn_pipeline(
            cmd=["/nonexistent/binary/that/cannot/be/found-xyz"],
            stem="failed-spawn",
            audio_path=Path("/tmp/a.m4a"),
            output_dir=tmp_path / "out",
            log_file=tmp_path / "out" / "x.log",
            registry=reg,
        )
    # Slot must be free even though Popen blew up
    assert reg.current is None
