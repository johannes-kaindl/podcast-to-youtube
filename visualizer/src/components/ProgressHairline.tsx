import React from 'react';
import {interpolate} from 'remotion';

type Props = {
  frame: number;
  durationInFrames: number;
  /** 0..1 — current broadband audio level. Modulates hairline brightness. */
  level: number;
  reducedMotion: boolean;
};

/**
 * Episode-progress hairline at the very top edge of the chamber.
 *
 *  • 1 px line, full chamber width, in `--accent`.
 *  • Width scales linearly with `frame / durationInFrames`.
 *  • Glow + opacity are gently audio-modulated so it reads as alive
 *    without jittering — clamped to [0.55, 1.0] so it never disappears.
 *  • Tiny tickmark sits at 25/50/75 % to give visual cadence over a
 *    long render. Major tick (50 %) is brighter.
 */
export const ProgressHairline: React.FC<Props> = ({
  frame,
  durationInFrames,
  level,
  reducedMotion,
}) => {
  const ratio = Math.max(0, Math.min(1, frame / Math.max(1, durationInFrames)));
  const widthPct = ratio * 100;

  const brightness = reducedMotion
    ? 0.85
    : interpolate(level, [0, 0.6], [0.55, 1], {
        extrapolateLeft: 'clamp',
        extrapolateRight: 'clamp',
      });

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        height: 8,
        pointerEvents: 'none',
      }}
    >
      {/* trough */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 1,
          background: 'var(--void-300)',
          opacity: 0.6,
        }}
      />
      {/* fill */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          height: 1,
          width: `${widthPct}%`,
          background: 'var(--accent)',
          opacity: brightness,
          boxShadow: `0 0 12px var(--accent)`,
        }}
      />
      {/* leading dot */}
      {ratio > 0 && ratio < 1 ? (
        <div
          style={{
            position: 'absolute',
            top: -2,
            left: `calc(${widthPct}% - 2px)`,
            width: 5,
            height: 5,
            borderRadius: 999,
            background: 'var(--accent)',
            boxShadow: `0 0 10px var(--accent)`,
            opacity: brightness,
          }}
        />
      ) : null}
      {/* quartile ticks */}
      {[0.25, 0.5, 0.75].map((q) => (
        <div
          key={q}
          style={{
            position: 'absolute',
            top: 0,
            left: `${q * 100}%`,
            width: 1,
            height: q === 0.5 ? 6 : 4,
            background: 'var(--void-500)',
            opacity: q === 0.5 ? 0.85 : 0.55,
          }}
        />
      ))}
    </div>
  );
};
