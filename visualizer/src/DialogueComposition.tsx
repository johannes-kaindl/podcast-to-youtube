import React, {useLayoutEffect, useMemo, useRef} from 'react';
import {
  AbsoluteFill,
  Audio,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {useWindowedAudioData, visualizeAudio, visualizeAudioWaveform} from '@remotion/media-utils';

import {ChamberBackground} from './components/ChamberBackground';
import {ProgressHairline} from './components/ProgressHairline';
import {SectionCard} from './components/SectionCard';
import type {Timeline, Turn} from './utils/timeline';
import {
  useTimeline,
  useEffectiveSpeaker,
  useActiveChapter,
  useNextTurn,
} from './utils/timeline';
import {SIGNAL_BY_SPEAKER} from './utils/speakers';

export type DialogueVizMode = 'dialogue' | 'monologue';

export type DialogueProps = {
  vizMode: DialogueVizMode;
  title: string;
  episode: string;
  showName: string;
};

// ── Helpers ────────────────────────────────────────────────────────────────

const fmtTc = (s: number): string => {
  const t = Math.max(0, Math.floor(s));
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`;
};

const smoothstep = (x: number): number => {
  const t = Math.max(0, Math.min(1, x));
  return t * t * (3 - 2 * t);
};

// WhisperX-Tags sind 0-indexed (SPEAKER_00, SPEAKER_01, ...). User-facing
// zählen wir ab 1 — "Speaker 01", "Speaker 02" — und vereinheitlichen das
// überall (Teleprompter, Monologue-Row, UpNext, MetaBar).
const formatSpeakerLabel = (s: string): string => {
  const m = s.match(/SPEAKER_(\d+)/);
  if (!m) return s;
  const n = parseInt(m[1], 10) + 1;
  return `Speaker ${String(n).padStart(2, '0')}`;
};
const formatSpeakerShort = (s: string): string => {
  const m = s.match(/SPEAKER_(\d+)/);
  if (!m) return s;
  const n = parseInt(m[1], 10) + 1;
  return `SPK·${String(n).padStart(2, '0')}`;
};

// ── Prompter layout ────────────────────────────────────────────────────────
// Prompter: left 120, right edge at 1920-620=1300 → width 1180
const PROMPTER_W = 1180;
const TURN_GAP = 64;
const SPEAKER_ROW_H = 48;
const CHAR_RATIO = 0.38; // EB Garamond italic: approx char-width / font-size

function lineCount(text: string, fs: number): number {
  const cpl = Math.max(1, Math.floor(PROMPTER_W / (fs * CHAR_RATIO)));
  const words = text.trim().split(/\s+/);
  let lines = 1;
  let len = 0;
  for (const w of words) {
    if (len > 0 && len + w.length + 1 > cpl) {
      lines++;
      len = w.length;
    } else {
      len += (len > 0 ? 1 : 0) + w.length;
    }
  }
  return lines;
}

function estimateTurnH(text: string, active: boolean): number {
  const fs = active ? 68 : 60;
  return SPEAKER_ROW_H + lineCount(text, fs) * fs * 1.14;
}

// ── Main composition ────────────────────────────────────────────────────────

export const DialogueVisualizer: React.FC<DialogueProps> = ({
  vizMode,
  title: _title,
  episode,
  showName,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();

  const audioSrc = staticFile('podcast.wav');
  // dataOffsetInSeconds MUSS an visualizeAudio/Waveform durchgereicht werden —
  // sonst liest die FFT ab Frame ≥ windowInSeconds*3 (bei 30s: ab 1:30) out-of-bounds
  // und gibt Nullen zurück. Buffer startet nicht bei 0s, sobald wir uns weit genug
  // im Audio bewegen.
  const {audioData, dataOffsetInSeconds} = useWindowedAudioData({src: audioSrc, frame, fps, windowInSeconds: 30});

  const audioLevel = useMemo(() => {
    if (!audioData) return 0;
    const sp = visualizeAudio({fps, frame, audioData, numberOfSamples: 16, optimizeFor: 'speed', dataOffsetInSeconds});
    return Math.min(1, Math.log10(1 + (sp.reduce((a, b) => a + b, 0) / Math.max(1, sp.length)) * 9));
  }, [audioData, frame, fps, dataOffsetInSeconds]);

  const spectrum = useMemo(() => {
    if (!audioData) return new Array(256).fill(0) as number[];
    return visualizeAudio({fps, frame, audioData, numberOfSamples: 256, optimizeFor: 'speed', dataOffsetInSeconds});
  }, [audioData, frame, fps, dataOffsetInSeconds]);

  // Echte Time-Domain-Waveform für DualWaveform — visualizeAudio gibt FFT-Bins
  // (bass links, treble rechts) zurück, was bei Sprache zu einseitigem Ausschlag
  // führt. visualizeAudioWaveform liefert dagegen die Audio-Samples des aktuellen
  // Frames als signierte Amplituden — eine realistische Welle.
  const waveform = useMemo(() => {
    if (!audioData) return new Array(140).fill(0) as number[];
    return visualizeAudioWaveform({
      fps, frame, audioData,
      numberOfSamples: 140,
      windowInSeconds: 1 / fps,
      channel: 0,
      dataOffsetInSeconds,
    });
  }, [audioData, frame, fps, dataOffsetInSeconds]);

  const timeline = useTimeline();
  const {effectiveIdx: activeSpeaker, current: currentTurn} =
    useEffectiveSpeaker(timeline, frame, fps, 4);
  const {chapter, framesFromBoundary} = useActiveChapter(timeline, frame, fps);
  const nextTurn = useNextTurn(timeline, frame, fps);

  // Silence-Detection auf DialogueVisualizer-Level — sowohl CompactRing
  // (Glow-Atmen) als auch MetaBar (LIVE-Dot-Atmen) brauchen es.
  const isSilent = !currentTurn && audioLevel < 0.08;
  const silenceBreath = isSilent
    ? 0.5 + 0.5 * Math.sin((frame * 2 * Math.PI) / 60)
    : 0;

  const elapsed = frame / fps;
  const total = durationInFrames / fps;

  // Endscreen-Safe-Phase: letzten 20s wird der Visualizer ausgefadet,
  // damit YouTube-Endscreen-Overlays (Subscribe, Next-Episode) freie Slots
  // bekommen. Hybrid-Timing:
  //   • T-20s..T-15s: Soft-Fade — Visualizer-Content fadet 1 → 0 (5s)
  //   • T-15s..T-13.5s: End-Frame fadet ein (1.5s)
  //   • T-13.5s..T-0s: End-Frame statisch sichtbar (12.5s — passt zu
  //     YouTube-Endscreen-Slot-Sichtbarkeit)
  const timeUntilEnd = total - elapsed;
  const FADE_START = 20;
  const FADE_END = 15;
  const END_FADE_IN = 1.5;
  const contentAlpha =
    timeUntilEnd >= FADE_START
      ? 1
      : timeUntilEnd >= FADE_END
      ? (timeUntilEnd - FADE_END) / (FADE_START - FADE_END)
      : 0;
  const endFrameAlpha =
    timeUntilEnd >= FADE_END
      ? 0
      : timeUntilEnd >= FADE_END - END_FADE_IN
      ? 1 - (timeUntilEnd - (FADE_END - END_FADE_IN)) / END_FADE_IN
      : 1;

  return (
    <AbsoluteFill className="ksp-stage" data-aspect="kantoku">
      <ChamberBackground />
      <ProgressHairline
        frame={frame}
        durationInFrames={durationInFrames}
        level={audioLevel}
        reducedMotion={false}
      />

      <MetaBar
        showName={showName}
        episode={episode}
        elapsed={elapsed}
        total={total}
        audioLevel={audioLevel}
        activeSpeaker={activeSpeaker}
        isSilent={isSilent}
        silenceBreath={silenceBreath}
      />

      <div style={{opacity: contentAlpha, transition: 'none'}}>
        {vizMode === 'dialogue' ? (
          <>
            <PrompterArea
              timeline={timeline}
              currentTurn={currentTurn}
              frame={frame}
              fps={fps}
            />
            <RightPanel
              spectrum={spectrum}
              waveform={waveform}
              frame={frame}
              fps={fps}
              activeSpeaker={activeSpeaker}
              currentTurn={currentTurn}
              nextTurn={nextTurn}
              elapsed={elapsed}
              silenceBreath={silenceBreath}
            />
          </>
        ) : (
          <MonologueArea
            timeline={timeline}
            spectrum={spectrum}
            waveform={waveform}
            currentTurn={currentTurn}
            activeSpeaker={activeSpeaker}
            silenceBreath={silenceBreath}
            frame={frame}
            fps={fps}
          />
        )}
      </div>

      <FooterBar vizMode={vizMode} />

      <SectionCard
        chapter={chapter}
        framesFromBoundary={framesFromBoundary}
        frame={frame}
        fps={fps}
        reducedMotion={false}
      />

      {endFrameAlpha > 0 && (
        <EndFrame
          showName={showName}
          episode={episode}
          opacity={endFrameAlpha}
        />
      )}

      <Audio src={audioSrc} />
    </AbsoluteFill>
  );
};

// ── EndFrame ────────────────────────────────────────────────────────────────
// Outro-Composition in den letzten ~15s: zentraler Show/Episode-Block +
// dezenter Outro-Hint. Rechte Bildhälfte bleibt frei für YouTube-Endscreen-
// Overlays (Subscribe-Button rechts oben, Next-Episode-Tile rechts unten).
const EndFrame: React.FC<{
  showName: string;
  episode: string;
  opacity: number;
}> = ({showName, episode, opacity}) => (
  <AbsoluteFill
    style={{
      opacity,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      pointerEvents: 'none',
      // Linke 60% des Bildes für den Outro-Block — rechte 40% bleibt frei
      // für die typischen YouTube-Endscreen-Slots (Subscribe rechts oben,
      // Next-Episode-Tile rechts mittig/unten).
      paddingRight: '40%',
      zIndex: 10,
    }}
  >
    <div
      style={{
        fontFamily: 'var(--font-display)',
        fontWeight: 500,
        fontSize: 72,
        letterSpacing: '-0.02em',
        color: 'var(--signal-pearl)',
        textTransform: 'uppercase',
      }}
    >
      {showName}
    </div>
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 22,
        letterSpacing: '0.08em',
        color: 'var(--signal-crimson)',
        marginTop: 16,
      }}
    >
      {episode}
    </div>
    <div
      style={{
        fontFamily: 'var(--font-display)',
        fontStyle: 'italic',
        fontSize: 28,
        color: 'var(--void-700)',
        marginTop: 64,
        letterSpacing: '0.01em',
      }}
    >
      — danke fürs zuhören —
    </div>
  </AbsoluteFill>
);

// ── MetaBar ─────────────────────────────────────────────────────────────────

const MetaBar: React.FC<{
  showName: string;
  episode: string;
  elapsed: number;
  total: number;
  audioLevel: number;
  activeSpeaker: 0 | 1 | null;
  isSilent: boolean;
  silenceBreath: number;
}> = ({showName, episode, elapsed, total, audioLevel, activeSpeaker, isSilent, silenceBreath}) => {
  // Active-Speaker-Indicator in der Mitte des Headers: kleiner Dot in der
  // Speaker-Farbe + Mono-Label. Bei null (Silence) gedimmt mit „—".
  const speakerColor =
    activeSpeaker === 0
      ? 'var(--signal-phosphor)'
      : activeSpeaker === 1
      ? 'var(--signal-spectre)'
      : 'var(--void-600)';
  const speakerLabel =
    activeSpeaker === 0 ? 'SPK·01' : activeSpeaker === 1 ? 'SPK·02' : '—';
  return (
    <div
      style={{
        position: 'absolute',
        top: 56,
        left: 120,
        right: 120,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        zIndex: 5,
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 16}}>
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: 'linear-gradient(135deg, var(--signal-crimson), var(--signal-ember))',
          }}
        />
        <span style={{fontWeight: 500, fontSize: 16, letterSpacing: '-0.01em', color: 'var(--signal-pearl)'}}>
          {showName}
        </span>
        <div style={{width: 1, height: 14, background: 'var(--void-400)'}} />
        <span style={{fontWeight: 400, fontSize: 15, color: 'var(--void-700)'}}>{episode}</span>
      </div>
      {/* Center: Active-Speaker-Indicator */}
      <div
        style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          transform: 'translate(-50%, -50%)',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: speakerColor,
            boxShadow: activeSpeaker !== null ? `0 0 6px ${speakerColor}` : 'none',
            opacity: activeSpeaker !== null ? 1 : 0.5,
          }}
        />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontWeight: 600,
            fontSize: 11,
            letterSpacing: '0.18em',
            color: speakerColor,
            opacity: activeSpeaker !== null ? 0.9 : 0.55,
          }}
        >
          {speakerLabel}
        </span>
      </div>
      <div style={{display: 'flex', alignItems: 'center', gap: 24}}>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontSize: 15,
            color: 'var(--void-700)',
          }}
        >
          {fmtTc(elapsed)} / {fmtTc(total)}
        </span>
        <div style={{display: 'flex', alignItems: 'center', gap: 8}}>
          {/* LIVE-Dot: bei Sprache pulst mit audioLevel (0.7..1.0), bei
              Silence atmet im 2s-Cycle (0.3..0.55) — konsistent zum Glow-
              Breath. */}
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: 999,
              background: 'var(--signal-crimson)',
              boxShadow: '0 0 8px var(--signal-crimson)',
              opacity: isSilent ? 0.3 + silenceBreath * 0.25 : 0.7 + audioLevel * 0.3,
            }}
          />
          <span
            style={{
              fontWeight: 500,
              fontSize: 13,
              color: 'var(--signal-pearl)',
              opacity: isSilent ? 0.5 : 1,
            }}
          >
            LIVE
          </span>
        </div>
      </div>
    </div>
  );
};

// ── PrompterArea ────────────────────────────────────────────────────────────

const PrompterArea: React.FC<{
  timeline: Timeline;
  currentTurn: Turn | null;
  frame: number;
  fps: number;
}> = ({timeline, currentTurn, frame, fps}) => {
  const nowMs = (frame / fps) * 1000;

  const {activeIdx, scrollFrac} = useMemo(() => {
    if (!timeline.ready || timeline.turns.length === 0) return {activeIdx: 0, scrollFrac: 0};
    if (currentTurn) return {activeIdx: timeline.turns.indexOf(currentTurn), scrollFrac: 0};
    if (nowMs < timeline.turns[0].startMs) return {activeIdx: 0, scrollFrac: 0};
    const last = timeline.turns.length - 1;
    if (nowMs >= timeline.turns[last].endMs) return {activeIdx: last, scrollFrac: 0};
    for (let i = 0; i < last; i++) {
      const end = timeline.turns[i].endMs;
      const next = timeline.turns[i + 1].startMs;
      if (nowMs >= end && nowMs < next) {
        const gap = next - end;
        return {activeIdx: i, scrollFrac: gap > 0 ? smoothstep((nowMs - end) / gap) : 0};
      }
    }
    return {activeIdx: 0, scrollFrac: 0};
  }, [timeline.turns, timeline.ready, currentTurn, nowMs]);

  // y-midpoints of each turn block (initial fallback for the very first
  // render-tick before useLayoutEffect has measured actual DOM positions).
  const cumYMid = useMemo(() => {
    const mids: number[] = [];
    let y = 0;
    timeline.turns.forEach((t, i) => {
      const h = estimateTurnH(t.text, i === activeIdx);
      mids.push(y + h / 2);
      y += h + TURN_GAP;
    });
    return mids;
  }, [timeline.turns, activeIdx]);

  // Prompter height: 1080 - top:160 - bottom:200 = 720; focal at 52%
  const FOCAL_Y = 720 * 0.52;

  // Initial-Estimate (überschrieben durch useLayoutEffect-Messung)
  const estimatedTargetY = useMemo(() => {
    if (cumYMid.length === 0) return 0;
    if (scrollFrac > 0 && activeIdx + 1 < cumYMid.length) {
      return cumYMid[activeIdx] + (cumYMid[activeIdx + 1] - cumYMid[activeIdx]) * scrollFrac;
    }
    return cumYMid[activeIdx] ?? 0;
  }, [cumYMid, activeIdx, scrollFrac]);

  // ── Anchor: präzise Zentrierung des active Turns am FOCAL_Y ───────────
  // Vorher wurde translateY aus estimateTurnH()-Schätzungen berechnet. Bei
  // langen Videos akkumulierten kleine Schätzfehler (line-wrap, font-metrics)
  // zu einer sichtbaren Drift — der active Turn wanderte über die Zeit aus
  // dem sichtbaren Bereich. Jetzt: refs auf active (und ggf. next-active)
  // Turn, useLayoutEffect liest offsetTop+offsetHeight nach jedem Render
  // und setzt transform direkt am inner-Container. Garantiert: active turn
  // immer exakt bei FOCAL_Y.
  const innerRef = useRef<HTMLDivElement | null>(null);
  const activeRef = useRef<HTMLDivElement | null>(null);
  const nextRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    const inner = innerRef.current;
    const active = activeRef.current;
    if (!inner || !active) return;
    const activeMid = active.offsetTop + active.offsetHeight / 2;
    let targetMid = activeMid;
    if (scrollFrac > 0 && nextRef.current) {
      const nextMid = nextRef.current.offsetTop + nextRef.current.offsetHeight / 2;
      targetMid = activeMid + (nextMid - activeMid) * scrollFrac;
    }
    const ty = FOCAL_Y - targetMid;
    inner.style.transform = `translateY(${ty.toFixed(2)}px)`;
  });

  return (
    <div
      style={{
        position: 'absolute',
        top: 160,
        bottom: 200,
        left: 120,
        right: 620,
        overflow: 'hidden',
        WebkitMaskImage:
          'linear-gradient(to bottom, transparent 0%, transparent 4%, black 26%, black 70%, transparent 96%, transparent 100%)',
        maskImage:
          'linear-gradient(to bottom, transparent 0%, transparent 4%, black 26%, black 70%, transparent 96%, transparent 100%)',
      }}
    >
      <div
        ref={innerRef}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          // Initial-Transform aus Estimate; wird per useLayoutEffect mit
          // gemessenem DOM-offset überschrieben (ohne Re-Render).
          transform: `translateY(${(FOCAL_Y - estimatedTargetY).toFixed(2)}px)`,
          display: 'flex',
          flexDirection: 'column',
          gap: TURN_GAP,
          willChange: 'transform',
        }}
      >
        {timeline.turns.map((turn, i) => {
          const isActive = i === activeIdx && scrollFrac < 0.5;
          const color = SIGNAL_BY_SPEAKER[turn.speaker] ?? 'var(--accent)';
          const ref =
            i === activeIdx ? activeRef : i === activeIdx + 1 ? nextRef : null;
          return (
            <TurnBlock
              key={i}
              ref={ref}
              turn={turn}
              isActive={isActive}
              nowMs={nowMs}
              color={color}
            />
          );
        })}
      </div>
    </div>
  );
};

const TurnBlock = React.forwardRef<
  HTMLDivElement,
  {
    turn: Turn;
    isActive: boolean;
    nowMs: number;
    color: string;
  }
>(({turn, isActive, nowMs, color}, ref) => {
  const fontSize = isActive ? 68 : 60;
  // Base-Caption-Opacity: bei aktivem Turn 0.92, bei inaktivem 0.36.
  // Im aktiven Turn werden alle Wörter via per-word style auf opacity 0.36
  // gedimmt (außer dem aktiv-gesprochenen + Afterglow-Schwanz).
  const captionOpacity = isActive ? 0.92 : 0.36;
  const AFTERGLOW_MS = 500;

  return (
    <div ref={ref}>
      <div style={{display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18}}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 999,
            background: color,
            boxShadow: isActive ? `0 0 10px ${color}` : undefined,
            flexShrink: 0,
          }}
        />
        <span style={{fontWeight: 500, fontSize: 15, letterSpacing: '-0.005em', color}}>
          {formatSpeakerLabel(turn.speaker)}
        </span>
        <span style={{width: 1, height: 12, background: 'var(--void-400)'}} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontWeight: 400,
            fontSize: 13,
            color: 'var(--void-600)',
          }}
        >
          {turn.score.toFixed(2)}
        </span>
      </div>
      <p
        style={{
          margin: 0,
          fontFamily: 'var(--font-display)',
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize,
          lineHeight: 1.14,
          letterSpacing: '-0.02em',
          color: `rgba(232,228,216,${captionOpacity})`,
        }}
      >
        {turn.words.length > 0 ? (
          turn.words.map((w, j) => {
            // Word-Fade im aktiven Turn:
            //   • zukünftiges Wort (nowMs < startMs): opacity 0.36 (dim)
            //   • aktuelles Wort (startMs..endMs):     speaker-color + glow
            //   • Afterglow (≤ 500ms nach endMs):      speaker-color, Glow fadet
            //   • Long past (>500ms nach endMs):        pearl (hell, lesbar)
            // Bei inaktivem Turn übernimmt parent-captionOpacity (alle dim).
            let style: React.CSSProperties = {};
            if (isActive) {
              const isCurrent = nowMs >= w.startMs && nowMs < w.endMs;
              const isPast = nowMs >= w.endMs;
              const elapsedSinceEnd = nowMs - w.endMs;
              const afterGlow =
                isPast && elapsedSinceEnd < AFTERGLOW_MS
                  ? 1 - elapsedSinceEnd / AFTERGLOW_MS
                  : 0;
              if (isCurrent) {
                style = {color, textShadow: '0 0 18px currentColor'};
              } else if (afterGlow > 0) {
                style = {
                  color,
                  textShadow: `0 0 ${(18 * afterGlow).toFixed(1)}px currentColor`,
                };
              } else if (isPast) {
                style = {color: 'var(--signal-pearl)'};
              } else {
                style = {opacity: 0.36};
              }
            }
            return (
              <React.Fragment key={j}>
                <span style={style}>{w.word}</span>
                {j < turn.words.length - 1 ? ' ' : null}
              </React.Fragment>
            );
          })
        ) : (
          turn.text
        )}
      </p>
    </div>
  );
});
TurnBlock.displayName = 'TurnBlock';

// ── RightPanel ──────────────────────────────────────────────────────────────

const RightPanel: React.FC<{
  spectrum: number[];
  waveform: number[];
  frame: number;
  fps: number;
  activeSpeaker: 0 | 1 | null;
  currentTurn: Turn | null;
  nextTurn: Turn | null;
  elapsed: number;
  silenceBreath: number;
}> = ({spectrum, waveform, frame, fps, activeSpeaker, currentTurn, nextTurn, elapsed, silenceBreath}) => {
  // 96 log-spaced bins für Spoke-Render (volle 360°, keine Spiegelung).
  // bin 1..255 wird log über 96 Spokes verteilt — Bass dehnt sich über viele
  // Spokes, Treble wird komprimiert. Dadurch wandert die spektrale Energie
  // sichtbar mit Phonemen um den Ring statt am 12-Uhr-Punkt zu klumpen.
  const spec96 = useMemo(() => {
    const out: number[] = [];
    const N = 96;
    const maxBin = spectrum.length - 1;
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1);
      const bin = Math.round(Math.pow(maxBin, t));
      out.push(spectrum[Math.min(maxBin, bin)] ?? 0);
    }
    return out;
  }, [spectrum]);

  // bassEnergy/midEnergy/centroid direkt aus raw spectrum (FFT-bins),
  // unabhängig vom Spoke-Mapping. Bin-Indizes entsprechen Frequenzen bei
  // sampleRate/512 Auflösung — bei 44.1kHz ≈ 86 Hz pro bin.
  const bassEnergy = useMemo(() => {
    const sub = spectrum.slice(1, 7);
    return Math.min(1, Math.log10(1 + (sub.reduce((a, b) => a + b, 0) / Math.max(1, sub.length)) * 9));
  }, [spectrum]);

  const spectralCentroid = useMemo(() => {
    let num = 0;
    let den = 0;
    for (let i = 0; i < spectrum.length; i++) {
      num += i * spectrum[i];
      den += spectrum[i];
    }
    return den < 1e-6 ? 0.25 : Math.min(1, num / (den * spectrum.length));
  }, [spectrum]);

  const midEnergy = useMemo(() => {
    const mid = spectrum.slice(8, 32);
    return Math.min(1, Math.log10(1 + (mid.reduce((a, b) => a + b, 0) / Math.max(1, mid.length)) * 9));
  }, [spectrum]);

  return (
    <div
      style={{
        position: 'absolute',
        top: 200,
        right: 120,
        width: 420,
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        zIndex: 4,
      }}
    >
      {/* Dual-channel waveform */}
      <div>
        <PanelHead title="Waveform" sub="Dual-Lane · live" />
        <DualWaveform waveform={waveform} activeSpeaker={activeSpeaker} />
      </div>

      {/* Compact ring */}
      <div>
        <PanelHead title="Taskmaster" sub="now · 監督" />
        <CompactRing
          spec96={spec96}
          bassEnergy={bassEnergy}
          spectralCentroid={spectralCentroid}
          midEnergy={midEnergy}
          activeSpeaker={activeSpeaker}
          currentTurn={currentTurn}
          silenceBreath={silenceBreath}
          frame={frame}
          fps={fps}
        />
      </div>

      {/* Up next */}
      <UpNextBar
        nextTurn={nextTurn}
        currentTurn={currentTurn}
        frame={frame}
        fps={fps}
        elapsed={elapsed}
      />
    </div>
  );
};

const PanelHead: React.FC<{title: string; sub: string}> = ({title, sub}) => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      marginBottom: 12,
    }}
  >
    <span style={{fontWeight: 500, fontSize: 13, color: 'var(--signal-pearl)'}}>{title}</span>
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontVariantNumeric: 'tabular-nums',
        fontWeight: 400,
        fontSize: 12,
        color: 'var(--void-600)',
      }}
    >
      {sub}
    </span>
  </div>
);

const DualWaveform: React.FC<{
  waveform: number[];
  activeSpeaker: 0 | 1 | null;
}> = ({waveform, activeSpeaker}) => {
  // Time-Domain-Waveform: jedes Sample ist eine signierte Amplitude ±1.
  // Sprach-Peaks liegen typisch bei 0.05–0.2 → ohne Gain praktisch unsichtbar
  // in einer 88 px hohen SVG. Mit GAIN=4.5 erreichen typische Peaks ~80 %
  // der Halbhöhe, lautere Stellen werden bei 1 geclamped.
  const SVG_W = 420;
  const SVG_H = 120;
  const CY = SVG_H / 2;
  const AMP = CY - 4; // 56 — fast volle Halbhöhe
  const GAIN = 4.5;
  const N = waveform.length;
  // Speaker-Wechsel klar sichtbar: aktive Lane voll, inaktive Lane auf 12 %.
  const uA = activeSpeaker === null ? 0.7 : activeSpeaker === 0 ? 1 : 0.12;
  const lA = activeSpeaker === null ? 0.7 : activeSpeaker === 1 ? 1 : 0.12;
  let dU = '';
  let dL = '';
  for (let i = 0; i < N; i++) {
    const x = (i / (N - 1)) * SVG_W;
    const v = Math.min(1, Math.abs(waveform[i] ?? 0) * GAIN);
    dU += `${i ? 'L' : 'M'}${x.toFixed(1)},${(CY - v * AMP * uA).toFixed(1)} `;
    dL += `${i ? 'L' : 'M'}${x.toFixed(1)},${(CY + v * AMP * lA).toFixed(1)} `;
  }
  // Active-Indicator-Dots — pulsieren bei aktivem Sprecher
  const dotR = 3.5;
  return (
    <svg viewBox={`0 0 ${SVG_W} ${SVG_H}`} width={SVG_W} height={SVG_H} style={{display: 'block'}}>
      {/* Center axis */}
      <line x1={0} y1={CY} x2={SVG_W} y2={CY} stroke="var(--void-300)" strokeWidth={1} strokeDasharray="2 5" opacity={0.6} />
      {/* Now-marker */}
      <line x1={SVG_W * 0.667} y1={4} x2={SVG_W * 0.667} y2={SVG_H - 4} stroke="var(--void-500)" strokeWidth={1} opacity={0.6} />
      {/* Lane labels */}
      <g transform={`translate(6 ${CY - AMP + 2})`}>
        <circle
          cx={0}
          cy={0}
          r={dotR}
          fill="var(--signal-phosphor)"
          opacity={activeSpeaker === 0 ? 1 : 0.35}
        />
        <text
          x={10}
          y={3.5}
          fill="var(--signal-phosphor)"
          fontFamily="var(--font-mono)"
          fontWeight={600}
          fontSize={9}
          letterSpacing="0.16em"
          opacity={activeSpeaker === 0 ? 1 : 0.45}
        >
          SPK·01
        </text>
      </g>
      <g transform={`translate(6 ${CY + AMP - 2})`}>
        <circle
          cx={0}
          cy={0}
          r={dotR}
          fill="var(--signal-spectre)"
          opacity={activeSpeaker === 1 ? 1 : 0.35}
        />
        <text
          x={10}
          y={3.5}
          fill="var(--signal-spectre)"
          fontFamily="var(--font-mono)"
          fontWeight={600}
          fontSize={9}
          letterSpacing="0.16em"
          opacity={activeSpeaker === 1 ? 1 : 0.45}
        >
          SPK·02
        </text>
      </g>
      <defs>
        <filter id="dw-glow" x="-3%" y="-50%" width="106%" height="200%">
          <feGaussianBlur stdDeviation="2" result="b1" />
          <feGaussianBlur stdDeviation="5" in="SourceGraphic" result="b2" />
          <feMerge>
            <feMergeNode in="b2" />
            <feMergeNode in="b1" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <g filter="url(#dw-glow)">
        <path d={dU} stroke="var(--signal-phosphor)" strokeWidth={1.5} fill="none" strokeLinecap="round" opacity={0.95} />
        <path d={dL} stroke="var(--signal-spectre)" strokeWidth={1.5} fill="none" strokeLinecap="round" opacity={0.95} />
      </g>
    </svg>
  );
};

const CompactRing: React.FC<{
  spec96: number[];
  bassEnergy: number;
  spectralCentroid: number;
  midEnergy: number;
  activeSpeaker: 0 | 1 | null;
  currentTurn: Turn | null;
  silenceBreath: number;
  frame: number;
  fps: number;
}> = ({spec96, bassEnergy, spectralCentroid, midEnergy, activeSpeaker, currentTurn, silenceBreath, frame, fps}) => {
  // Ring B — Sprech-Cadence: pulse-Periode skaliert mit Words-per-Second der
  // letzten 3s. Schnelles Sprechen (~4 wps) → period 12 (schnell pulsierend),
  // langsam/Pausen (~0 wps) → period 32 (gemächliches Atmen).
  const cadencePeriod = (() => {
    if (!currentTurn?.words?.length) return 24;
    const nowMs = (frame / fps) * 1000;
    const past3sMs = nowMs - 3000;
    const recentWords = currentTurn.words.filter(
      (w) => w.endMs >= past3sMs && w.startMs <= nowMs,
    );
    const wps = recentWords.length / 3;
    return Math.round(Math.max(12, Math.min(32, 32 - wps * 5)));
  })();
  const pulseFrom = frame - (frame % cadencePeriod);
  const pulse =
    spring({fps, frame: frame - pulseFrom, config: {damping: 14, stiffness: 140, mass: 0.6}, durationInFrames: 24}) *
    bassEnergy;

  const RB = 96, CX = 210, CY = 190, RIN = 92, ROUT = 86;
  const arcR = 82;
  const arcAngle = -90 + spectralCentroid * 360;
  const arcLen = 12 + midEnergy * 100;
  const a1 = (arcAngle * Math.PI) / 180;
  const a2 = ((arcAngle + arcLen) * Math.PI) / 180;
  const ax1 = CX + Math.cos(a1) * arcR;
  const ay1 = CY + Math.sin(a1) * arcR;
  const ax2 = CX + Math.cos(a2) * arcR;
  const ay2 = CY + Math.sin(a2) * arcR;
  const arcPath = `M ${ax1.toFixed(1)} ${ay1.toFixed(1)} A ${arcR} ${arcR} 0 ${arcLen > 180 ? 1 : 0} 1 ${ax2.toFixed(1)} ${ay2.toFixed(1)}`;

  const pupilR = 14 + pulse * 8;
  const ringOpacity = 0.45 + pulse * 0.35;
  // Ring C — Spectral-Centroid Modulation (kalibriert auf Sprach-Range
  // 0.10–0.45, da Sibilanten selten den theoretisch möglichen Vollbereich
  // erreichen). Ein normiertes c01 streckt den genutzten Bereich auf 0..1
  // — sonst bleiben alle Effekte unsichtbar.
  //   • glowR (Crimson-Glow-Radius) atmet ambient mit Stimm-Brightness
  //   • centroidRing als zusätzlicher Outer-Ring leuchtet bei hohen
  //     Frequenzen (Sibilanten s/sh/ch/t) deutlich auf
  //   • ringBrightness moduliert Bar-Opacity
  const c01 = Math.min(1, Math.max(0, (spectralCentroid - 0.1) / 0.35));
  const glowR = 150 + c01 * 60;
  const ringBrightness = 0.55 + c01 * 0.45;

  // Ring D — Confidence-Wobble + Glitch. Bei niedrigem turn.score:
  //   • Bars-Group wackelt sin/cos-phased (1–2 px, max 0.8 bei score=0.65)
  //   • Chromatic-Aberration via SVG-filter: ein R-shift nach rechts, ein
  //     B-shift nach links — Glitch wirkt wie defektes RGB-CRT-Display.
  //     Aberration-Strength wird in der filter-feOffset dx live aktualisiert.
  const score = currentTurn?.score ?? 1;
  const lowConfidence = score < 0.85;
  const confidenceIntensity = lowConfidence ? (0.85 - score) * 4 : 0; // 0..0.8
  const wobble = lowConfidence
    ? {
        x: Math.sin(frame * 0.65) * confidenceIntensity,
        y: Math.cos(frame * 0.54) * confidenceIntensity,
      }
    : {x: 0, y: 0};
  const chromShift = lowConfidence ? Math.max(1, confidenceIntensity * 4) : 0; // 0..3.2 px

  // glowOpacity setzt sich aus drei Modulations-Quellen zusammen:
  //   • base 0.28
  //   • pulse-modulated (sprech-rhythmisch, cadence-driven)
  //   • centroid-modulated (stimmen-brightness)
  //   • silenceBreath (nur bei Stille, atmend +0.25) — von Parent übergeben
  const glowOpacity =
    0.28 + pulse * 0.15 + c01 * 0.2 + silenceBreath * 0.25;

  return (
    <svg viewBox="0 0 420 380" width={420} height={380} style={{display: 'block'}}>
      <defs>
        <radialGradient id="cr-glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="var(--signal-crimson)" stopOpacity={glowOpacity} />
          <stop offset="100%" stopColor="var(--signal-crimson)" stopOpacity={0} />
        </radialGradient>
        <radialGradient id="cr-bar-00" cx="0.5" cy="1" r="1">
          <stop offset="0%" stopColor="var(--signal-phosphor)" />
          <stop offset="100%" stopColor="var(--signal-phosphor)" stopOpacity={0.2} />
        </radialGradient>
        <radialGradient id="cr-bar-01" cx="0.5" cy="1" r="1">
          <stop offset="0%" stopColor="var(--signal-spectre)" />
          <stop offset="100%" stopColor="var(--signal-spectre)" stopOpacity={0.2} />
        </radialGradient>
        {/*
          Confidence-Glitch — RGB-Channel-Split:
          • R-Channel verschoben um +chromShift px (nach rechts)
          • B-Channel verschoben um -chromShift px (nach links)
          • G-Channel bleibt zentriert
          Bei chromShift=0 hat der Filter keinen sichtbaren Effekt (Pass-through).
        */}
        <filter id="cr-glitch" x="-10%" y="-10%" width="120%" height="120%">
          <feOffset in="SourceGraphic" dx={chromShift} dy={0} result="r-pos" />
          <feColorMatrix
            in="r-pos"
            type="matrix"
            values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
            result="r"
          />
          <feOffset in="SourceGraphic" dx={-chromShift} dy={0} result="b-pos" />
          <feColorMatrix
            in="b-pos"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"
            result="b"
          />
          <feMerge>
            <feMergeNode in="r" />
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <circle cx={CX} cy={CY} r={glowR} fill="url(#cr-glow)" />

      {/*
       * Bars zeigen Mono-Spectrum log-mapped über volle 360° — Bass am
       * 12-Uhr-Punkt, Treble bei kurz-vor-12 CCW. Treble-Boost (2x bei
       * höchstem Bin) gleicht den natürlichen Sprach-Bass-Bias aus.
       * Sprecher-Identität durch globale Bar-Farbe. Wobble (Ring D)
       * als group-transform.
       */}
      <g
        transform={`translate(${wobble.x.toFixed(2)}, ${wobble.y.toFixed(2)})`}
        filter={lowConfidence ? 'url(#cr-glitch)' : undefined}
      >
        {(() => {
          const activeBarGrad = activeSpeaker === 1 ? 'cr-bar-01' : 'cr-bar-00';
          return Array.from({length: RB}).map((_, i) => {
            const angle = (i / RB) * Math.PI * 2 - Math.PI / 2;
            const deg = ((angle * 180) / Math.PI + 360) % 360;
            const inSeam =
              (deg < 4 || deg > 356) ||
              (deg > 86 && deg < 94) ||
              (deg > 176 && deg < 184) ||
              (deg > 266 && deg < 274);
            if (inSeam) return null;
            const v = spec96[i] ?? 0;
            const trebleBoost = 1 + i / (RB - 1); // 1x bei Bass → 2x bei Treble
            const logMag = Math.min(1, Math.log10(1 + v * 20 * trebleBoost));
            const len = Math.max(6, logMag * ROUT);
            const x1 = CX + Math.cos(angle) * RIN;
            const y1 = CY + Math.sin(angle) * RIN;
            const x2 = CX + Math.cos(angle) * (RIN + len);
            const y2 = CY + Math.sin(angle) * (RIN + len);
            return (
              <line
                key={i}
                x1={x1.toFixed(1)}
                y1={y1.toFixed(1)}
                x2={x2.toFixed(1)}
                y2={y2.toFixed(1)}
                stroke={`url(#${activeBarGrad})`}
                strokeWidth={1.5}
                strokeLinecap="round"
                opacity={0.85 * ringBrightness}
              />
            );
          });
        })()}
      </g>

      <circle
        cx={CX}
        cy={CY}
        r={arcR}
        fill="none"
        stroke="var(--signal-crimson)"
        strokeWidth={1}
        opacity={ringOpacity}
        style={{filter: 'drop-shadow(0 0 8px var(--signal-crimson))'}}
      />
      <circle cx={CX} cy={CY} r={66} fill="var(--void-050)" />
      <line x1={CX - 56} y1={CY} x2={CX + 56} y2={CY} stroke="var(--void-400)" strokeWidth={1} opacity={0.45} />
      <line x1={CX} y1={CY - 56} x2={CX} y2={CY + 56} stroke="var(--void-400)" strokeWidth={1} opacity={0.45} />
      <circle cx={CX} cy={CY} r={30} fill="none" stroke="var(--void-500)" strokeWidth={1} opacity={0.5} />
      <circle cx={CX} cy={CY} r={50} fill="none" stroke="var(--void-500)" strokeWidth={1} opacity={0.35} />

      <path
        d={arcPath}
        stroke="var(--signal-crimson)"
        strokeWidth={1.5}
        fill="none"
        strokeLinecap="round"
        opacity={0.85}
        style={{filter: 'drop-shadow(0 0 6px var(--signal-crimson))'}}
      />
      <circle cx={CX} cy={CY} r={pupilR + 8} fill="var(--signal-crimson)" opacity={0.12 + pulse * 0.18} />
      <circle
        cx={CX}
        cy={CY}
        r={pupilR}
        fill="var(--signal-crimson)"
        opacity={0.98}
        style={{filter: 'drop-shadow(0 0 14px var(--signal-crimson))'}}
      />
      <circle cx={CX} cy={CY} r={4} fill="var(--signal-pearl)" />
    </svg>
  );
};

