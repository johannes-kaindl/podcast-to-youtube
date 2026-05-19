/**
 * Map SPEAKER_xx tags from the SRT to fixed Signal hues.
 *
 * Per KSP: each voice has a stable identity. We don't randomise.
 * Up to four speakers covered out of the box; extend as needed.
 */
export const SIGNAL_BY_SPEAKER: Record<string, string> = {
  SPEAKER_00: 'var(--signal-phosphor)',
  SPEAKER_01: 'var(--signal-spectre)',
  SPEAKER_02: 'var(--signal-ember)',
  SPEAKER_03: 'var(--signal-circuit)',
};
