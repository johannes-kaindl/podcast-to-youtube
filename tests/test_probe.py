"""Tests for webgui.probe."""
import json
from pathlib import Path
import pytest


def test_probe_returns_valid_for_existing_audio(fixtures_dir):
    from webgui.probe import audio_probe
    result = audio_probe(fixtures_dir / "sample.m4a", output_root=fixtures_dir / "_output")
    assert result["valid"] is True
    assert result["stem"] == "sample"
    assert result["format"] in ("m4a", "mp4", "mov,mp4,m4a,3gp,3g2,mj2")
    assert result["duration_s"] == pytest.approx(1.0, abs=0.2)
    assert result["channels"] == 2
    assert result["sample_rate"] == 48000
    assert result["resume_state"] is None
    assert result["disk_free_bytes"] > 0


def test_probe_returns_invalid_for_missing_file(tmp_path):
    from webgui.probe import audio_probe
    result = audio_probe(tmp_path / "missing.m4a", output_root=tmp_path)
    assert result["valid"] is False
    assert result["error"] == "file_not_found"


def test_probe_returns_invalid_for_unsupported_format(tmp_path):
    from webgui.probe import audio_probe
    bad = tmp_path / "doc.flac"
    bad.write_bytes(b"fake")
    result = audio_probe(bad, output_root=tmp_path)
    assert result["valid"] is False
    assert result["error"] == "format_unsupported"


def test_probe_picks_up_resume_state(fixtures_dir, tmp_path):
    """When output/<stem>/run-state.json exists, probe returns it."""
    from webgui.probe import audio_probe
    stem = "sample"
    output_dir = tmp_path / stem
    output_dir.mkdir()
    state = {
        "schema_version": 1, "stem": stem, "audio": str(fixtures_dir / "sample.m4a"),
        "phases": {
            "transcribe": {"status": "done"},
            "meta": {"status": "done"},
            "render": {"status": "aborted"},
            "upload": {"status": "pending"},
        },
    }
    (output_dir / "run-state.json").write_text(json.dumps(state))
    result = audio_probe(fixtures_dir / "sample.m4a", output_root=tmp_path)
    assert result["valid"] is True
    assert result["resume_state"]["phases"]["render"]["status"] == "aborted"


def test_eta_estimate_scales_with_duration():
    from webgui.probe import eta_estimate
    e_short = eta_estimate(duration_s=60, model="large-v3-turbo", viz="dialogue")
    e_long = eta_estimate(duration_s=600, model="large-v3-turbo", viz="dialogue")
    assert e_long["total"] > e_short["total"]
    assert e_long["transcribe"] / e_short["transcribe"] == pytest.approx(10.0, abs=0.1)
