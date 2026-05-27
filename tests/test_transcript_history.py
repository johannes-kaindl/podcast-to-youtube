"""Tests for transcript_history — snapshot, undo_last, cleanup."""
import json
import shutil
import time
from pathlib import Path
import pytest


@pytest.fixture
def sample_run(tmp_path, fixtures_dir):
    stem = "ep01"
    run_dir = tmp_path / stem
    run_dir.mkdir()
    src = fixtures_dir / "sample-transcript.whisperx.json"
    dst = run_dir / f"{stem}.whisperx.json"
    shutil.copy(src, dst)
    return {"dir": run_dir, "stem": stem, "json_path": dst}


def test_snapshot_creates_file(sample_run):
    from transcript_history import snapshot
    snap_path = snapshot(str(sample_run["json_path"]), action="edit_text", metric="1 segment edited")
    assert Path(snap_path).exists()
    # File should be a sibling under snapshots/
    assert "snapshots" in str(snap_path)


def test_snapshot_content_matches_pre_mutation(sample_run):
    from transcript_history import snapshot
    pre_content = sample_run["json_path"].read_text(encoding="utf-8")
    snap_path = snapshot(str(sample_run["json_path"]), action="edit_text", metric="x")
    # Snapshot file must contain the PRE-mutation state (caller hasn't mutated yet)
    assert Path(snap_path).read_text(encoding="utf-8") == pre_content


def test_snapshot_appends_history_entry(sample_run):
    from transcript_history import snapshot
    snapshot(str(sample_run["json_path"]), action="edit_text", metric="1 segment edited")
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    history = data.get("_history", [])
    assert len(history) == 1
    assert history[0]["action"] == "edit_text"
    assert history[0]["metric"] == "1 segment edited"
    assert "ts" in history[0]
    assert "snapshot" in history[0]


def test_snapshot_history_path_is_relative(sample_run):
    from transcript_history import snapshot
    snap_path = snapshot(str(sample_run["json_path"]), action="merge", metric="0+1")
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # Stored path should be relative to output dir: "snapshots/<ts>.json"
    rel = data["_history"][-1]["snapshot"]
    assert rel.startswith("snapshots/")
    assert rel.endswith(".json")


def test_cleanup_snapshots_keeps_cap(sample_run, monkeypatch):
    from transcript_history import snapshot, cleanup_snapshots, SNAPSHOT_CAP
    # Force a small cap for the test
    monkeypatch.setattr("transcript_history.SNAPSHOT_CAP", 3)
    for i in range(5):
        snapshot(str(sample_run["json_path"]), action="x", metric=f"{i}")
        time.sleep(0.01)  # ensure ts ordering
    cleanup_snapshots(str(sample_run["json_path"]))
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    # Only 3 history entries should remain
    assert len(data["_history"]) == 3
    # Corresponding snapshot files: also 3
    snap_dir = sample_run["dir"] / "snapshots"
    assert len(list(snap_dir.glob("*.json"))) == 3
