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

/**
 * The same family in its loud expression, for whatever is "now": the word being
 * spoken, the voice speaking. Everything at rest keeps SIGNAL_BY_SPEAKER.
 * birds of yore, decided 2026-10-14 (_design, identities/birds-of-yore/targets/remotion.md).
 */
export const SIGNAL_LAUT_BY_SPEAKER: Record<string, string> = Object.fromEntries(
  Object.entries(SIGNAL_BY_SPEAKER).map(([k, v]) => [k, `${v.slice(0, -1)}-laut)`]),
);