const UpNextBar: React.FC<{
  nextTurn: Turn | null;
  currentTurn: Turn | null;
  frame: number;
  fps: number;
  elapsed: number;
}> = ({nextTurn, currentTurn, frame, fps, elapsed}) => {
  if (!nextTurn) return null;
  const color = SIGNAL_BY_SPEAKER[nextTurn.speaker] ?? 'var(--accent)';
  const dt = nextTurn.startMs / 1000 - elapsed;
  const dtLabel = dt > 0 ? `in ${dt.toFixed(1)}s` : '—';
  // Countdown-Linie: schrumpft von 100 % auf 0 % über die Dauer des aktuellen
  // Turns hinweg. Glow in der next-Speaker-Farbe — visuelles Pendant zum
  // textuellen Countdown („in 3.8s") direkt drüber. Bei null currentTurn
  // (Silence-Phase) wird die Linie ausgeblendet.
  const lineFraction = currentTurn
    ? Math.max(
        0,
        Math.min(
          1,
          1 -
            ((frame / fps) * 1000 - currentTurn.startMs) /
              Math.max(1, currentTurn.endMs - currentTurn.startMs),
        ),
      )
    : 0;
  return (
    <div style={{position: 'relative', paddingTop: 12}}>
      {/* Countdown-Track + animierte Linie statt statischer Border-Top */}
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          height: 1,
          background: 'var(--void-300)',
          opacity: 0.55,
        }}
      />
      <div
        style={{
          position: 'absolute',
          top: -0.5,
          right: 0,
          width: `${(lineFraction * 100).toFixed(2)}%`,
          height: 2,
          background: color,
          boxShadow: `0 0 6px ${color}, 0 0 12px ${color}`,
          opacity: 0.95,
          transition: 'none',
        }}
      />
      <div style={{display: 'flex', alignItems: 'center', gap: 10}}>
        <span style={{fontWeight: 500, fontSize: 13, color: 'var(--void-600)', marginRight: 'auto'}}>
          Up next
        </span>
        <span
          style={{
            width: 6,
            height: 6,
            borderRadius: 999,
            background: color,
            boxShadow: `0 0 6px ${color}`,
          }}
        />
        <span style={{fontWeight: 500, fontSize: 14, color}}>
          {formatSpeakerLabel(nextTurn.speaker)}
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontVariantNumeric: 'tabular-nums',
            fontSize: 12,
            color: 'var(--void-600)',
          }}
        >
          {dtLabel}
        </span>
      </div>
    </div>
  );
};

