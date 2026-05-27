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


def _backup_path_for(json_path: Path) -> Path:
    """Given <stem>.whisperx.json, return <stem>.whisperx.original.json."""
    # json_path.stem strips only the LAST .json suffix → keep ".whisperx" intact
    return json_path.with_name(json_path.stem + ".original.json")


def save_edits(json_path: str, new_texts: list[str]) -> dict:
    """Update each segment's text from new_texts (parallel list).

    On first save, creates a one-time backup at <stem>.whisperx.original.json.
    Sets `_edited: true` on segments where the new text differs from the existing.
    Returns: {"total_segments": int, "edited_count": int, "backup_created": bool}.
    """
    path = Path(json_path)
    backup_path = _backup_path_for(path)
    backup_created = False
    if not backup_path.exists():
        shutil.copy2(path, backup_path)
        backup_created = True

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
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    regenerate_srt_txt(str(path))
    return {
        "total_segments": len(segments),
        "edited_count": edited_count,
        "backup_created": backup_created,
    }


def has_been_edited(json_path: str) -> bool:
    """Return True if any segment in the JSON has _edited: true."""
    path = Path(json_path)
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    return any(seg.get("_edited") for seg in data.get("segments", []))


def _format_srt_time(seconds: float) -> str:
    """HH:MM:SS,mmm — matches transcribe.format_srt_time byte-for-byte."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def regenerate_srt_txt(json_path: str) -> tuple[str, str]:
    """Rewrite <stem>.srt and <stem>.txt siblings from the JSON segments.

    Same format as transcribe.py — SRT carries [SPEAKER_id] prefix per cue,
    TXT groups consecutive same-speaker segments under a speaker header.
    Returns (srt_path, txt_path) as strings.
    """
    path = Path(json_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])
    # Strip ".whisperx" from path.stem to recover the base stem ("ep01.whisperx" → "ep01")
    base_stem = path.stem
    if base_stem.endswith(".whisperx"):
        base_stem = base_stem[: -len(".whisperx")]
    srt_path = path.parent / f"{base_stem}.srt"
    txt_path = path.parent / f"{base_stem}.txt"

    with srt_path.open("w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            speaker = seg.get("speaker", "SPEAKER_00")
            text = f"[{speaker}] {seg['text'].strip()}"
            f.write(
                f"{i}\n"
                f"{_format_srt_time(seg['start'])} --> {_format_srt_time(seg['end'])}\n"
                f"{text}\n\n"
            )

    with txt_path.open("w", encoding="utf-8") as f:
        current_speaker = None
        for seg in segments:
            speaker = seg.get("speaker", "SPEAKER_00")
            if speaker != current_speaker:
                current_speaker = speaker
                f.write(f"\n{speaker}:\n")
            f.write(seg["text"].strip() + " ")
        f.write("\n")

    return str(srt_path), str(txt_path)


def invalidate_downstream(run_state_path: str) -> list[str]:
    """Reset meta + render phases to 'pending' if they were 'done'.

    Returns list of invalidated phase names. Upload is intentionally left
    alone — V1 treats edits as affecting transcript-derived artifacts only.
    """
    path = Path(run_state_path)
    if not path.exists():
        return []
    state = json.loads(path.read_text(encoding="utf-8"))
    phases = state.setdefault("phases", {})
    invalidated: list[str] = []
    for phase in ("meta", "render"):
        entry = phases.get(phase, {})
        if entry.get("status") == "done":
            phases[phase] = {"status": "pending"}
            invalidated.append(phase)
    if invalidated:
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    return invalidated
