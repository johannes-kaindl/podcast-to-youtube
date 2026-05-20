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

// Tail-toggle wiring
document.addEventListener('click', (e) => {
  if (e.target.id !== 'tail-toggle') return;
  const pressed = e.target.getAttribute('aria-pressed') === 'true';
  e.target.setAttribute('aria-pressed', pressed ? 'false' : 'true');
});
