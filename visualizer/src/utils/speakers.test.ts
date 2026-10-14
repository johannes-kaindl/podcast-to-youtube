import { describe, expect, it } from 'vitest';
import { SIGNAL_BY_SPEAKER, SIGNAL_LAUT_BY_SPEAKER } from './speakers';

const KEYS = ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02', 'SPEAKER_03'];

describe('SIGNAL_BY_SPEAKER', () => {
  it('maps the first four speaker tags to distinct Signal hues', () => {
    for (const k of KEYS) {
      expect(SIGNAL_BY_SPEAKER[k]).toMatch(/^var\(--signal-[a-z]+\)$/);
    }
    const hues = KEYS.map((k) => SIGNAL_BY_SPEAKER[k]);
    expect(new Set(hues).size).toBe(4); // all distinct
  });
});

describe('SIGNAL_LAUT_BY_SPEAKER', () => {
  it('gives each speaker the loud expression of the same family', () => {
    for (const k of KEYS) {
      const quiet = SIGNAL_BY_SPEAKER[k].slice(0, -1);
      expect(SIGNAL_LAUT_BY_SPEAKER[k]).toBe(`${quiet}-laut)`);
    }
  });
});
