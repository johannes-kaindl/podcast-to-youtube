"""Diff transcript vs. .original.json snapshot.

Pure function — read-only. Produces a per-current-segment list with
text-diff tags, speaker-change flag, and merge/split origin metadata.
"""
import difflib
import json
from pathlib import Path


def _backup_path_for(json_path: Path) -> Path:
    return json_path.with_name(json_path.stem + ".original.json")


def _load(json_path: str) -> dict:
    return json.loads(Path(json_path).read_text(encoding="utf-8"))


def compute_segment_diff(json_path: str) -> list[dict]:
    """Return per-current-segment diff entries.

    If .original.json doesn't exist, returns []. Otherwise each entry has:
      - current_index: int
      - original_indices: list[int] — derived from _split_from / _merged_from
            or [current_index] when no metadata is present
      - text_changed: bool
      - text_diff: list[tuple(tag, original_word, current_word)]  # via SequenceMatcher
      - speaker_changed: bool
      - original_speaker: str
      - current_speaker: str
      - merge_or_split: "merged" | "split" | None
    """
    cur_path = Path(json_path)
    orig_path = _backup_path_for(cur_path)
    if not orig_path.exists():
        return []
    current = _load(json_path)
    original = _load(str(orig_path))
    cur_segs = current.get("segments", [])
    orig_segs = original.get("segments", [])

    out: list[dict] = []
    for i, seg in enumerate(cur_segs):
        if "_merged_from" in seg:
            orig_indices = list(seg["_merged_from"])
            merge_or_split = "merged"
        elif "_split_from" in seg:
            orig_indices = [int(seg["_split_from"])]
            merge_or_split = "split"
        else:
            orig_indices = [i] if i < len(orig_segs) else []
            merge_or_split = None

        # Concat original text(s) for comparison
        original_text = " ".join(
            orig_segs[oi]["text"] for oi in orig_indices if 0 <= oi < len(orig_segs)
        ).strip()
        current_text = seg.get("text", "").strip()
        text_changed = original_text != current_text
        # Word-level diff via SequenceMatcher
        orig_words = original_text.split()
        cur_words = current_text.split()
        matcher = difflib.SequenceMatcher(a=orig_words, b=cur_words)
        text_diff: list[tuple] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            text_diff.append((tag, " ".join(orig_words[i1:i2]), " ".join(cur_words[j1:j2])))

        # Speaker compare
        original_speaker = (
            orig_segs[orig_indices[0]].get("speaker", "")
            if orig_indices and 0 <= orig_indices[0] < len(orig_segs)
            else ""
        )
        current_speaker = seg.get("speaker", "")
        speaker_changed = original_speaker != current_speaker

        out.append({
            "current_index": i,
            "original_indices": orig_indices,
            "text_changed": text_changed,
            "text_diff": text_diff,
            "speaker_changed": speaker_changed,
            "original_speaker": original_speaker,
            "current_speaker": current_speaker,
            "merge_or_split": merge_or_split,
        })
    return out
