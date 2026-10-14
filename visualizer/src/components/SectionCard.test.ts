import { describe, expect, it } from 'vitest';
import type { ChapterMarker } from '../utils/timeline';
import { SECTION_CARD_FRAMES, sectionCardVisibility } from './SectionCard';

const FPS = 30;
// Chapter starts at 13.4 s → frame 402.
const chapter: ChapterMarker = { index: 0, startMs: 13_400, endMs: 60_000, title: 'Kapitel' };
const START = 402;

describe('sectionCardVisibility', () => {
  it('is hidden without a chapter', () => {
    expect(sectionCardVisibility(null, START + 20, FPS, false).opacity).toBe(0);
  });

  it('is hidden before the chapter starts and after the card time', () => {
    expect(sectionCardVisibility(chapter, START - 1, FPS, false).opacity).toBe(0);
    expect(
      sectionCardVisibility(chapter, START + SECTION_CARD_FRAMES + 1, FPS, false).opacity,
    ).toBe(0);
  });

  it('is fully up in the hold phase, where the caption is ducked hardest', () => {
    const { opacity } = sectionCardVisibility(chapter, START + 40, FPS, false);
    expect(opacity).toBeGreaterThan(0.95);
  });

  it('fades out towards the end, so the caption comes back with the same curve', () => {
    const late = sectionCardVisibility(chapter, START + 84, FPS, false).opacity;
    expect(late).toBeGreaterThan(0);
    expect(late).toBeLessThan(1);
    expect(sectionCardVisibility(chapter, START + SECTION_CARD_FRAMES, FPS, false).opacity).toBe(0);
  });

  it('enters linearly over 12 frames with reduced motion', () => {
    expect(sectionCardVisibility(chapter, START + 6, FPS, true).opacity).toBeCloseTo(0.5);
  });
});
