import React from 'react';
import {interpolate, spring} from 'remotion';
import type {ChapterMarker} from '../utils/timeline';

type Props = {
  chapter: ChapterMarker | null;
  /** Frames until the chapter starts (positive) or since it ended (negative). */
  framesFromBoundary: number;
  frame: number;
  fps: number;
  reducedMotion: boolean;
};

/**
 * Section / Chapter title-card overlay. Drives off the Mentor (Sensei /
 * Ember) aspect — overrides the host viz aspect for the duration of
 * the card. Animation:
 *
 *  • A spring scales a horizontal rule from 0 → 1 across 18 frames.
 *  • The kanji + roman title fade up 12 px on entry.
 *  • Holds for the full chapter duration if the chapter is short
 *    (< 6 s); for longer chapters the card auto-dismisses after 90
 *    frames so it doesn't block the visualiser.
 */
export const SectionCard: React.FC<Props> = ({
  chapter,
  framesFromBoundary,
  frame,
  fps,
  reducedMotion,
}) => {
  if (!chapter) return null;

  const chapterFrameStart = (chapter.startMs / 1000) * fps;
  const localFrame = frame - chapterFrameStart;

  // Visible during the first ~90 frames of the chapter, fading out
  // smoothly between frame 78 and 90.
  if (localFrame < 0 || localFrame > 90) return null;

  const enterProgress = reducedMotion
    ? Math.min(1, Math.max(0, localFrame / 12))
    : spring({
        frame: localFrame,
        fps,
        config: {damping: 22, stiffness: 140, mass: 0.7},
        durationInFrames: 24,
      });

  const fadeOut = interpolate(localFrame, [78, 90], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  const opacity = Math.min(enterProgress, fadeOut);
  const lift = (1 - enterProgress) * 12;

  return (
    <div
      data-aspect="sensei"
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        opacity,
        background: `radial-gradient(ellipse at center,
          color-mix(in oklab, var(--signal-ember) 14%, transparent) 0%,
          transparent 60%)`,
      }}
    >
      <div
        className="ksp-mono-caps"
        style={{
          fontSize: 13,
          letterSpacing: '0.24em',
          color: 'var(--signal-ember)',
          marginBottom: 16,
          transform: `translateY(${lift}px)`,
        }}
      >
        CHAPTER · 章 · {String(chapter.index + 1).padStart(2, '0')}
      </div>
      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: 96,
          lineHeight: 1.05,
          letterSpacing: '-0.02em',
          color: 'var(--fg-primary)',
          textAlign: 'center',
          maxWidth: 1400,
          transform: `translateY(${lift}px)`,
        }}
      >
        {chapter.title}
      </div>
      {/* Spring-scaled rule beneath title */}
      <div
        style={{
          marginTop: 32,
          width: `${Math.round(enterProgress * 320)}px`,
          height: 2,
          background: 'var(--signal-ember)',
          boxShadow: '0 0 18px var(--signal-ember)',
        }}
      />
    </div>
  );
};
