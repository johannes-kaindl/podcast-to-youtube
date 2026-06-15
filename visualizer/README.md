# Kuro Signal Protocol — Podcast Visualizer (Remotion)

A 1920×1080 / 30 fps podcast visualizer rendered with Remotion 4.x. It turns a
WhisperX transcript + audio into the video for the pipeline's **render** phase.

## Compositions

A single `DialogueVisualizer` (`src/DialogueComposition.tsx`) drives two modes via
its `vizMode` prop, registered as two compositions in `src/Root.tsx`:

| `--viz` (pipeline) | Composition id | Layout |
| --- | --- | --- |
| `dialogue` | `Podcast-Dialogue` | Two-column: teleprompter (left) + waveform/ring (right). For 2-speaker conversations. |
| `monologue` | `Podcast-Monologue` | Centered ring + bottom caption. For single-speaker episodes. |

Duration is derived from the audio at render time (`calculateMetadata` reads
`public/podcast.wav`); `defaultProps` carry `title` / `episode` / `showName`.

## Inputs

The pipeline's `render_video.py` populates `public/` before rendering:

- `podcast.wav` — the episode audio, converted to WAV with a short trailing pad.
- `podcast.whisperx.json` — the WhisperX transcript (segments + speakers); the
  timeline loader (`src/utils/timeline.ts`) reads this via `staticFile`.
- `podcast.srt` — optional captions (an empty file is written if absent).

## Scripts

```bash
npm run dev          # remotion studio (interactive preview)
npm run build        # tsc --noEmit + remotion bundle
npm run test         # vitest (timeline + speaker helpers)
npm run lint         # biome check
npm run typecheck    # tsc --noEmit
npm run render:dialogue    # remotion render Podcast-Dialogue out/dialogue.mp4
npm run render:monologue   # remotion render Podcast-Monologue out/monologue.mp4
```

In the normal flow you don't call these directly — the Python pipeline invokes
`npx remotion render src/Root.tsx Podcast-{Dialogue,Monologue} …` from `render_video.py`.

## Architecture

```
src/
  Root.tsx                      ← registerRoot · Podcast-Dialogue + Podcast-Monologue
  DialogueComposition.tsx       ← the visualizer (vizMode: dialogue | monologue)
  styles.css                    ← KSP design tokens
  components/
    ChamberBackground.tsx       ← void + grid + corner ticks + grain
    ProgressHairline.tsx        ← thin top progress line
    SectionCard.tsx             ← chapter card (honours useReducedMotion)
  utils/
    timeline.ts                 ← WhisperX → Turn/Word/Chapter timeline + frame selectors
    speakers.ts                 ← SPEAKER_xx → Signal hue
```

### Performance contract

- `useCurrentFrame()` is read once in the composition; child pieces receive `frame`.
- `useWindowedAudioData({windowInSeconds: 30})` — long episodes never load whole-file
  PCM into memory.
- `visualizeAudio` / `visualizeAudioWaveform` with power-of-two sample counts.
- Animations short-circuit when `useReducedMotion()` is true.
