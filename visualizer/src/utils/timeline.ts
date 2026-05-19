import {useEffect, useMemo, useState} from 'react';
import {cancelRender, continueRender, delayRender, staticFile} from 'remotion';

/* ────────────────────────────────────────────────────────────────────────
   WhisperX standard schema (the `--diarize` JSON output).
   We type it loosely — WhisperX adds optional fields across versions
   (language, alignment confidences, etc.) and we don't need them all.
   ──────────────────────────────────────────────────────────────────────── */

export type WhisperXWord = {
  word: string;
  start?: number; // seconds; rare but possible to be missing on filler tokens
  end?: number;
  score?: number; // 0..1, alignment confidence
  speaker?: string; // 'SPEAKER_00' etc — sometimes only on segment level
};

export type WhisperXSegment = {
  start: number;
  end: number;
  text: string;
  speaker?: string;
  words?: WhisperXWord[];
};

export type WhisperXFile = {
  segments: WhisperXSegment[];
  word_segments?: WhisperXWord[]; // top-level mirror in newer versions
  language?: string;
};

/* ────────────────────────────────────────────────────────────────────────
   Public timeline shape — what every component reads from.
   Speakers normalised to a 0/1 index for two-lane visualisers; original
   tag preserved for caption chips and confidence labels.
   ──────────────────────────────────────────────────────────────────────── */

export type Turn = {
  startMs: number;
  endMs: number;
  speaker: string; // 'SPEAKER_00'
  speakerIdx: 0 | 1; // ≥2 collapses to 1 — second lane
  text: string;
  words: TimedWord[];
  /** Mean alignment confidence over words; falls back to 1 if absent */
  score: number;
};

export type TimedWord = {
  word: string;
  startMs: number;
  endMs: number;
  speaker: string;
  speakerIdx: 0 | 1;
  score: number;
};

export type ChapterMarker = {
  index: number;
  startMs: number;
  /** End is the next chapter's start, or +Infinity for the last. */
  endMs: number;
  title: string;
};

export type Timeline = {
  ready: boolean;
  turns: Turn[];
  words: TimedWord[];
  chapters: ChapterMarker[];
};

/* ────────────────────────────────────────────────────────────────────────
   Loader
   ──────────────────────────────────────────────────────────────────────── */

const speakerToIdx = (speaker: string | undefined): 0 | 1 => {
  if (!speaker) return 0;
  const m = speaker.match(/(\d+)/);
  if (!m) return 0;
  const n = parseInt(m[1], 10);
  return n === 0 ? 0 : 1; // ≥1 collapses to lane 1
};

const normaliseFile = (raw: WhisperXFile): {turns: Turn[]; words: TimedWord[]} => {
  const turns: Turn[] = [];
  const words: TimedWord[] = [];

  for (const seg of raw.segments ?? []) {
    const speaker = seg.speaker ?? seg.words?.find((w) => w.speaker)?.speaker ?? 'SPEAKER_00';
    const speakerIdx = speakerToIdx(speaker);
    const segWords: TimedWord[] = (seg.words ?? [])
      .filter((w) => w.start != null && w.end != null && w.word)
      .map((w) => {
        const wSpk = w.speaker ?? speaker;
        return {
          word: w.word,
          startMs: (w.start as number) * 1000,
          endMs: (w.end as number) * 1000,
          speaker: wSpk,
          speakerIdx: speakerToIdx(wSpk),
          score: typeof w.score === 'number' ? w.score : 1,
        };
      });

    const score =
      segWords.length > 0
        ? segWords.reduce((a, w) => a + w.score, 0) / segWords.length
        : 1;

    turns.push({
      startMs: seg.start * 1000,
      endMs: seg.end * 1000,
      speaker,
      speakerIdx,
      text: seg.text.trim(),
      words: segWords,
      score,
    });
    words.push(...segWords);
  }

  // If the file has a top-level word_segments[] we use it as the source of truth
  // for word timing (it sometimes contains words that fall between segments).
  if (raw.word_segments && raw.word_segments.length > 0 && words.length === 0) {
    for (const w of raw.word_segments) {
      if (w.start == null || w.end == null) continue;
      const speaker = w.speaker ?? 'SPEAKER_00';
      words.push({
        word: w.word,
        startMs: w.start * 1000,
        endMs: w.end * 1000,
        speaker,
        speakerIdx: speakerToIdx(speaker),
        score: typeof w.score === 'number' ? w.score : 1,
      });
    }
  }

  // Stable sort, just in case input wasn't.
  turns.sort((a, b) => a.startMs - b.startMs);
  words.sort((a, b) => a.startMs - b.startMs);

  // Chapter detection — segments whose text begins with `[CHAPTER]`
  // (or `[CHAPTER: Foo]`) become section markers. The chapter title
  // is the rest of that segment (or the bracketed name).
  const chapters: ChapterMarker[] = [];
  raw.segments?.forEach((seg) => {
    const m = seg.text.match(/^\s*\[CHAPTER(?:\s*[:·\-]\s*([^\]]+))?\]\s*(.*)$/i);
    if (!m) return;
    const title = (m[1] || m[2] || 'Chapter').trim();
    chapters.push({
      index: chapters.length,
      startMs: seg.start * 1000,
      endMs: Number.POSITIVE_INFINITY,
      title,
    });
  });
  for (let i = 0; i < chapters.length - 1; i++) {
    chapters[i].endMs = chapters[i + 1].startMs;
  }

  return {turns, words, chapters};
};

