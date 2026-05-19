import React from 'react';
import {AbsoluteFill} from 'remotion';

/**
 * The chamber. Flat near-black ground, a 1px grid overlay at very low
 * alpha, four corner tickmarks. Per KSP: patterns are *earned* — no
 * gradients as wallpaper, no glassmorphism. The grid sits behind
 * everything; cards on top must remain flat.
 */
export const ChamberBackground: React.FC = () => {
  return (
    <AbsoluteFill style={{background: 'var(--void-050)', overflow: 'hidden'}}>
      {/* 1px grid — earned only on the vault surface */}
      <AbsoluteFill
        style={{
          backgroundImage: `
            linear-gradient(to right, var(--void-300) 1px, transparent 1px),
            linear-gradient(to bottom, var(--void-300) 1px, transparent 1px)
          `,
          backgroundSize: '64px 64px',
          opacity: 0.18,
        }}
      />

      {/* Subtle radial darkening from edges — keeps focus center stage */}
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse at center, transparent 0%, var(--void-050) 78%)',
        }}
      />

      {/* SVG noise grain at ~3% opacity */}
      <AbsoluteFill style={{opacity: 0.04, mixBlendMode: 'overlay'}}>
        <svg width="100%" height="100%" preserveAspectRatio="none">
          <filter id="ksp-noise">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.9"
              numOctaves="2"
              stitchTiles="stitch"
            />
          </filter>
          <rect width="100%" height="100%" filter="url(#ksp-noise)" />
        </svg>
      </AbsoluteFill>

      {/* Corner tickmarks — protocol witnesses */}
      <CornerTicks />
    </AbsoluteFill>
  );
};

const CornerTicks: React.FC = () => {
  const T = 32; // arm length
  const O = 64; // offset from edge
  const stroke = 'var(--void-500)';
  const sw = 1.5;
  return (
    <svg
      width="100%"
      height="100%"
      viewBox="0 0 1920 1080"
      preserveAspectRatio="none"
      style={{position: 'absolute', inset: 0}}
    >
      {/* TL */}
      <path d={`M${O} ${O + T} V${O} H${O + T}`} stroke={stroke} strokeWidth={sw} fill="none" />
      {/* TR */}
      <path d={`M${1920 - O - T} ${O} H${1920 - O} V${O + T}`} stroke={stroke} strokeWidth={sw} fill="none" />
      {/* BL */}
      <path d={`M${O} ${1080 - O - T} V${1080 - O} H${O + T}`} stroke={stroke} strokeWidth={sw} fill="none" />
      {/* BR */}
      <path d={`M${1920 - O - T} ${1080 - O} H${1920 - O} V${1080 - O - T}`} stroke={stroke} strokeWidth={sw} fill="none" />
    </svg>
  );
};
