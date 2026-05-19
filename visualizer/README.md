# Kuro Signal Protocol — Podcast Visualizer (Remotion)

A 1920×1080 / 30fps podcast visualizer rendered with Remotion 4.x. Three
visualization modes — `bars` · `waveform` · `ring` — share a single
chamber, header, footer-meta and caption strip, but each runs under a
different KSP **Aspect**:

| `vizType`  | Aspect              | Accent     |
| ---------- | ------------------- | ---------- |
| `bars`     | Guardian (*Shugo*)  | Phosphor   |
| `waveform` | Strategist (*Gunshi*) | Spectre  |
| `ring`     | Taskmaster (*Kantoku*) | Crimson |

## Inputs

Drop into your Remotion project's `public/`:

- `podcast.mp3` — German conversational podcast, 1–3 speakers
- `podcast.srt` — SRT, optional `[SPEAKER_00] …` tags per line

Then `npx remotion render Podcast-Bars out/bars.mp4`
(or `Podcast-Waveform`, `Podcast-Ring`).

## Architecture

```
src/
  Root.tsx                      ← registerRoot · 3 compositions
  Composition.tsx               ← reads frame ONCE, useWindowedAudioData(30s)
  styles.css                    ← KSP tokens (mirror of design system)
  components/
    ChamberBackground.tsx       ← void + 1px grid + corner ticks + grain
    HeaderBar.tsx               ← sigil · wordmark · title · timecode · chips
    FooterMeta.tsx              ← LIVE indicator + window status
    Captions.tsx                ← SRT, 4-frame fade in, speaker chip
  visualizers/
    AudioBars.tsx               ← 64 bins, log-scaled, mirrored
    AudioWaveform.tsx           ← 512-sample time domain + glow
    AudioRing.tsx               ← 128-bin polar + spring bass-pulse
  utils/
    captions.ts                 ← parseSrt + delayRender bridge
    speakers.ts                 ← SPEAKER_xx → Signal hue
```

### Performance contract

- `useCurrentFrame()` is called **once** in `Composition.tsx`; visualizers
  receive `frame` as a prop. No leaf hook subscriptions.
- `useWindowedAudioData({windowInSeconds: 30})` — long pods don't load
  whole-file PCM into memory.
- `visualizeAudio({optimizeFor: 'speed'})`, `numberOfSamples` always a
  power of two (`64` for bars, `128` for ring; `512` for waveform).
- All animations short-circuit when `useReducedMotion()` is true.
