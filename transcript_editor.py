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

    Returns: {"total_segments": int, "edited_count": int, "backup_created": bool}.
    Backup, SRT/TXT regeneration, and _edited-flag logic are added in later tasks.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    if len(new_texts) != len(segments):
        raise ValueError(
            f"new_texts length {len(new_texts)} != segments length {len(segments)}"
        )
    for seg, new_text in zip(segments, new_texts):
        seg["text"] = new_text
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "total_segments": len(segments),
        "edited_count": 0,
        "backup_created": False,
    }
