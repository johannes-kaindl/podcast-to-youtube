"""Tests for webgui.runner — JobRegistry + subprocess spawning."""
import asyncio
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
