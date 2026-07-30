"""Tests for transcript_align — propagating segment.text edits into segment.words.

The Remotion renderer drives the per-word karaoke highlight from segment.words
and only falls back to segment.text when the word list is empty
(visualizer/src/DialogueComposition.tsx:644). A text edit that never reaches
words is therefore invisible in the rendered MP4.
"""

from itertools import pairwise


def test_replacing_one_word_keeps_the_surrounding_timings():
    from transcript_align import propagate_text_to_words

    segment = {
        "start": 0.0,
        "end": 2.0,
        "text": "wir deployen auf Kubernetes heute",
        "words": [
            {"word": "wir", "start": 0.0, "end": 0.3, "score": 0.9},
            {"word": "deployen", "start": 0.3, "end": 0.7, "score": 0.9},
            {"word": "auf", "start": 0.7, "end": 0.9, "score": 0.9},
            {"word": "Kubernetis", "start": 0.9, "end": 1.5, "score": 0.4},
            {"word": "heute", "start": 1.5, "end": 2.0, "score": 0.9},
        ],
    }

    propagate_text_to_words(segment)

    words = segment["words"]
    assert [w["word"] for w in words] == [
        "wir",
        "deployen",
        "auf",
        "Kubernetes",
        "heute",
    ]
    # The replaced word keeps the slot it was spoken in.
    assert words[3]["start"] == 0.9
    assert words[3]["end"] == 1.5
    # Untouched neighbours keep their timings byte-for-byte.
    assert words[0]["start"] == 0.0
    assert words[4]["end"] == 2.0


def test_deleted_word_disappears_and_leaves_the_others_untouched():
    from transcript_align import propagate_text_to_words

    segment = {
        "start": 0.0,
        "end": 1.0,
        "text": "wir deployen heute",
        "words": [
            {"word": "wir", "start": 0.0, "end": 0.3, "score": 0.9},
            {"word": "deployen", "start": 0.3, "end": 0.7, "score": 0.9},
            {"word": "jetzt", "start": 0.7, "end": 0.8, "score": 0.9},
            {"word": "heute", "start": 0.8, "end": 1.0, "score": 0.9},
        ],
    }

    propagate_text_to_words(segment)

    assert [w["word"] for w in segment["words"]] == ["wir", "deployen", "heute"]
    assert segment["words"][2]["start"] == 0.8


def test_segment_without_words_stays_empty():
    """WhisperX leaves some segments wordless; the renderer falls back to
    segment.text there. Inventing words would fake timings that were never
    measured — and the fake would then drive the karaoke highlight."""
    from transcript_align import propagate_text_to_words

    segment = {"start": 2.5, "end": 4.0, "text": "Sounds great to me.", "words": []}

    assert propagate_text_to_words(segment) == 0
    assert segment["words"] == []


def test_inserted_word_gets_a_highlightable_slot_between_gapless_neighbours():
    from transcript_align import propagate_text_to_words

    segment = {
        "start": 0.0,
        "end": 1.0,
        "text": "wir deployen das heute",
        "words": [
            {"word": "wir", "start": 0.0, "end": 0.3, "score": 0.9},
            {"word": "deployen", "start": 0.3, "end": 0.7, "score": 0.9},
            {"word": "heute", "start": 0.7, "end": 1.0, "score": 0.9},
        ],
    }

    propagate_text_to_words(segment)

    words = segment["words"]
    assert [w["word"] for w in words] == ["wir", "deployen", "das", "heute"]
    # Every word needs a non-empty window — the renderer highlights on
    # `nowMs >= startMs && nowMs < endMs`, so start == end never lights up.
    for w in words:
        assert w["end"] > w["start"], f"{w['word']} has an empty window"
    # Monotonic and inside the segment.
    assert all(a["end"] <= b["start"] for a, b in pairwise(words))
    assert words[0]["start"] >= segment["start"]
    assert words[-1]["end"] <= segment["end"]
