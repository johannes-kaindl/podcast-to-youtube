/* =========================================================================
 * Whisper-Pipeline · Tweaks panel + small mockup helpers
 * Vanilla JS, separate from product code.
 * ========================================================================= */
(function () {
  const STORAGE_KEY = 'wp-tweaks';
  const DEFAULTS = /*EDITMODE-BEGIN*/{
    "aspect": "gunshi",
    "phases": "stepper",
    "theme": "dark",
    "grain": false,
    "tail": true
  }/*EDITMODE-END*/;

  let state = { ...DEFAULTS };
  try { state = { ...state, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') }; } catch (e) {}

  // ─── APPLY STATE ──────────────────────────────────────────────────────
  function apply() {
    document.documentElement.setAttribute('data-aspect', state.aspect);
    document.documentElement.setAttribute('data-theme', state.theme);
    document.body.setAttribute('data-grain', state.grain ? 'on' : 'off');

    // Phase indicator variant
    document.querySelectorAll('[data-phases-wrapper]').forEach(w => {
      w.querySelectorAll('[data-phases-variant]').forEach(v => {
        v.hidden = v.getAttribute('data-phases-variant') !== state.phases;
      });
    });

    // Tail-auto-scroll toggle reflection (purely visual)
    document.querySelectorAll('.tail').forEach(t => {
      t.setAttribute('aria-pressed', state.tail ? 'true' : 'false');
    });
  }

  function persist() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
    try { window.parent.postMessage({ type: '__edit_mode_set_keys', edits: state }, '*'); } catch (e) {}
  }

  // ─── WAVEFORM BUILDER ────────────────────────────────────────────────
  // Procedural pseudo-random bars based on a seed, so static markup
  // gets a credible waveform without huge SVG payloads.
  function mulberry(seed) {
    let t = seed >>> 0;
    return function () {
      t = (t + 0x6D2B79F5) >>> 0;
      let x = t;
      x = Math.imul(x ^ (x >>> 15), x | 1);
      x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
      return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
    };
  }
  function buildWaveform(el) {
    const bars = parseInt(el.dataset.bars || '32', 10);
    const seed = parseInt(el.dataset.seed || '1', 10);
    const variant = el.dataset.waveform || 'default';
    const rand = mulberry(seed);

    // Bias the curve so it looks like real audio (envelope-ish):
    // ramp up at start, fluctuate, fade at end.
    function envelope(i) {
      const t = i / (bars - 1);
      const ramp = Math.min(1, t / 0.12);
      const fade = Math.min(1, (1 - t) / 0.08);
      return ramp * fade;
    }

    el.classList.add('waveform');
    el.innerHTML = '';
    for (let i = 0; i < bars; i++) {
      const noise = 0.35 + rand() * 0.65;        // 0.35–1.0
      const env = envelope(i);
      const h = Math.max(2, Math.round(noise * env * 28));
      const bar = document.createElement('span');
      bar.className = 'bar';
      bar.style.height = h + 'px';
      el.appendChild(bar);
    }

    // Variant-specific tone
    if (variant === 'muted') el.classList.add('muted');
  }
  function buildAllWaveforms() {
    document.querySelectorAll('[data-waveform]').forEach(buildWaveform);
  }

  // ─── TAIL TOGGLE (per-page wireup) ───────────────────────────────────
  function wireTailToggles() {
    document.querySelectorAll('.tail').forEach(t => {
      if (t.dataset.bound) return;
      t.dataset.bound = '1';
      t.addEventListener('click', () => {
        state.tail = t.getAttribute('aria-pressed') !== 'true';
        apply(); persist();
      });
    });
  }

  // ─── PANEL ───────────────────────────────────────────────────────────
  function buildPanel() {
    const root = document.createElement('div');
    root.id = 'tweaks-root';
    root.style.display = 'none';
    root.innerHTML = `
      <div class="tweaks-panel" role="dialog" aria-label="Tweaks">
        <div class="tweaks-head">
          <span>⌬</span><span>Tweaks</span>
          <button class="close" aria-label="Close">✕</button>
        </div>
        <div class="tweaks-body">
          <div class="tweaks-row">
            <div class="tweaks-label">Aspect · accent</div>
            <div class="swatches" data-control="aspect">
              <div class="swatch" data-value="gunshi"  title="Strategist · Spectre"  style="background:#a878ff"></div>
              <div class="swatch" data-value="shugo"   title="Guardian · Phosphor"   style="background:#39ff7a"></div>
              <div class="swatch" data-value="kantoku" title="Taskmaster · Crimson"  style="background:#d4203a"></div>
              <div class="swatch" data-value="sensei"  title="Mentor · Ember"        style="background:#ffb442"></div>
            </div>
          </div>

          <div class="tweaks-row">
            <div class="tweaks-label">Theme</div>
            <div class="segmented" data-control="theme">
              <button class="opt" data-value="dark">Dark</button>
              <button class="opt" data-value="light">Light</button>
            </div>
          </div>

          <div class="tweaks-row">
            <div class="tweaks-label">Phase indicator</div>
            <div class="segmented" data-control="phases">
              <button class="opt" data-value="stepper">Stepper</button>
              <button class="opt" data-value="subway">Subway</button>
              <button class="opt" data-value="cards">Cards</button>
            </div>
          </div>

          <div class="tweaks-row">
            <div class="toggle">
              <span>Grain overlay</span>
              <div class="switch" data-control="grain" role="switch" tabindex="0"></div>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(root);

    function sync() {
      root.querySelectorAll('[data-control="aspect"] .swatch').forEach(el => el.setAttribute('aria-pressed', el.dataset.value === state.aspect ? 'true' : 'false'));
      root.querySelectorAll('[data-control="theme"] .opt').forEach(el => el.setAttribute('aria-pressed', el.dataset.value === state.theme ? 'true' : 'false'));
      root.querySelectorAll('[data-control="phases"] .opt').forEach(el => el.setAttribute('aria-pressed', el.dataset.value === state.phases ? 'true' : 'false'));
      root.querySelector('[data-control="grain"]').setAttribute('aria-pressed', state.grain ? 'true' : 'false');
    }
    sync();

    root.addEventListener('click', (e) => {
      const swatch = e.target.closest('[data-control="aspect"] .swatch');
      if (swatch) { state.aspect = swatch.dataset.value; apply(); persist(); sync(); return; }
      const theme = e.target.closest('[data-control="theme"] .opt');
      if (theme) { state.theme = theme.dataset.value; apply(); persist(); sync(); return; }
      const opt = e.target.closest('[data-control="phases"] .opt');
      if (opt) { state.phases = opt.dataset.value; apply(); persist(); sync(); return; }
      const grain = e.target.closest('[data-control="grain"]');
      if (grain) { state.grain = !state.grain; apply(); persist(); sync(); return; }
      if (e.target.closest('.close')) { hide(); return; }
    });

    return root;
  }

  let panel = null;
  function show() {
    if (!panel) panel = buildPanel();
    panel.style.display = 'block';
  }
  function hide() {
    if (panel) panel.style.display = 'none';
    try { window.parent.postMessage({ type: '__edit_mode_dismissed' }, '*'); } catch (e) {}
  }

  // ─── MODAL HELPERS (cheatsheet auto-injects on every page) ──────────
  function injectCheatsheet() {
    if (document.getElementById('modal-cheatsheet')) return;
    const html = `
      <div class="modal-backdrop" id="modal-cheatsheet" hidden>
        <div class="modal modal--wide" role="dialog" aria-modal="true">
          <header class="modal-head">
            <span class="caps">Keyboard · whisper-pipeline</span>
            <button class="close" type="button" data-close-modal aria-label="Close">✕</button>
          </header>
          <div class="modal-body">
            <h2 class="modal-title">The chamber listens to keys.</h2>
            <div class="kbd-list">
              <div class="group">
                <h4>Global</h4>
                <div class="item"><span>Show this cheatsheet</span><span class="keys"><kbd>?</kbd></span></div>
                <div class="item"><span>Focus search</span><span class="keys"><kbd>/</kbd></span></div>
                <div class="item"><span>Go to start</span><span class="keys"><kbd>g</kbd><kbd>s</kbd></span></div>
                <div class="item"><span>Go to runs</span><span class="keys"><kbd>g</kbd><kbd>r</kbd></span></div>
                <div class="item"><span>Close modal / cancel</span><span class="keys"><kbd>Esc</kbd></span></div>
              </div>
              <div class="group">
                <h4>On start</h4>
                <div class="item"><span>Start pipeline</span><span class="keys"><kbd>Ctrl</kbd><kbd>R</kbd></span></div>
                <div class="item"><span>Drop audio (focus path)</span><span class="keys"><kbd>p</kbd></span></div>
                <div class="item"><span>Toggle skip-render</span><span class="keys"><kbd>s</kbd><kbd>r</kbd></span></div>
                <div class="item"><span>Reload resume state</span><span class="keys"><kbd>r</kbd></span></div>
              </div>
              <div class="group">
                <h4>On run-detail</h4>
                <div class="item"><span>Abort current run</span><span class="keys"><kbd>Ctrl</kbd><kbd>.</kbd></span></div>
                <div class="item"><span>Pause auto-scroll (log)</span><span class="keys"><kbd>t</kbd></span></div>
                <div class="item"><span>Copy YouTube URL</span><span class="keys"><kbd>c</kbd><kbd>u</kbd></span></div>
                <div class="item"><span>Open MP4 locally</span><span class="keys"><kbd>o</kbd></span></div>
              </div>
              <div class="group">
                <h4>On runs list</h4>
                <div class="item"><span>Move selection</span><span class="keys"><kbd>↑</kbd><kbd>↓</kbd></span></div>
                <div class="item"><span>Open selected</span><span class="keys"><kbd>↵</kbd></span></div>
                <div class="item"><span>Filter: done / aborted</span><span class="keys"><kbd>f</kbd><kbd>d</kbd> / <kbd>f</kbd><kbd>a</kbd></span></div>
              </div>
            </div>
          </div>
          <footer class="modal-foot">
            <span class="mono dim" style="margin-right:auto; font-size: var(--text-xs); letter-spacing: 0.04em;">All shortcuts also available in palette · <kbd>Ctrl</kbd><kbd>K</kbd></span>
            <button class="btn btn--primary" type="button" data-close-modal>Got it</button>
          </footer>
        </div>
      </div>
    `;
    const div = document.createElement('div');
    div.innerHTML = html;
    document.body.appendChild(div.firstElementChild);
  }
  function wireModals() {
    document.addEventListener('click', (e) => {
      const opener = e.target.closest('[data-open-modal]');
      if (opener) {
        e.preventDefault();
        const id = opener.dataset.openModal;
        const el = document.getElementById('modal-' + id);
        if (el) el.hidden = false;
        return;
      }
      const closer = e.target.closest('[data-close-modal]');
      if (closer) {
        document.querySelectorAll('.modal-backdrop').forEach(m => m.hidden = true);
        return;
      }
      const backdrop = e.target.closest('.modal-backdrop');
      if (backdrop && e.target === backdrop) { backdrop.hidden = true; }
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-backdrop').forEach(m => m.hidden = true);
      }
      if (e.key === '?' && !/^(INPUT|TEXTAREA)$/.test(document.activeElement?.tagName)) {
        e.preventDefault();
        document.querySelectorAll('.modal-backdrop').forEach(m => m.hidden = true);
        const cs = document.getElementById('modal-cheatsheet');
        if (cs) cs.hidden = false;
      }
    });
  }

  // ─── BOOT ────────────────────────────────────────────────────────────
  apply();
  buildAllWaveforms();
  wireTailToggles();
  injectCheatsheet();
  wireModals();

  window.addEventListener('message', (e) => {
    const data = e.data;
    if (!data || typeof data !== 'object') return;
    if (data.type === '__activate_edit_mode')   show();
    if (data.type === '__deactivate_edit_mode') hide();
  });
  try { window.parent.postMessage({ type: '__edit_mode_available' }, '*'); } catch (e) {}
})();