// ── MonologueArea ───────────────────────────────────────────────────────────

const MonologueArea: React.FC<{
  timeline: Timeline;
  spectrum: number[];
  waveform: number[];
  currentTurn: Turn | null;
  activeSpeaker: 0 | 1 | null;
  silenceBreath: number;
  frame: number;
  fps: number;
}> = ({timeline, spectrum, waveform, currentTurn, activeSpeaker, silenceBreath, frame, fps}) => {
  const nowMs = (frame / fps) * 1000;

  // 128 log-spaced bins für Spoke-Render (volle 360°, keine Spiegelung).
  // Analog zu spec96 im Dialogue-Mode — log-mapping verteilt Sprach-Energie
  // sichtbar über den ganzen Umfang statt am 12-Uhr-Punkt zu klumpen.
  const spec128 = useMemo(() => {
    const out: number[] = [];
    const N = 128;
    const maxBin = spectrum.length - 1;
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1);
      const bin = Math.round(Math.pow(maxBin, t));
      out.push(spectrum[Math.min(maxBin, bin)] ?? 0);
    }
    return out;
  }, [spectrum]);

  // bassEnergy/midEnergy/centroid direkt aus raw spectrum, unabhängig
  // vom Spoke-Mapping.
  const bassEnergy = useMemo(() => {
    const sub = spectrum.slice(1, 10);
    return Math.min(1, Math.log10(1 + (sub.reduce((a, b) => a + b, 0) / Math.max(1, sub.length)) * 9));
  }, [spectrum]);

  const spectralCentroid = useMemo(() => {
    let num = 0;
    let den = 0;
    for (let i = 0; i < spectrum.length; i++) {
      num += i * spectrum[i];
      den += spectrum[i];
    }
    return den < 1e-6 ? 0.25 : Math.min(1, num / (den * spectrum.length));
  }, [spectrum]);

  const midEnergy = useMemo(() => {
    const mid = spectrum.slice(12, 48);
    return Math.min(1, Math.log10(1 + (mid.reduce((a, b) => a + b, 0) / Math.max(1, mid.length)) * 9));
  }, [spectrum]);

  const speakerColor =
    SIGNAL_BY_SPEAKER[currentTurn?.speaker ?? 'SPEAKER_00'] ?? 'var(--signal-phosphor)';

  const AFTERGLOW_MS = 500;

  // Find the last chapter for the chapter tag
  const activeChapter = useMemo(() => {
    return timeline.chapters.find((c) => nowMs >= c.startMs && nowMs < c.endMs) ?? null;
  }, [timeline.chapters, nowMs]);

  return (
    <>
      {/* Chapter tag */}
      {activeChapter && (
        <div
          style={{
            position: 'absolute',
            top: 160,
            left: '50%',
            transform: 'translateX(-50%)',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            zIndex: 5,
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontWeight: 500,
              fontSize: 11,
              letterSpacing: '0.18em',
              color: 'var(--void-700)',
              whiteSpace: 'nowrap',
              textTransform: 'uppercase',
            }}
          >
            CHAPTER
            <span style={{color: 'var(--signal-crimson)'}}> · 章 · </span>
            {activeChapter.title}
          </span>
        </div>
      )}

      {/* Speaker row */}
      <div
        style={{
          position: 'absolute',
          top: activeChapter ? 200 : 160,
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: 14,
          zIndex: 5,
        }}
      >
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: 999,
            background: speakerColor,
            boxShadow: `0 0 10px ${speakerColor}`,
          }}
        />
        <span style={{fontWeight: 500, fontSize: 16, letterSpacing: '-0.005em', color: speakerColor}}>
          {currentTurn ? formatSpeakerLabel(currentTurn.speaker) : 'Speaker 01'}
        </span>
        {currentTurn && (
          <>
            <span style={{width: 1, height: 12, background: 'var(--void-400)'}} />
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontVariantNumeric: 'tabular-nums',
                fontWeight: 400,
                fontSize: 13,
                color: 'var(--void-600)',
              }}
            >
              {currentTurn.score.toFixed(2)}
            </span>
          </>
        )}
      </div>

      {/* Centered ring */}
      <div
        style={{
          position: 'absolute',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -54%)',
          zIndex: 3,
        }}
      >
        <MonoRing
          spec128={spec128}
          bassEnergy={bassEnergy}
          spectralCentroid={spectralCentroid}
          midEnergy={midEnergy}
          activeSpeaker={activeSpeaker}
          currentTurn={currentTurn}
          silenceBreath={silenceBreath}
          frame={frame}
          fps={fps}
        />
      </div>

      {/* Caption row */}
      <div
        style={{
          position: 'absolute',
          bottom: 200,
          left: 200,
          right: 200,
          zIndex: 5,
        }}
      >
        <p
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontWeight: 500,
            fontSize: 56,
            lineHeight: 1.22,
            letterSpacing: '-0.02em',
            textAlign: 'center',
            color: 'rgba(232,228,216,0.30)',
          }}
        >
          {currentTurn && currentTurn.words.length > 0 ? (
            currentTurn.words.map((w, i) => {
              // Word-Fade (analog Teleprompter):
              //   • Future word: dim
              //   • Current:    speaker color + glow
              //   • Afterglow:  speaker color, glow fades
              //   • Long past:  pearl (lesbar)
              const isCurrent = nowMs >= w.startMs && nowMs < w.endMs;
              const isPast = nowMs >= w.endMs;
              const elapsedSinceEnd = nowMs - w.endMs;
              const afterGlow =
                isPast && elapsedSinceEnd < AFTERGLOW_MS
                  ? 1 - elapsedSinceEnd / AFTERGLOW_MS
                  : 0;
              let style: React.CSSProperties;
              if (isCurrent) {
                style = {color: speakerColor, textShadow: '0 0 28px currentColor'};
              } else if (afterGlow > 0) {
                style = {
                  color: speakerColor,
                  textShadow: `0 0 ${(28 * afterGlow).toFixed(1)}px currentColor`,
                };
              } else if (isPast) {
                style = {color: 'var(--signal-pearl)'};
              } else {
                style = {opacity: 0.3};
              }
              return (
                <React.Fragment key={i}>
                  <span style={style}>{w.word}</span>
                  {i < currentTurn.words.length - 1 ? ' ' : null}
                </React.Fragment>
              );
            })
          ) : (
            currentTurn?.text ?? ''
          )}
        </p>
      </div>

      {/* Bottom waveform — Time-Domain analog DualWaveform */}
      <MonoWaveform waveform={waveform} color={speakerColor} />
    </>
  );
};

