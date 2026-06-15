import { describe, expect, it } from 'vitest';
import { SIGNAL_BY_SPEAKER } from './speakers';

describe('SIGNAL_BY_SPEAKER', () => {
  it('maps the first four speaker tags to distinct Signal hues', () => {
    const keys = ['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02', 'SPEAKER_03'];
    for (const k of keys) {
      expect(SIGNAL_BY_SPEAKER[k]).toMatch(/^var\(--signal-/);
    }
    const hues = keys.map((k) => SIGNAL_BY_SPEAKER[k]);
    expect(new Set(hues).size).toBe(4); // all distinct
  });
});
