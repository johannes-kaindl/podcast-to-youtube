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


def test_undo_last_restores_pre_mutation_state(sample_run):
    from transcript_history import snapshot, undo_last
    pre_content = sample_run["json_path"].read_text(encoding="utf-8")
    snapshot(str(sample_run["json_path"]), action="edit_text", metric="1 changed")
    # Simulate a mutation: alter segment 0's text
    data = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    data["segments"][0]["text"] = "CHANGED."
    sample_run["json_path"].write_text(json.dumps(data, indent=2), encoding="utf-8")

    entry = undo_last(str(sample_run["json_path"]))
    assert entry is not None
    assert entry["action"] == "edit_text"
    # Content should match pre-snapshot state
    restored = json.loads(sample_run["json_path"].read_text(encoding="utf-8"))
    assert restored["segments"][0]["text"] != "CHANGED."


def test_undo_last_deletes_snapshot_file(sample_run):
    from transcript_history import snapshot, undo_last
    snap_path = snapshot(str(sample_run["json_path"]), action="x", metric="y")
    assert Path(snap_path).exists()
    undo_last(str(sample_run["json_path"]))
    assert not Path(snap_path).exists()


def test_undo_last_returns_none_when_empty(sample_run):
    from transcript_history import undo_last
    entry = undo_last(str(sample_run["json_path"]))
    assert entry is None


def test_list_history_returns_entries_newest_last(sample_run):
    from transcript_history import snapshot, list_history
    snapshot(str(sample_run["json_path"]), action="a", metric="1")
    time.sleep(0.01)
    snapshot(str(sample_run["json_path"]), action="b", metric="2")
    entries = list_history(str(sample_run["json_path"]))
    assert len(entries) == 2
    assert entries[0]["action"] == "a"
    assert entries[1]["action"] == "b"
