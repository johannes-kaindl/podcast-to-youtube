// SSE listener + HTMX-OOB swaps for phase/progress fragments

function startEventSource(stem) {
  const url = `/runs/${stem}/stream`;
  const es = new EventSource(url);
  const logEl = document.getElementById('log');

  es.addEventListener('log', (e) => {
    const data = JSON.parse(e.data);
    if (!logEl) return;
    const row = document.createElement('div');
    row.className = `row ${data.level || ''}`;
    const mark = document.createElement('span');
    mark.className = 'mark';
    mark.textContent = '·';
    const msg = document.createElement('span');
    msg.className = 'msg';
    msg.textContent = data.msg;
    row.appendChild(mark);
    row.appendChild(msg);
    logEl.appendChild(row);
    const tail = document.getElementById('tail-toggle');
    if (!tail || tail.getAttribute('aria-pressed') === 'true') {
      logEl.scrollTop = logEl.scrollHeight;
    }
  });

  es.addEventListener('phase', (e) => {
    if (window.htmx) {
      htmx.ajax('GET', `/runs/${stem}/phases`, { target: '[data-phases-wrapper]', swap: 'outerHTML' });
    }
  });

  es.addEventListener('progress', (e) => {
    const data = JSON.parse(e.data);
    const params = new URLSearchParams({
      value: String(Math.round(data.value)),
      label: data.label || '',
    });
    if (window.htmx) {
      htmx.ajax('GET', `/runs/${stem}/progress?${params}`, { target: '#progress', swap: 'outerHTML' });
    }
  });

  es.addEventListener('done', (e) => {
    es.close();
    // Full reload of the detail page — variant switches based on run-state.json
    window.location.href = `/runs/${stem}`;
  });
}

window.startEventSource = startEventSource;

