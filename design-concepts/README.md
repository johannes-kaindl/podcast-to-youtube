# Whisper-Pipeline · WebGUI Mockups

Static HTML/CSS mockups for the FastAPI + Jinja2 + HTMX rebuild of the Whisper-Pipeline TUI. Built on the **Kuro Signal Protocol** design system, **Strategist** aspect (Spectre `#a878ff` — same violet the Textual TUI uses today).

## Files

| File | What |
|---|---|
| `index.html` | Start / configuration screen. Idle drag-drop by default, full set of alternate states (hover, filled-with-waveform, two error variants), resume banners (all three variants), config form, run trigger with pre-flight ETA, confirm-run modal. |
| `run_detail--running.html` | Live state · phase 3 in progress. Live log streaming with tail toggle, transcript + metadata previews populated. |
| `run_detail--ready-to-upload.html` | **Trust moment** · phases 1–3 done, render previewable, upload-trigger card prominent with privacy choice. The user must actively confirm. |
| `run_detail--done.html` | Terminal success · all four phases done, MP4 preview, YouTube URL. |
| `run_detail--aborted.html` | Render aborted at frame 4 580. Error card with last 10 stderr lines, resume hint. |
| `runs.html` | Past runs — dense table with waveform thumbs (procedurally generated, seeded per row) + empty state. |
| `compare.html` | 2 × 2 grid of run-detail states + coverage checklist. |
| `style.css` | Single stylesheet — tokens + components, dark + light themes. |
| `tweaks.js` | Mockup-only overlay. Hosts the tweaks panel, waveform builder, modal infrastructure, keyboard-shortcut hooks. Not part of the production code. |

All five product screens share the same topbar/nav and a consistent grid (`max-width: 1180px`, 8-pt spacing). Mockups are sized for desktop browser windows ≥ 1200 px wide — mobile is out of V1 scope per the brief. Hit <kbd>?</kbd> on any page for the keyboard cheatsheet.

## Run-detail state machine

The four `run_detail--*.html` files trace one episode through the pipeline:

```
  running  ───done──→  ready-to-upload  ──upload─→  done
     │                       │
     └──failure───────────────┐
                          aborted
```

The **ready-to-upload** state is where the user controls the trust hand-off: the rendered MP4 is previewable, but no upload happens until they pick a privacy setting and click the upload button. Public is disabled at the application level.

## Tweaks (review only)

Toggle the **Tweaks** button in the toolbar to swap:

- **Aspect / accent** — Strategist (Spectre, default) · Guardian (Phosphor) · Taskmaster (Crimson) · Mentor (Ember).
- **Theme** — dark (default) / light. Light mode flips the void scale to a warm parchment palette and damps the signal colours so they hold up against the lighter ground.
- **Phase indicator** — Stepper (default) · Subway · Cards. All three are rendered server-side; the panel toggles visibility so a reviewer can pick the variant before it's baked into the Jinja template.
- **Grain overlay** — adds a faint SVG-noise layer over the vault ground.

The panel is implemented in `tweaks.js` as a vanilla-JS overlay and is intentionally separate from the page CSS so the eventual Jinja templates can drop it without touching the design.

`tweaks.js` also handles:
- **Waveform generation** — every `[data-waveform data-bars=N data-seed=K]` element gets a credible audio-shaped bar pattern via a seeded PRNG. Use this anywhere the design needs a stand-in for real-audio peaks.
- **Modal wiring** — `[data-open-modal="..."]` opens the modal with `id="modal-..."`, `[data-close-modal]` closes any open modal. <kbd>Esc</kbd> closes; <kbd>?</kbd> opens the cheatsheet.
- **Tail toggle** — the `Tail` pill in the log-panel header reflects the auto-scroll preference.

---

## Design tokens

All tokens live as CSS Custom Properties on `:root` in `style.css`. The four aspect overrides live on `[data-aspect="…"]`. Same naming conventions Kuro Signal Protocol uses, so the values port to the broader system one-for-one.

### Colour — signals (semantic)

| Token | Hex | Used for |
|---|---|---|
| `--accent` | `#a878ff` Spectre · default | Primary buttons, link underlines, running-phase glyphs, focus ring |
| `--role-success` | `#39ff7a` Phosphor | Done phase, success log line, valid form state, uploaded badge |
| `--role-error` | `#d4203a` Crimson | Aborted phase, error log line, error banner, destructive button |
| `--role-warning` | `#ffb442` Ember | Aborted-resume banner, warn log line |
| `--role-info` | `#7ab8c4` Ghost | In-progress resume banner, info log line |
| `--role-link` | `#4ac8d8` Circuit | YouTube URLs, generic inline links |

Aspect overrides (set on `<html data-aspect="…">`):

| `data-aspect` | Accent |
|---|---|
| `shugo` (Guardian) | Phosphor `#39ff7a` |
| `gunshi` (Strategist) — default | Spectre `#a878ff` |
| `kantoku` (Taskmaster) | Crimson `#d4203a` |
| `sensei` (Mentor) | Ember `#ffb442` |

### Colour — surfaces (void scale)

