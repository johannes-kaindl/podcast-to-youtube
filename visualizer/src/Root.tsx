import {Composition, registerRoot, staticFile} from 'remotion';
import {getAudioDurationInSeconds} from '@remotion/media-utils';
import {DialogueVisualizer} from './DialogueComposition';
import type {DialogueVizMode} from './DialogueComposition';
import './styles.css';

// 30fps · 1920×1080. Duration is computed dynamically from public/podcast.wav
// via calculateMetadata; FALLBACK is used if the probe fails (e.g. in Studio
// before an audio file is dropped in).
const FPS = 30;
const FALLBACK_DURATION = FPS * 60 * 3;
// render_video.py pads the WAV with this many seconds of trailing silence so
// useWindowedAudioData (windowInSeconds: 30) never overruns EOF at the end of
// the render. We subtract it back here so the video stops at the original
// audio's last sample. MUST match AUDIO_PAD_SEC in render_video.py.
const AUDIO_TRAILING_PAD_SECONDS = 20;

const calcAudioDuration = async () => {
  try {
    const seconds = await getAudioDurationInSeconds(staticFile('podcast.wav'));
    const usable = Math.max(1, Math.floor((seconds - AUDIO_TRAILING_PAD_SECONDS) * FPS));
    return {durationInFrames: usable};
  } catch {
    return {durationInFrames: FALLBACK_DURATION};
  }
};

export const Root: React.FC = () => {
  return (
    <>
      {/* Dialogue — Teleprompter (left) + Waveform + Ring (right) */}
      <Composition
        id="Podcast-Dialogue"
        component={DialogueVisualizer}
        durationInFrames={FALLBACK_DURATION}
        calculateMetadata={calcAudioDuration}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={{
          vizMode: 'dialogue' as DialogueVizMode,
          title: 'The Vault Will Not Mourn It',
          episode: 'EP 047 · Drift',
          showName: 'SIGNAL',
        }}
      />

      {/* Monologue — Centered ring + bottom caption */}
      <Composition
        id="Podcast-Monologue"
        component={DialogueVisualizer}
        durationInFrames={FALLBACK_DURATION}
        calculateMetadata={calcAudioDuration}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={{
          vizMode: 'monologue' as DialogueVizMode,
          title: 'The Vault Will Not Mourn It',
          episode: 'EP 047 · Drift',
          showName: 'SIGNAL',
        }}
      />
    </>
  );
};

registerRoot(Root);
