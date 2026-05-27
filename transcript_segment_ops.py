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


def bulk_rename_speaker(json_path: str, old_name: str, new_name: str) -> int:
    """Rename every segment whose speaker == old_name to new_name.

    Does NOT set _speaker_edited (this is a display rename, not a diarization fix).
    Returns the count of renamed segments.
    """
    if not old_name or not new_name:
        raise ValueError("both names must be non-empty")
    if old_name == new_name:
        raise ValueError("old and new names must differ")
    if len(new_name) > 64:
        raise ValueError("new name too long (max 64 chars)")
    data = _load(json_path)
    count = 0
    for seg in data.get("segments", []):
        if seg.get("speaker") == old_name:
            seg["speaker"] = new_name
            count += 1
    if count > 0:
        _save(json_path, data)
        regenerate_srt_txt(json_path)
    return count


def merge_segment(json_path: str, segment_index: int) -> None:
    """Merge segments[index] with segments[index+1] in-place.

    The combined text uses single-space join. words are concatenated.
    Resulting segment has start=current.start, end=next.end,
    speaker=current.speaker. Sets _merged_from = [index, index+1].
    Clears _split_from (mutually exclusive with merged_from).

    Raises ValueError if index has no successor.
    """
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments) - 1:
        raise ValueError(f"segment {segment_index}: no next segment to merge with")
    curr = segments[segment_index]
    nxt = segments[segment_index + 1]
    merged = {
        "start": curr["start"],
        "end": nxt["end"],
        "text": curr["text"] + " " + nxt["text"],
        "speaker": curr.get("speaker", "SPEAKER_00"),
        "words": curr.get("words", []) + nxt.get("words", []),
        "_merged_from": [segment_index, segment_index + 1],
    }
    # Carry over edit flags from curr (preserves "user touched this" history)
    for flag in ("_edited", "_speaker_edited"):
        if curr.get(flag):
            merged[flag] = True
    segments[segment_index:segment_index + 2] = [merged]
    _save(json_path, data)
    regenerate_srt_txt(json_path)