| Token | Hex | Role |
|---|---|---|
| `--surface-vault` | `#060709` | Page ground |
| `--surface-primary` | `#0b0d11` | Topbar, table-header rows |
| `--surface-raised` | `#11141a` | Cards, dropzone, banner |
| `--surface-overlay` | `#181c24` | Modals, popovers, tweaks panel |
| `--surface-inset` | `#04050780` | Inputs, code blocks, log panel body |
| `--border-subtle` | `#22272f` | Hairlines on cards, table rows |
| `--border-default` | `#2e343d` | Input borders, button outlines |
| `--border-strong` | `#3d4450` | Hover-promoted borders |
| `--fg-primary` | `#e8e4d8` Pearl | Body text |
| `--fg-secondary` | `#828a97` | Captions, mono meta lines |
| `--fg-tertiary` | `#5a6170` | Eyebrows, disabled labels |
| `--fg-disabled` | `#3d4450` | Skipped phase glyph |

### Type

| Family | Token | Used for |
|---|---|---|
| **EB Garamond** *italic* | `--font-serif` | **H1** — page titles, episode/run stems, YouTube titles, empty-state titles. Subtle accent-coloured `text-shadow` glow per the Kuro vault convention. |
| Space Grotesk | `--font-display` | H2/H3/H4, phase names, dropzone label, utility display |
| Inter | `--font-body` | Body, form labels, transcript |
| JetBrains Mono | `--font-mono` | Log panel, eyebrows, timestamps, kbd, code, kv lists, status pills |

Scale (`--text-xs … --text-3xl`): 11 · 13 · 15 · 17 · 20 · 24 · 32 · 44 px. Letter-spacing: serif h1 `-0.01em`, display h2/h3 `-0.02em`, mono caps `0.12em`.

### Spacing · radii · motion

| Group | Tokens |
|---|---|
| Spacing | `--space-1…8`: 4 · 8 · 12 · 16 · 24 · 32 · 48 · 64 px (4-base) |
| Radii | `--radius-sm` 3 · `--radius-md` 6 · `--radius-lg` 10 · `--radius-xl` 14 · `--radius-full` 999 |
| Easing | `--ease-signal` decisive arrival, long release · `--ease-pulse` warnings only |
| Duration | `--dur-fast` 120 ms · `--dur-base` 200 ms · `--dur-slow` 360 ms |

### Component classes (jinja-friendly)

The brief asks for class-based components, not web components. Key classes:

- `.btn` · `.btn--primary` · `.btn--ghost` · `.btn--danger` · `.btn--sm` · `.btn--lg`
- `.input` · `.select` · `.check` · `.segmented` (with `<input type="radio">` children) · `.field` · `.field-label`
  - `<input class="input" data-state="valid|error">` for inline validation feedback (paired with `.field-valid` / `.field-error` text)
- `.card` · `.card--padded` · `.card--inset` with `data-tone="success|warning|error|accent"` for the top-border treatment
- `.banner[data-variant="aborted|complete|inprogress"]`
- `.dropzone[data-state="idle|hover|filled"]`
- `.phases--stepper` · `.phases--subway` · `.phases--cards` · `.phases--compact` — each containing `.phase[data-status="pending|running|done|aborted|skipped"]`
- `.progress` with `.progress-fill[data-state="done|aborted"]`
- `.logpanel` · `.logpanel-head` · `.logpanel-body` — log rows use `.row.success|warn|error|info|phase` for line styling. `.tail[aria-pressed]` toggles auto-scroll-to-bottom.
- `.runs-row` (dense table) · `.runs-row.is-header` · `.thumb.wave` for rendered runs, `.thumb.empty` for unrendered
- `.pill[data-tone="…"]` for status badges
- `.transcript .line[data-spk="a|b"]` for two-speaker colouring
- `.meta-title` · `.meta-desc` · `.tags > .tag` · `.chapters > .chapter`
- `.modal-backdrop` · `.modal` · `.modal-head` · `.modal-body` · `.modal-foot` · `.modal-title`. Open with `data-open-modal="<id>"` targeting `#modal-<id>`; close with `data-close-modal`.
- `.will-list` for the confirm-run "this will happen" preview; `.kbd-list` for keyboard cheatsheets
- `.eta-block` for inline pre-flight metadata (time / size / disk)
- `[data-waveform data-bars=N data-seed=K]` for procedural waveform thumbnails

### HTMX hooks (suggestions for the Jinja port)

The mockups don't bind anything, but they expose the obvious swap targets:

- `#log` on every `run_detail` — SSE-tail target; rows are append-only.
- `[data-phases-wrapper]` — full strip, swap with `hx-swap-oob` on phase change.
- `.progress` — overall progress fragment.
- `.banner` + the form inside `index.html` — swap together when audio path changes (server re-derives stem and resume state).
- Run-list rows are anchor tags (`<a class="runs-row" href="run_detail.html">`) — drop in an `hx-boost` on the container for SPA-feel navigation.

### Production notes

- **Fonts** — `style.css` imports EB Garamond, Space Grotesk, Inter, JetBrains Mono from Google Fonts for the mockup phase. Vendor `*.woff2` files into `static/fonts/` for production and replace the `@import` with `@font-face` declarations.
- **Light mode** — wired via `[data-theme="light"]` on `<html>`. The tweaks panel flips it for review; for production, default to dark and respect `prefers-color-scheme` with a simple `<script>` that sets the attribute on first paint.
- **No JS framework** — `tweaks.js` is the only JS file. The Jinja port can drop it entirely; the small inline scripts (timer tick on `run_detail--running.html`, modal triggers) are HTMX-replaceable.
- **Reduced motion** — the running-phase pulse, scan-line animation, and live-log cursor blink should be wrapped in `@media (prefers-reduced-motion: reduce)` once locked in.

---

## Out of scope (per brief §9)

Transcript editor · job queue / multi-audio · auth · multi-user · remote access · tag/category management. None of these are reflected in the mockups.