// Elapsed-timer for an active run — ticks from the run's started_at.
function startElapsedTimer(startedAtIso) {
  const el = document.getElementById('elapsed');
  if (!el || !startedAtIso) return;
  const start = new Date(startedAtIso).getTime();
  if (Number.isNaN(start)) return;
  const pad = (n) => String(n).padStart(2, '0');
  const tick = () => {
    const s = Math.max(0, Math.floor((Date.now() - start) / 1000));
    el.textContent = `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
  };
  tick();
  setInterval(tick, 1000);
}

window.startElapsedTimer = startElapsedTimer;

// Tail-toggle wiring
document.addEventListener('click', (e) => {
  if (e.target.id !== 'tail-toggle') return;
  const pressed = e.target.getAttribute('aria-pressed') === 'true';
  e.target.setAttribute('aria-pressed', pressed ? 'false' : 'true');
});

// Audio-path probe + start-button enable

async function probeAudio(path) {
  if (!path.trim()) return null;
  try {
    const r = await fetch('/api/audio/probe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path }),
    });
    return await r.json();
  } catch (e) {
    return { valid: false, error: 'network' };
  }
}

function updateResumeBanner(stem, resumeState) {
  const slot = document.getElementById('resume-banner-slot');
  if (!slot) return;
  if (!resumeState || !stem) { slot.innerHTML = ''; return; }
  fetch(`/runs/${stem}/resume-banner`)
    .then(r => r.ok ? r.text() : '')
    .then(html => { slot.innerHTML = html; });
}

function updateEtaBlock(eta, diskFree) {
  const totalEl = document.getElementById('eta-total');
  const diskEl = document.getElementById('disk-free');
  if (totalEl && eta) totalEl.textContent = `~ ${Math.round(eta.total / 60)} min`;
  if (diskEl && diskFree) diskEl.textContent = `${(diskFree / 1e9).toFixed(0)} GB`;
}

function setStartEnabled(enabled) {
  const btn = document.getElementById('start-btn');
  if (btn) btn.disabled = !enabled;
}

document.addEventListener('input', async (e) => {
  if (e.target.id !== 'audio-path') return;
  const path = e.target.value.trim();
  if (!path) {
    setStartEnabled(false);
    updateResumeBanner(null, null);
    return;
  }
  const probe = await probeAudio(path);
  const errEl = document.getElementById('audio-error');
  if (!probe || !probe.valid) {
    if (errEl) {
      errEl.textContent = probe?.error === 'file_not_found' ? '✗ File not found.'
                         : probe?.error === 'format_unsupported' ? '✗ Format not supported (use .m4a, .mp3, .wav).'
                         : '✗ Audio check failed.';
      errEl.hidden = false;
    }
    setStartEnabled(false);
    return;
  }
  if (errEl) errEl.hidden = true;
  updateResumeBanner(probe.stem, probe.resume_state);
  updateEtaBlock(probe.eta_estimate_s, probe.disk_free_bytes);
  setStartEnabled(true);
  window.__lastProbe = probe;
});

// Modal open / close + run submission
document.addEventListener('click', (e) => {
  const openTrigger = e.target.closest('[data-open-modal]');
  if (openTrigger) {
    const id = `modal-${openTrigger.dataset.openModal}`;
    document.getElementById(id)?.removeAttribute('hidden');
  }
  if (e.target.closest('[data-close-modal]')) {
    e.target.closest('.modal-backdrop')?.setAttribute('hidden', '');
  }
  if (e.target.id === 'start-btn' || e.target.closest('#start-btn')) {
    openConfirmModal();
  }
  if (e.target.id === 'confirm-start' || e.target.closest('#confirm-start')) {
    submitRun();
  }
});

function openConfirmModal() {
  const probe = window.__lastProbe;
  if (!probe) return;
  const titleEl = document.getElementById('confirm-modal-title');
  if (titleEl) titleEl.textContent = `Start pipeline · ${probe.stem}`;
  const willList = document.getElementById('confirm-will-list');
  const eta = probe.eta_estimate_s;
  const phases = [
    { name: 'Transcribe', t: Math.round(eta.transcribe), skip: false },
    { name: 'Metadata',   t: Math.round(eta.meta),       skip: false },
    { name: 'Render',     t: Math.round(eta.render),     skip: false },
    { name: 'Upload',     t: Math.round(eta.upload),     skip: document.querySelector('input[name="skip_upload"]')?.checked ?? true },
  ];
  if (willList) {
    willList.innerHTML = phases.map(p => `
      <div class="row" data-state="${p.skip ? 'skip' : ''}">
        <span class="mark">${p.skip ? '·' : '▶'}</span>
        <span class="label">${p.name}</span>
        <span class="est">~ ${Math.floor(p.t/60)}:${String(p.t%60).padStart(2,'0')}</span>
      </div>`).join('');
  }
  const totalNonSkipped = phases.filter(p => !p.skip).reduce((s,p) => s + p.t, 0);
  const etaEl = document.getElementById('confirm-eta-block');
  if (etaEl) {
    etaEl.innerHTML = `<span class="eta-item"><span>Total est.</span><span class="v">~ ${Math.round(totalNonSkipped/60)} min</span></span>`;
  }
  document.getElementById('modal-confirm-run')?.removeAttribute('hidden');
}

async function submitRun() {
  const form = document.getElementById('config-form');
  if (!form) return;
  const audio = document.getElementById('audio-path').value.trim();
  const body = {
    audio,
    viz: form.viz.value,
    language: form.language.value,
    model: form.model.value,
    diarize: form.querySelector('input[name="diarize"]:checked').value,
    episode: form.episode.value || 'EP 01',
    show_name: form.show_name.value || 'Signal',
    skip_transcribe: form.skip_transcribe.checked,
    skip_meta: form.skip_meta.checked,
    skip_render: form.skip_render.checked,
    skip_upload: form.skip_upload.checked,
    pause_after_transcribe: form.pause_after_transcribe.checked,
  };
  const r = await fetch('/api/runs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    redirect: 'manual',
  });
  if (r.status === 303 || r.type === 'opaqueredirect' || r.redirected) {
    window.location.href = `/runs/${window.__lastProbe.stem}`;
  } else if (r.status === 409) {
    const data = await r.json();
    const otherStem = data?.detail?.stem || 'another run';
    alert(`Slot is busy with ${otherStem}`);
  } else {
    alert(`Start failed: ${r.status}`);
  }
}

// Native macOS file-picker via /api/audio/pick (osascript-backed)
document.addEventListener('click', async (e) => {
  if (!e.target.closest('#pick-audio-btn')) return;
  try {
    const r = await fetch('/api/audio/pick', { method: 'POST' });
    if (!r.ok) { alert(`File-Picker fehlgeschlagen: ${r.status}`); return; }
    const data = await r.json();
    if (data.cancelled) return;
    if (data.path) {
      const input = document.getElementById('audio-path');
      if (input) {
        input.value = data.path;
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
  } catch (err) {
    alert(`File-Picker Fehler: ${err}`);
  }
});

// Keyboard shortcut Ctrl+R / Cmd+R → open confirm modal
document.addEventListener('keydown', (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'r') {
    const startBtn = document.getElementById('start-btn');
    if (startBtn && !startBtn.disabled) {
      e.preventDefault();
      openConfirmModal();
    }
  }
});

document.addEventListener('click', async (e) => {
  if (e.target.id === 'upload-btn' || e.target.closest('#upload-btn')) {
    const privacy = document.querySelector('#upload-privacy input:checked')?.value || 'private';
    const stem = window.location.pathname.split('/').pop();
    const r = await fetch(`/runs/${stem}/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ privacy }),
    });
    if (r.ok) {
      if (window.startEventSource) window.startEventSource(stem);
    } else {
      alert(`Upload failed: ${r.status}`);
    }
  }
  if (e.target.id === 'skip-upload-btn' || e.target.closest('#skip-upload-btn')) {
    const stem = window.location.pathname.split('/').pop();
    await fetch(`/runs/${stem}/skip-upload`, { method: 'POST' });
    window.location.reload();
  }
});