/**
 * Load WhisperX JSON once. delayRender bridges the fetch into the
 * Remotion render so the renderer waits before grabbing frame 0.
 *
 * Default path: `staticFile('podcast.whisperx.json')`.
 */
export const useTimeline = (
  src: string = staticFile('podcast.whisperx.json'),
): Timeline => {
  const [data, setData] = useState<{
    turns: Turn[];
    words: TimedWord[];
    chapters: ChapterMarker[];
  }>({turns: [], words: [], chapters: []});
  const [ready, setReady] = useState(false);
  const [handle] = useState(() => delayRender('Loading WhisperX timeline'));

  useEffect(() => {
    let cancelled = false;
    fetch(src)
      .then((r) => {
        if (!r.ok) throw new Error(`Timeline fetch failed: ${r.status}`);
        return r.json();
      })
      .then((json: WhisperXFile) => {
        if (cancelled) return;
        setData(normaliseFile(json));
        setReady(true);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
    return () => {
      cancelled = true;
    };
  }, [src, handle]);

  return useMemo(
    () => ({
      ready,
      turns: data.turns,
      words: data.words,
      chapters: (data as any).chapters ?? [],
    }),
    [ready, data],
  );
};

/**
 * Resolve the active chapter for a given frame, plus the signed delta
 * from its boundary (positive = into the chapter, negative = before it).
 * SectionCard uses this for entry timing.
 */
export const useActiveChapter = (
  timeline: Timeline,
  frame: number,
  fps: number,
): {chapter: ChapterMarker | null; framesFromBoundary: number} => {
  return useMemo(() => {
    const ms = (frame / fps) * 1000;
    const chapter =
      timeline.chapters.find((c) => ms >= c.startMs && ms < c.endMs) ?? null;
    const framesFromBoundary = chapter
      ? ((ms - chapter.startMs) / 1000) * fps
      : 0;
    return {chapter, framesFromBoundary};
  }, [timeline.chapters, frame, fps]);
};

/* ────────────────────────────────────────────────────────────────────────
   Selectors — frame-keyed lookups built on top of a Timeline.

   All return null when nothing is active. Selectors avoid binary search
   for now (linear scan is fine up to ~5k segments — well under a typical
   60-min podcast). We can swap to a sorted-index later if needed.
   ──────────────────────────────────────────────────────────────────────── */

export const useActiveTurn = (
  timeline: Timeline,
  frame: number,
  fps: number,
): Turn | null => {
  return useMemo(() => {
    const ms = (frame / fps) * 1000;
    return (
      timeline.turns.find((t) => ms >= t.startMs && ms < t.endMs) ?? null
    );
  }, [timeline.turns, frame, fps]);
};

export const useActiveWord = (
  timeline: Timeline,
  frame: number,
  fps: number,
): TimedWord | null => {
  return useMemo(() => {
    const ms = (frame / fps) * 1000;
    return (
      timeline.words.find((w) => ms >= w.startMs && ms < w.endMs) ?? null
    );
  }, [timeline.words, frame, fps]);
};

/**
 * Resolve the "effective" speaker, taking PRE-ROLL into account.
 *
 * Visual cues should fire *before* the speaker actually starts so the
 * lane swap doesn't feel like a delay relative to the audio. We look
 * `lookaheadFrames` ahead: if a turn starts in that window, that turn's
 * speaker becomes effective NOW.
 *
 * Returns the active turn, the upcoming turn (if within lookahead),
 * and the effective speaker index — what every visualiser should bind
 * its lane state to.
 */
export type EffectiveSpeaker = {
  current: Turn | null;
  upcoming: Turn | null;
  /** Frames until upcoming turn starts; 0 if not in lookahead. */
  framesUntilUpcoming: number;
  /** 0 | 1 if any speaker is effective, otherwise null (silence). */
  effectiveIdx: 0 | 1 | null;
};

export const useEffectiveSpeaker = (
  timeline: Timeline,
  frame: number,
  fps: number,
  lookaheadFrames: number = 4,
): EffectiveSpeaker => {
  return useMemo(() => {
    const nowMs = (frame / fps) * 1000;
    const horizonMs = nowMs + (lookaheadFrames / fps) * 1000;

    const current =
      timeline.turns.find((t) => nowMs >= t.startMs && nowMs < t.endMs) ?? null;

    // First turn whose start is in (now, horizon].
    const upcoming =
      timeline.turns.find(
        (t) => t.startMs > nowMs && t.startMs <= horizonMs,
      ) ?? null;

    let effectiveIdx: 0 | 1 | null = null;
    if (current) effectiveIdx = current.speakerIdx;
    else if (upcoming) effectiveIdx = upcoming.speakerIdx;

    const framesUntilUpcoming = upcoming
      ? Math.max(0, ((upcoming.startMs - nowMs) / 1000) * fps)
      : 0;

    return {current, upcoming, framesUntilUpcoming, effectiveIdx};
  }, [timeline.turns, frame, fps, lookaheadFrames]);
};

/**
 * Look up the next turn after `frame`, regardless of horizon.
 * Used by the caption-preview ghost line.
 */
export const useNextTurn = (
  timeline: Timeline,
  frame: number,
  fps: number,
): Turn | null => {
  return useMemo(() => {
    const ms = (frame / fps) * 1000;
    return timeline.turns.find((t) => t.startMs > ms) ?? null;
  }, [timeline.turns, frame, fps]);
};
