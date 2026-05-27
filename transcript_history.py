"""Snapshots + undo stack for transcript edits.

Each mutating operation calls snapshot() BEFORE the mutation, capturing
the pre-mutation JSON. _history[] in the main JSON references each
snapshot. cleanup_snapshots enforces SNAPSHOT_CAP.
"""
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_CAP = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _save(json_path: str, data: dict) -> None:
    Path(json_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def snapshot(json_path: str, action: str, metric: str) -> str:
    """Save a pre-mutation snapshot and append a _history entry.

    Returns absolute path to the snapshot file.
    Snapshot is written BEFORE the caller mutates json_path, so it reflects
    the state to revert TO if undone.
    """
    path = Path(json_path)
    snap_dir = path.parent / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    # Use millisecond-precision timestamp so rapid successive snapshots don't collide
    ts = int(time.time() * 1000)
    snap_file = snap_dir / f"{ts}.json"
    # Ensure unique filename if same ms-tick
    while snap_file.exists():
        ts += 1
        snap_file = snap_dir / f"{ts}.json"
    shutil.copy2(path, snap_file)

    data = _load(json_path)
    data.setdefault("_history", []).append({
        "ts": _now_iso(),
        "action": action,
        "metric": metric,
        "snapshot": f"snapshots/{snap_file.name}",
    })
    _save(json_path, data)
    return str(snap_file)


def cleanup_snapshots(json_path: str) -> int:
    """Delete oldest snapshots beyond SNAPSHOT_CAP. Returns count deleted."""
    data = _load(json_path)
    history = data.get("_history", [])
    if len(history) <= SNAPSHOT_CAP:
        return 0
    excess = len(history) - SNAPSHOT_CAP
    to_remove = history[:excess]
    parent = Path(json_path).parent
    deleted = 0
    for entry in to_remove:
        snap_rel = entry.get("snapshot", "")
        if snap_rel:
            snap_path = parent / snap_rel
            if snap_path.exists():
                snap_path.unlink()
                deleted += 1
    data["_history"] = history[excess:]
    _save(json_path, data)
    return deleted
