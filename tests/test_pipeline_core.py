"""Tests for pipeline_core shared helpers."""
import os
import sys
from pathlib import Path
import pytest


def test_match_line_detects_transcribe_phase(stdout_snippet):
    from pipeline_core import match_line
    lines = stdout_snippet("transcribe")
    events = [match_line(line, 0) for line in lines]
    assert any(e and e.step == 1 for e in events)
    schritt_event = next(e for e in events if e and "Transkription" in e.label)
    assert schritt_event.progress == 2


def test_match_line_extracts_render_progress(stdout_snippet):
    from pipeline_core import match_line
    lines = stdout_snippet("render")
    pct_events = [match_line(line, 3) for line in lines if "Rendering" in line and "%" in line]
    assert len(pct_events) >= 4
    progresses = [e.progress for e in pct_events if e]
    assert progresses == sorted(progresses)


def test_match_line_returns_none_for_unmatched():
    from pipeline_core import match_line
    assert match_line("random log line that means nothing", 0) is None


def test_build_command_minimal_config():
    from pipeline_core import PipelineConfig, build_command
    cfg = PipelineConfig(
        audio="/tmp/test.m4a", viz="dialogue", language="de",
        model="large-v3-turbo", diarize="auto", episode="EP 01",
        show_name="Signal", skip_transcribe=False, skip_meta=False,
        skip_render=False, skip_upload=False,
    )
    cmd = build_command(cfg, Path("/repo"))
    assert "pipeline.py" in cmd[1]
    assert cmd[2] == "/tmp/test.m4a"
    assert "--viz" in cmd and "dialogue" in cmd


def test_build_command_skip_flags():
    from pipeline_core import PipelineConfig, build_command
    cfg = PipelineConfig(
        audio="/tmp/test.m4a", viz="dialogue", language="de",
        model="large-v3-turbo", diarize="off", episode="EP 01",
        show_name="Signal", skip_transcribe=True, skip_meta=False,
        skip_render=False, skip_upload=True,
    )
    cmd = build_command(cfg, Path("/repo"))
    assert "--skip-transcribe" in cmd
    assert "--skip-upload" in cmd
    assert "--no-diarize" in cmd
    assert "--skip-meta" not in cmd


def test_resolve_audio_path_absolute():
    from pipeline_core import resolve_audio_path
    p = resolve_audio_path("/abs/path.m4a", Path("/some/fallback"))
    assert p == Path("/abs/path.m4a")


def test_resolve_audio_path_user_home(tmp_path, monkeypatch):
    from pipeline_core import resolve_audio_path
    monkeypatch.setenv("HOME", str(tmp_path))
    audio = tmp_path / "foo.m4a"
    audio.write_bytes(b"")
    p = resolve_audio_path("~/foo.m4a", Path("/some/fallback"))
    assert p == audio
