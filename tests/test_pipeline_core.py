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
    assert schritt_event.step == 1
    assert 0 < schritt_event.progress < 100


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


def test_resolve_audio_path_falls_back_to_pipeline_dir(tmp_path, monkeypatch):
    """When the cwd-relative path doesn't exist, resolve falls back to fallback_dir."""
    from pipeline_core import resolve_audio_path
    fallback = tmp_path / "fallback"
    fallback.mkdir()
    audio = fallback / "foo.m4a"
    audio.write_bytes(b"")
    monkeypatch.chdir(tmp_path / "elsewhere" if False else tmp_path)  # ensure cwd isn't fallback
    other_cwd = tmp_path / "other-cwd"
    other_cwd.mkdir()
    monkeypatch.chdir(other_cwd)
    p = resolve_audio_path("foo.m4a", fallback)
    assert p == audio


def test_match_line_render_pct_only_matches_rendering_lines():
    """A percent in an unrelated log line must not trigger render progress."""
    from pipeline_core import match_line
    # current_step==3 means we ARE in the render phase
    # but lines without 'Rendering' prefix should not be classified as render-progress
    assert match_line("Upload 50% complete", 3) is None
    assert match_line("Some 25% stat from elsewhere", 3) is None
    # genuine render line should still match
    evt = match_line("Rendering 42.0%", 3)
    assert evt is not None
    assert evt.step == 3


def test_resolve_audio_path_user_home(tmp_path, monkeypatch):
    from pipeline_core import resolve_audio_path
    monkeypatch.setenv("HOME", str(tmp_path))
    audio = tmp_path / "foo.m4a"
    audio.write_bytes(b"")
    p = resolve_audio_path("~/foo.m4a", Path("/some/fallback"))
    assert p == audio
