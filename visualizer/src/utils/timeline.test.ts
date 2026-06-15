import { describe, expect, it } from 'vitest';
import { normaliseFile, speakerToIdx } from './timeline';

describe('speakerToIdx', () => {
  it('maps SPEAKER_00 to lane 0 and any other speaker to lane 1', () => {
    expect(speakerToIdx('SPEAKER_00')).toBe(0);
    expect(speakerToIdx('SPEAKER_01')).toBe(1);
    expect(speakerToIdx('SPEAKER_02')).toBe(1);
    expect(speakerToIdx(undefined)).toBe(0);
    expect(speakerToIdx('Anna')).toBe(0); // no digit → lane 0
  });
});

describe('normaliseFile', () => {
  it('normalises segments into turns + flattened words with ms timings', () => {
    const { turns, words } = normaliseFile({
      segments: [
        {
          start: 0,
          end: 2,
          text: '  Hallo Welt  ',
          speaker: 'SPEAKER_00',
          words: [
            { word: 'Hallo', start: 0, end: 1, score: 0.9 },
            { word: 'Welt', start: 1, end: 2, score: 0.7 },
          ],
        },
        { start: 2, end: 4, text: 'Antwort', speaker: 'SPEAKER_01' },
      ],
    });

    expect(turns).toHaveLength(2);
    expect(turns[0].text).toBe('Hallo Welt'); // trimmed
    expect(turns[0].startMs).toBe(0);
    expect(turns[0].endMs).toBe(2000); // seconds → ms
    expect(turns[0].speakerIdx).toBe(0);
    expect(turns[0].score).toBeCloseTo(0.8); // mean of word scores
    expect(turns[1].speakerIdx).toBe(1);

    expect(words).toHaveLength(2);
    expect(words[0]).toMatchObject({ word: 'Hallo', startMs: 0, endMs: 1000 });
  });

  it('detects [CHAPTER] segments as chapter markers with boundary end-times', () => {
    const { chapters } = normaliseFile({
      segments: [
        { start: 0, end: 1, text: '[CHAPTER: Intro] welcome' },
        { start: 10, end: 11, text: 'normal line' },
        { start: 20, end: 21, text: '[CHAPTER] Zweites Kapitel' },
      ],
    });

    expect(chapters).toHaveLength(2);
    expect(chapters[0].title).toBe('Intro');
    expect(chapters[0].startMs).toBe(0);
    expect(chapters[0].endMs).toBe(20000); // runs until the next chapter starts
    expect(chapters[1].title).toBe('Zweites Kapitel');
    expect(chapters[1].endMs).toBe(Number.POSITIVE_INFINITY);
  });
});
