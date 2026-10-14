import { createHash } from 'node:crypto';
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// The visualizer's look is the identity "birds of yore" (mode Kuro), vendored from
// the design house. These checks guard the token file against the drifts that
// went silent before: a variable used but never defined, a font fetched over the
// network, a font file that is referenced but missing.

const SRC = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(SRC, 'styles.css'), 'utf8');

const sourceFiles = (dir: string): string[] =>
  readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = join(dir, e.name);
    if (e.isDirectory()) return sourceFiles(p);
    return /\.tsx?$/.test(e.name) && !e.name.endsWith('.test.ts') ? [p] : [];
  });

const defined = new Set([...css.matchAll(/(--[a-z0-9-]+)\s*:/g)].map((m) => m[1]));

describe('styles.css (birds of yore tokens)', () => {
  it('defines every custom property the components use', () => {
    const used = new Set<string>();
    for (const f of [...sourceFiles(SRC), join(SRC, 'styles.css')]) {
      for (const m of readFileSync(f, 'utf8').matchAll(/var\((--[a-z0-9-]+)/g)) used.add(m[1]);
    }
    expect(used.size).toBeGreaterThan(0);
    const missing = [...used].filter((v) => !defined.has(v)).sort();
    expect(missing).toEqual([]);
  });

  it('makes no network request for fonts', () => {
    expect(css).not.toMatch(/@import/);
    expect(css).not.toMatch(/https?:\/\//);
  });

  it('declares only the identity faces, each from a local file that exists', () => {
    const faces = [...css.matchAll(/@font-face\s*{([^}]*)}/g)].map((m) => m[1]);
    expect(faces.length).toBeGreaterThan(0);
    const families = new Set(faces.map((f) => /font-family:\s*["']([^"']+)["']/.exec(f)?.[1]));
    expect([...families].sort()).toEqual(['EB Garamond', 'JetBrains Mono']);
    for (const f of faces) {
      const url = /url\(["']([^"']+)["']\)/.exec(f)?.[1];
      expect(url, f).toBeTruthy();
      expect(existsSync(join(SRC, url as string)), url).toBe(true);
    }
  });

  it('names no face outside the identity', () => {
    expect(css).not.toMatch(/Inter|Space Grotesk/);
  });

  it('gives every signal a loud expression', () => {
    const quiet = [...defined].filter((v) => /^--signal-[a-z]+$/.test(v));
    expect(quiet.length).toBeGreaterThan(0);
    for (const v of quiet) expect(defined.has(`${v}-laut`), `${v}-laut`).toBe(true);
  });
});

describe('design/ (vendored from _design)', () => {
  it('holds every vendored file byte-identical to its recorded hash', () => {
    const vendor = JSON.parse(readFileSync(join(SRC, 'design', 'VENDOR.json'), 'utf8'));
    const entries = Object.entries(vendor.files as Record<string, { sha256: string }>);
    expect(entries.length).toBeGreaterThan(0);
    for (const [path, { sha256 }] of entries) {
      const actual = createHash('sha256')
        .update(readFileSync(join(SRC, 'design', path)))
        .digest('hex');
      expect(actual, path).toBe(sha256);
    }
  });
});