const MonoRing: React.FC<{
  spec128: number[];
  bassEnergy: number;
  spectralCentroid: number;
  midEnergy: number;
  activeSpeaker: 0 | 1 | null;
  currentTurn: Turn | null;
  silenceBreath: number;
  frame: number;
  fps: number;
}> = ({spec128, bassEnergy, spectralCentroid, midEnergy, activeSpeaker, currentTurn, silenceBreath, frame, fps}) => {
  // Cadence-Pulse (analog CompactRing): pulse-Periode aus Words-per-Second der
  // letzten 3 s. Bei Monologue ist meist nur ein Sprecher — Cadence skaliert
  // mit dessen Sprechtempo.
  const cadencePeriod = (() => {
    if (!currentTurn?.words?.length) return 26;
    const nowMs = (frame / fps) * 1000;
    const past3sMs = nowMs - 3000;
    const recentWords = currentTurn.words.filter(
      (w) => w.endMs >= past3sMs && w.startMs <= nowMs,
    );
    const wps = recentWords.length / 3;
    return Math.round(Math.max(14, Math.min(34, 34 - wps * 5)));
  })();
  const pulseFrom = frame - (frame % cadencePeriod);
  const pulse =
    spring({fps, frame: frame - pulseFrom, config: {damping: 14, stiffness: 120, mass: 0.6}, durationInFrames: 28}) *
    bassEnergy;

  const MRB = 128, MCX = 300, MCY = 300, MRIN = 132, MROUT = 122, arcR = 122;
  const arcAngle = -90 + spectralCentroid * 360;
  const arcLen = 14 + midEnergy * 110;
  const a1 = (arcAngle * Math.PI) / 180;
  const a2 = ((arcAngle + arcLen) * Math.PI) / 180;
  const ax1 = MCX + Math.cos(a1) * arcR;
  const ay1 = MCY + Math.sin(a1) * arcR;
  const ax2 = MCX + Math.cos(a2) * arcR;
  const ay2 = MCY + Math.sin(a2) * arcR;
  const arcPath = `M ${ax1.toFixed(1)} ${ay1.toFixed(1)} A ${arcR} ${arcR} 0 ${arcLen > 180 ? 1 : 0} 1 ${ax2.toFixed(1)} ${ay2.toFixed(1)}`;

  const pupilR = 20 + pulse * 10;
  const ringOpacity = 0.45 + pulse * 0.4;

  // Spectral-Centroid Modulation (kalibriert auf c01) — analog CompactRing
  const c01 = Math.min(1, Math.max(0, (spectralCentroid - 0.1) / 0.35));
  const glowOpacity = 0.32 + pulse * 0.12 + c01 * 0.2 + silenceBreath * 0.25;
  const glowR = 220 + c01 * 60;
  const ringBrightness = 0.55 + c01 * 0.45;

  // Confidence-Wobble + Glitch (analog CompactRing)
  const score = currentTurn?.score ?? 1;
  const lowConfidence = score < 0.85;
  const confidenceIntensity = lowConfidence ? (0.85 - score) * 4 : 0;
  const wobble = lowConfidence
    ? {
        x: Math.sin(frame * 0.65) * confidenceIntensity,
        y: Math.cos(frame * 0.54) * confidenceIntensity,
      }
    : {x: 0, y: 0};
  const chromShift = lowConfidence ? Math.max(1, confidenceIntensity * 4) : 0;

  // Bar-Gradient nach activeSpeaker (mr-bar-00 = phosphor, mr-bar-01 = spectre)
  const activeBarGrad = activeSpeaker === 1 ? 'mr-bar-01' : 'mr-bar-00';

  return (
    <svg viewBox="0 0 600 600" width={600} height={600} style={{display: 'block'}}>
      <defs>
        <radialGradient id="mr-glow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0%" stopColor="var(--signal-crimson)" stopOpacity={glowOpacity} />
          <stop offset="100%" stopColor="var(--signal-crimson)" stopOpacity={0} />
        </radialGradient>
        <radialGradient id="mr-bar-00" cx="0.5" cy="1" r="1">
          <stop offset="0%" stopColor="var(--signal-phosphor)" />
          <stop offset="100%" stopColor="var(--signal-phosphor)" stopOpacity={0.15} />
        </radialGradient>
        <radialGradient id="mr-bar-01" cx="0.5" cy="1" r="1">
          <stop offset="0%" stopColor="var(--signal-spectre)" />
          <stop offset="100%" stopColor="var(--signal-spectre)" stopOpacity={0.15} />
        </radialGradient>
        <filter id="mr-glitch" x="-10%" y="-10%" width="120%" height="120%">
          <feOffset in="SourceGraphic" dx={chromShift} dy={0} result="r-pos" />
          <feColorMatrix
            in="r-pos"
            type="matrix"
            values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
            result="r"
          />
          <feOffset in="SourceGraphic" dx={-chromShift} dy={0} result="b-pos" />
          <feColorMatrix
            in="b-pos"
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0"
            result="b"
          />
          <feMerge>
            <feMergeNode in="r" />
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <circle cx={MCX} cy={MCY} r={glowR} fill="url(#mr-glow)" />

      <g
        transform={`translate(${wobble.x.toFixed(2)}, ${wobble.y.toFixed(2)})`}
        filter={lowConfidence ? 'url(#mr-glitch)' : undefined}
      >
        {Array.from({length: MRB}).map((_, i) => {
          const angle = (i / MRB) * Math.PI * 2 - Math.PI / 2;
          // Log-mapped spec128: Bass am 12 Uhr, Treble bei kurz-vor-12 CCW.
          // Treble-Boost (2x bei höchstem Bin) gleicht den Sprach-Bass-Bias aus.
          const v = spec128[i] ?? 0;
          const trebleBoost = 1 + i / (MRB - 1);
          const logMag = Math.min(1, Math.log10(1 + v * 20 * trebleBoost));
          const len = Math.max(6, logMag * MROUT);
          const x1 = MCX + Math.cos(angle) * MRIN;
          const y1 = MCY + Math.sin(angle) * MRIN;
          const x2 = MCX + Math.cos(angle) * (MRIN + len);
          const y2 = MCY + Math.sin(angle) * (MRIN + len);
          return (
            <line
              key={i}
              x1={x1.toFixed(1)}
              y1={y1.toFixed(1)}
              x2={x2.toFixed(1)}
              y2={y2.toFixed(1)}
              stroke={`url(#${activeBarGrad})`}
              strokeWidth={1.5}
              strokeLinecap="round"
              opacity={(0.5 + logMag * 0.4) * ringBrightness}
            />
          );
        })}
      </g>

      <circle
        cx={MCX}
        cy={MCY}
        r={arcR}
        fill="none"
        stroke="var(--signal-crimson)"
        strokeWidth={1}
        opacity={ringOpacity}
        style={{filter: 'drop-shadow(0 0 10px var(--signal-crimson))'}}
      />
      <circle cx={MCX} cy={MCY} r={98} fill="var(--void-050)" />
      <line x1={MCX - 82} y1={MCY} x2={MCX + 82} y2={MCY} stroke="var(--void-400)" strokeWidth={1} opacity={0.4} />
      <line x1={MCX} y1={MCY - 82} x2={MCX} y2={MCY + 82} stroke="var(--void-400)" strokeWidth={1} opacity={0.4} />
      <circle cx={MCX} cy={MCY} r={44} fill="none" stroke="var(--void-500)" strokeWidth={1} opacity={0.45} />
      <circle cx={MCX} cy={MCY} r={72} fill="none" stroke="var(--void-500)" strokeWidth={1} opacity={0.3} />

      <path
        d={arcPath}
        stroke="var(--signal-crimson)"
        strokeWidth={1.5}
        fill="none"
        strokeLinecap="round"
        opacity={0.85}
        style={{filter: 'drop-shadow(0 0 8px var(--signal-crimson))'}}
      />
      <circle cx={MCX} cy={MCY} r={pupilR + 12} fill="var(--signal-crimson)" opacity={0.14 + pulse * 0.2} />
      <circle
        cx={MCX}
        cy={MCY}
        r={pupilR}
        fill="var(--signal-crimson)"
        opacity={0.98}
        style={{filter: 'drop-shadow(0 0 18px var(--signal-crimson))'}}
      />
      <circle cx={MCX} cy={MCY} r={6} fill="var(--signal-pearl)" />
    </svg>
  );
};

