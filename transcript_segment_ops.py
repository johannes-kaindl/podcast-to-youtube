"""Segment-level operations: merge, split, change_speaker, bulk_rename_speaker.

All operations work on the WhisperX JSON in-place and regenerate SRT/TXT
siblings via transcript_editor.regenerate_srt_txt.
"""
import json
from pathlib import Path

from transcript_editor import regenerate_srt_txt


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def _save(json_path: str, data: dict) -> None:
    Path(json_path).write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def change_speaker(json_path: str, segment_index: int, new_speaker: str) -> None:
    """Change segment speaker; sets _speaker_edited flag if value changed.

    Raises ValueError on empty new_speaker or out-of-range index.
    """
    if not new_speaker or not new_speaker.strip():
        raise ValueError("speaker name must be non-empty")
    if len(new_speaker) > 64:
        raise ValueError("speaker name too long (max 64 chars)")
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments):
        raise ValueError(f"segment_index {segment_index} out of range")
    seg = segments[segment_index]
    if seg.get("speaker") == new_speaker:
        return  # no-op
    seg["speaker"] = new_speaker
    seg["_speaker_edited"] = True
    _save(json_path, data)
    regenerate_srt_txt(json_path)
