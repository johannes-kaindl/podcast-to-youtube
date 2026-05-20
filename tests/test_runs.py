"""Tests for webgui.runs."""
import json
import shutil
from pathlib import Path
import pytest


@pytest.fixture
def output_root(tmp_path, fixtures_dir):
    """Build a tmp output/ tree from the run-states fixtures."""
    root = tmp_path / "output"
    root.mkdir()
    for src in (fixtures_dir / "run-states").glob("*.json"):
        stem = src.stem
        if stem == "empty":
            (root / stem).mkdir()
            (root / stem / "run-state.json").write_text(src.read_text())
            continue
        (root / stem).mkdir()
        shutil.copy(src, root / stem / "run-state.json")
    return root


def test_list_runs_returns_all_valid(output_root):
    from webgui.runs import list_runs
    runs = list_runs(output_root)
    valid_stems = {r.stem for r in runs}
    assert "done" in valid_stems
    assert "running" in valid_stems
    assert "aborted" in valid_stems
    assert "empty" not in valid_stems  # invalid schema → skipped


def test_list_runs_sorted_newest_first(output_root):
    from webgui.runs import list_runs
    runs = list_runs(output_root)
    timestamps = [r.updated_at for r in runs]
    assert timestamps == sorted(timestamps, reverse=True)


def test_run_summary_includes_phase_statuses(output_root):
    from webgui.runs import list_runs
    runs = list_runs(output_root)
    done = next(r for r in runs if r.stem == "done")
    assert done.phases["transcribe"] == "done"
    assert done.phases["upload"] == "done"
    assert done.youtube_url == "https://youtu.be/qC7w-2hL"


def test_aborted_run_has_no_youtube_url(output_root):
    from webgui.runs import list_runs
    runs = list_runs(output_root)
    aborted = next(r for r in runs if r.stem == "aborted")
    assert aborted.youtube_url is None
    assert aborted.phases["render"] == "aborted"


def test_filter_runs_done(output_root):
    from webgui.runs import list_runs, filter_runs
    all_runs = list_runs(output_root)
    done = filter_runs(all_runs, "done")
    assert {r.stem for r in done} == {"done"}


def test_filter_runs_aborted(output_root):
    from webgui.runs import list_runs, filter_runs
    aborted = filter_runs(list_runs(output_root), "aborted")
    assert {r.stem for r in aborted} == {"aborted"}


def test_filter_runs_not_uploaded(output_root):
    from webgui.runs import list_runs, filter_runs
    not_uploaded = filter_runs(list_runs(output_root), "not-uploaded")
    stems = {r.stem for r in not_uploaded}
    # done has upload.done; aborted has upload.skipped, skipped-upload has upload.skipped
    # so only running + partial-resume are not-yet-uploaded
    assert "running" in stems
    assert "partial-resume" in stems
    assert "done" not in stems
