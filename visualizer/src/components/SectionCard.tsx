import type React from 'react';
import { interpolate, spring } from 'remotion';
import type { ChapterMarker } from '../utils/timeline';

type Props = {
  chapter: ChapterMarker | null;
  /** Frames until the chapter starts (positive) or since it ended (negative). */
  framesFromBoundary: number;
  frame: number;
  fps: number;
  reducedMotion: boolean;
};

/** Frames the card stays up after the chapter starts (fade-out ends here). */
export const SECTION_CARD_FRAMES = 90;
const FADE_OUT_FROM = 78;

/**
 * Visibility of the card at `frame`: `opacity` (0 when hidden) and the
 * entry `enterProgress` (0 → 1). Pure, so the composition can duck the
 * running caption with the same curve the card fades with.
 */
export const sectionCardVisibility = (
  chapter: ChapterMarker | null,
  frame: number,
  fps: number,
  reducedMotion: boolean,
): { opacity: number; enterProgress: number } => {
  if (!chapter) return { opacity: 0, enterProgress: 0 };

  const chapterFrameStart = (chapter.startMs / 1000) * fps;
  const localFrame = frame - chapterFrameStart;

  // Visible during the first SECTION_CARD_FRAMES of the chapter, fading
  // out smoothly over the last 12 of them.
  if (localFrame < 0 || localFrame > SECTION_CARD_FRAMES) return { opacity: 0, enterProgress: 0 };

  const enterProgress = reducedMotion
    ? Math.min(1, Math.max(0, localFrame / 12))
    : spring({
        frame: localFrame,
        fps,
        config: { damping: 22, stiffness: 140, mass: 0.7 },
        durationInFrames: 24,
      });

  const fadeOut = interpolate(localFrame, [FADE_OUT_FROM, SECTION_CARD_FRAMES], [1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return { opacity: Math.min(enterProgress, fadeOut), enterProgress };
};

/**
 * Section / Chapter title-card overlay in the stage accent (birds of yore,
 * Subtheme Crimson; until 2026-10-14 the KSP aspect Sensei/Ember). Animation:
 *
 *  • A spring scales a horizontal rule from 0 → 1 across 18 frames.
 *  • The kanji + roman title fade up 12 px on entry.
 *  • Dismisses after SECTION_CARD_FRAMES (3 s at 30 fps), whatever the
 *    chapter length, so it doesn't block the visualiser.
 */
export const SectionCard: React.FC<Props> = ({ chapter, frame, fps, reducedMotion }) => {
  const { opacity, enterProgress } = sectionCardVisibility(chapter, frame, fps, reducedMotion);
  if (!chapter || opacity <= 0) return null;

  const lift = (1 - enterProgress) * 12;

  return (
    <div
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
          color-mix(in oklab, var(--accent) 14%, transparent) 0%,
          transparent 60%)`,
      }}
    >
      <div
        className="ksp-mono-caps"
        style={{
          fontSize: 13,
          letterSpacing: '0.24em',
          color: 'var(--accent)',
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
          background: 'var(--accent)',
          boxShadow: '0 0 18px var(--accent)',
        }}
      />
    </div>
  );
};