document.addEventListener('click', async (e) => {
  if (e.target.closest('#theme-toggle')) {
    const html = document.documentElement;
    const next = html.dataset.theme === 'dark' ? 'light' : 'dark';
    html.dataset.theme = next;
    localStorage.setItem('theme', next);
    const icon = document.getElementById('theme-icon');
    if (icon) icon.textContent = next === 'dark' ? '☾' : '☀';
    fetch('/api/settings', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ theme: next }),
    });
  }
});

// Editor keyboard shortcuts (only on /runs/<stem>/edit pages).
// Ctrl/Cmd+Z → undo last edit (form POST /edit/undo)
// Ctrl/Cmd+S → save & return (submit main edit form)
// Active text inputs/textareas keep native browser behavior — we don't intercept there.
document.addEventListener('keydown', (e) => {
  const editFormMatch = window.location.pathname.match(/^\/runs\/([^/]+)\/edit$/);
  if (!editFormMatch) return;
  const stem = editFormMatch[1];
  const mod = e.ctrlKey || e.metaKey;
  if (!mod) return;
  const inField = ['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName);

  if (e.key.toLowerCase() === 'z' && !e.shiftKey) {
    if (inField) return; // native field-undo wins
    e.preventDefault();
    const f = document.createElement('form');
    f.method = 'post';
    f.action = `/runs/${stem}/edit/undo`;
    document.body.appendChild(f);
    f.submit();
  } else if (e.key.toLowerCase() === 's') {
    e.preventDefault();
    const form = document.getElementById('edit-form');
    if (form) {
      const btn = form.querySelector('button[value="save-return"]');
      if (btn) btn.click();
      else form.submit();
    }
  }
});
