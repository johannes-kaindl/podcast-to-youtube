"""Transcript editor helpers — load, save, regenerate, invalidate.

Pure Python, no FastAPI dependency. Tested standalone in
tests/test_transcript_editor.py.
"""
import json
import shutil
from pathlib import Path


def load_segments(json_path: str) -> list[dict]:
    """Return the list of segments from a WhisperX JSON file.

    Each segment dict carries: start, end, text, speaker, words (list),
    _edited (bool, defaults False if absent).
    """
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    return data.get("segments", [])


def save_edits(json_path: str, new_texts: list[str]) -> dict:
    """Update each segment's text from new_texts (parallel list).

    Sets `_edited: true` on segments where the new text differs from the existing.
    Returns: {"total_segments": int, "edited_count": int, "backup_created": bool}.
    Backup and SRT/TXT regeneration are added in later tasks.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    if len(new_texts) != len(segments):
        raise ValueError(
            f"new_texts length {len(new_texts)} != segments length {len(segments)}"
        )
    edited_count = 0
    for seg, new_text in zip(segments, new_texts):
        if seg.get("text") != new_text:
            seg["text"] = new_text
            seg["_edited"] = True
            edited_count += 1
        # else: leave seg untouched (keep prior _edited flag if it was set)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "total_segments": len(segments),
        "edited_count": edited_count,
        "backup_created": False,
    }


def has_been_edited(json_path: str) -> bool:
    """Return True if any segment in the JSON has _edited: true."""
    path = Path(json_path)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return any(seg.get("_edited") for seg in data.get("segments", []))
