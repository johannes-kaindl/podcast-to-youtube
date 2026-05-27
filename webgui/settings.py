"""Settings persistence — Theme / tail-default / preferred-defaults."""
import json
from pathlib import Path

DEFAULTS = {
    "theme": "dark",
    "tail_default": True,
    "preferred_visualizer": "dialogue",
    "preferred_model": "large-v3-turbo",
    "pause_after_transcribe": False,
}


def load_settings(path: Path) -> dict:
    if not path.exists():
        return dict(DEFAULTS)
    try:
        on_disk = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(on_disk)
    return merged


def save_settings(path: Path, partial: dict) -> None:
    current = load_settings(path)
    current.update(partial)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")
