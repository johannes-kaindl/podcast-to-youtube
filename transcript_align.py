"""Propagate segment.text edits into segment.words.

The Remotion renderer drives the per-word karaoke highlight from segment.words
and only falls back to segment.text when the word list is empty
(visualizer/src/DialogueComposition.tsx:644). A text edit that never reaches
words is therefore invisible in the rendered MP4.

Pure Python, imports nothing from the other transcript_* modules (they import
regenerate_srt_txt from transcript_editor, so a back-import would be circular).
"""

from difflib import SequenceMatcher
from typing import Any


def _distribute(
    tokens: list[str],
    t0: float,
    t1: float,
    template: dict[str, Any],
    anchor_first: bool = False,
) -> list[dict[str, Any]]:
    """Spread tokens across [t0, t1], each token's share by character length.

    template supplies the non-timing fields (score, speaker, …). With
    anchor_first the leading token is a re-timed but textually unchanged word,
    so it does not get the _edited flag.
    """
    total = sum(len(t) for t in tokens) or 1
    span = max(t1 - t0, 0.0)
    out: list[dict[str, Any]] = []
    cursor = t0
    for idx, token in enumerate(tokens):
        word = {k: v for k, v in template.items() if k not in ("word", "start", "end", "_edited")}
        word["word"] = token
        word["start"] = round(cursor, 3)
        cursor += span * (len(token) / total)
        word["end"] = round(cursor, 3)
        if not (anchor_first and idx == 0):
            word["_edited"] = True
        out.append(word)
    if out:
        out[-1]["end"] = round(t1, 3)
    return out


def propagate_text_to_words(segment: dict[str, Any]) -> int:
    """Rewrite segment["words"] so it spells out segment["text"].

    Unchanged runs keep their timings byte-for-byte. A changed run is
    redistributed across the time span its predecessors occupied; an insertion
    borrows the span from its left neighbour (or, at the segment head, from the
    room before the next word).

    Segments without words are left alone — the renderer falls back to
    segment.text there, so there is nothing to fix and nothing to invent.

    Returns the number of word entries whose text changed.
    """
    words: list[dict[str, Any]] = segment.get("words", [])
    if not words:
        return 0
    tokens: list[str] = segment["text"].split()
    old_tokens = [w.get("word", "") for w in words]
    if old_tokens == tokens:
        return 0

    new_words: list[dict[str, Any]] = []
    changed = 0
    matcher = SequenceMatcher(a=old_tokens, b=tokens, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            new_words.extend(words[i1:i2])
            continue

        block_tokens = tokens[j1:j2]
        old_block = words[i1:i2]
        if old_block:
            template = old_block[0]
            t0, t1 = old_block[0]["start"], old_block[-1]["end"]
            anchor_first = False
        elif new_words:
            # Pure insertion: pull the left neighbour back in and re-time both.
            anchor = new_words.pop()
            block_tokens = [anchor["word"], *block_tokens]
            template = anchor
            t0 = anchor["start"]
            t1 = words[i2]["start"] if i2 < len(words) else segment["end"]
            anchor_first = True
        else:
            # Insertion at the very head of the segment.
            template = words[0]
            t0 = segment["start"]
            t1 = words[i2]["start"] if i2 < len(words) else segment["end"]
            anchor_first = False

        new_words.extend(_distribute(block_tokens, t0, t1, template, anchor_first))
        changed += len(tokens[j1:j2])

    segment["words"] = new_words
    return changed
