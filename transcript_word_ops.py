"""Word-level edit operations.

V1 does not re-align word timings against audio. After a word edit, the
word's start/end remain at the pre-edit values; segment.text is
rebuilt from the (possibly updated) word list.
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


def load_words_flat(json_path: str, segment_index: int | None = None) -> list[dict]:
    """Return a flat list of {word, start, end, score, _edited, segment_index, word_index}.

    If segment_index is given, returns only words for that segment.
    """
    data = _load(json_path)
    out: list[dict] = []
    for seg_i, seg in enumerate(data.get("segments", [])):
        if segment_index is not None and seg_i != segment_index:
            continue
        for word_i, w in enumerate(seg.get("words", [])):
            out.append({
                **w,
                "segment_index": seg_i,
                "word_index": word_i,
            })
    return out


def save_word_edits(json_path: str, segment_index: int, new_words: list[str]) -> dict:
    """Update word strings within a single segment.

    Sets _edited: true on each word whose string changed. Rebuilds the
    segment.text via " ".join(words). Does NOT set segment._edited
    (word-level tracking is separate).

    Returns: {"edited_count": int, "total_words": int}.
    Raises ValueError on length mismatch or out-of-range index.
    """
    data = _load(json_path)
    segments = data.get("segments", [])
    if segment_index < 0 or segment_index >= len(segments):
        raise ValueError(f"segment_index {segment_index} out of range")
    seg = segments[segment_index]
    words = seg.get("words", [])
    if len(new_words) != len(words):
        raise ValueError(
            f"new_words length {len(new_words)} != words length {len(words)}"
        )
    edited_count = 0
    for word, new_str in zip(words, new_words):
        if word.get("word") != new_str:
            word["word"] = new_str
            word["_edited"] = True
            edited_count += 1
    if edited_count > 0:
        # Rebuild segment.text from words
        seg["text"] = " ".join(w.get("word", "") for w in words)
    _save(json_path, data)
    if edited_count > 0:
        regenerate_srt_txt(json_path)
    return {"edited_count": edited_count, "total_words": len(words)}
