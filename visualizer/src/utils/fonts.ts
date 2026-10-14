import { useEffect, useState } from 'react';
import { cancelRender, continueRender, delayRender } from 'remotion';

// The four faces declared in styles.css (vendored from _design, birds of yore).
export const FONT_FACES = [
  '400 16px "JetBrains Mono"',
  'italic 400 16px "JetBrains Mono"',
  '400 16px "EB Garamond"',
  'italic 400 16px "EB Garamond"',
];

/**
 * Hold frame 0 until the local faces are loaded. Without this the renderer
 * may grab the first frames before the woff2 files arrive, and text falls
 * back to Menlo/Georgia without a sound. A face that resolves to nothing
 * (wrong family name, missing file) aborts the render instead of shipping
 * a video in the fallback stack.
 */
export const useFontsReady = (): void => {
  const [handle] = useState(() => delayRender('Loading identity fonts'));

  useEffect(() => {
    Promise.all(FONT_FACES.map((spec) => document.fonts.load(spec)))
      .then((loaded) => {
        const missing = FONT_FACES.filter((_, i) => loaded[i].length === 0);
        if (missing.length) throw new Error(`Fonts not loaded: ${missing.join(', ')}`);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [handle]);
};