const MonoWaveform: React.FC<{waveform: number[]; color: string}> = ({waveform, color}) => {
  // Time-Domain analog DualWaveform: signed Audio-Samples, symmetrische
  // Auslenkung um die Mittellinie. Gain=4.5 mit Clamp wie in DualWaveform.
  const W = 1680;
  const H = 60;
  const CY = H / 2;
  const AMP = CY - 4;
  const GAIN = 4.5;
  const N = waveform.length;
  // Envelope: in der Mitte am stärksten, an den Rändern sanft auslaufend
  let dUp = '';
  let dDown = '';
  for (let i = 0; i < N; i++) {
    const x = (i / (N - 1)) * W;
    const env = 0.45 + 0.55 * Math.exp(-Math.pow((i - N / 2) / (N * 0.35), 2));
    const v = Math.min(1, Math.abs(waveform[i] ?? 0) * GAIN) * env;
    dUp += `${i ? 'L' : 'M'}${x.toFixed(1)},${(CY - v * AMP).toFixed(1)} `;
    dDown += `${i ? 'L' : 'M'}${x.toFixed(1)},${(CY + v * AMP).toFixed(1)} `;
  }
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 140,
        left: 120,
        right: 120,
        zIndex: 4,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontFamily: 'var(--font-mono)',
          fontWeight: 500,
          fontSize: 11,
          letterSpacing: '0.16em',
          color: 'var(--void-600)',
          marginBottom: 8,
          textTransform: 'uppercase',
        }}
      >
        <span style={{color}}>Waveform</span>
        <span style={{color: 'var(--void-700)'}}>Single-Lane · live</span>
      </div>
      <svg viewBox="0 0 1680 60" width="100%" height={60} preserveAspectRatio="none" style={{display: 'block'}}>
        <defs>
          <filter id="mw-glow" x="-3%" y="-50%" width="106%" height="200%">
            <feGaussianBlur stdDeviation="2" result="b1" />
            <feGaussianBlur stdDeviation="5" in="SourceGraphic" result="b2" />
            <feMerge>
              <feMergeNode in="b2" />
              <feMergeNode in="b1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <line x1={0} y1={30} x2={1680} y2={30} stroke="var(--void-300)" strokeWidth={1} strokeDasharray="2 6" opacity={0.5} />
        <line x1={1120} y1={4} x2={1120} y2={56} stroke="var(--void-500)" strokeWidth={1} opacity={0.6} />
        <g filter="url(#mw-glow)">
          <path d={dUp} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" opacity={0.95} />
          <path d={dDown} stroke={color} strokeWidth={1.5} fill="none" strokeLinecap="round" opacity={0.95} />
        </g>
      </svg>
    </div>
  );
};

// ── FooterBar ───────────────────────────────────────────────────────────────

const FooterBar: React.FC<{vizMode: DialogueVizMode}> = ({vizMode}) => (
  <div
    style={{
      position: 'absolute',
      bottom: 56,
      left: 120,
      right: 120,
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      zIndex: 5,
    }}
  >
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 500,
        fontSize: 11,
        letterSpacing: '0.12em',
        textTransform: 'uppercase',
        color: 'var(--void-600)',
      }}
    >
      {vizMode === 'dialogue' ? 'Dialogue View · 対話' : 'Monologue View · 独白'}
    </span>
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontWeight: 400,
        fontSize: 12,
        color: 'var(--void-600)',
      }}
    >
      {vizMode === 'dialogue' ? 'Dual-Lane · WhisperX' : 'Single-Lane · WhisperX'}
    </span>
  </div>
);
