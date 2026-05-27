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
