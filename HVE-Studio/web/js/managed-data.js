import { t, onLang } from './i18n.js';
import { el } from './ui.js';
import { store } from './store.js';

// FR-1090 AC-489 AC-490 AC-491: always show presence, progress and an explicit cleanup action.
export function initManagedData(reload) {
  const host = document.getElementById('generatedData');
  const title = el('strong', { id: 'generatedDataTitle' });
  const presence = el('span', { 'data-testid': 'data-presence' });
  const path = el('code', { class: 'generated-data-path', 'data-testid': 'data-path' });
  const note = el('span', { class: 'mini' });
  const progress = el('progress', { max: 1, value: 0, 'data-testid': 'data-progress' });
  const message = el('span', { role: 'status', 'aria-live': 'polite', 'data-testid': 'data-message' });
  const error = el('span', { role: 'alert', class: 'generated-data-error', 'data-testid': 'data-error' });
  const sync = el('button', { type: 'button', class: 'chip', 'data-testid': 'data-sync', onclick: () => run('sync') });
  const remove = el('button', { type: 'button', class: 'chip', 'data-testid': 'data-delete', onclick: () => run('delete') });
  host.append(el('div', { class: 'generated-data-summary' }, title, presence, path),
    el('div', { class: 'generated-data-controls' }, sync, remove, progress, message, error), note);
  let state = null, repo = '', failure = '', pending = false, polling = false, handled = '';

  function draw() {
    const data = state?.data || {}, job = state?.operation || {};
    const busy = pending || job.status === 'running';
    const phase = job.progress;
    title.textContent = t('data.title');
    presence.textContent = t('data.' + (data.state || 'unknown'));
    host.dataset.state = data.state || 'unknown';
    path.textContent = data.path || '';
    note.textContent = t('data.note');
    sync.textContent = t('data.sync');
    remove.textContent = t('data.delete');
    sync.disabled = !repo || busy || data.state === 'conflict';
    remove.disabled = !repo || busy || !data.exists || data.state === 'conflict';
    progress.hidden = !busy;
    progress.setAttribute('aria-label', t('data.progress'));
    progress.max = Math.max(1, phase?.total || 1);
    progress.value = phase?.completed || 0;
    message.textContent = busy
      ? t('data.phase.' + (phase?.phase || 'prepare')) + ` ${phase?.completed || 0}/${phase?.total || 1}`
      : job.status === 'done' ? t('data.done.' + job.action) : '';
    message.title = phase?.detail || '';
    error.textContent = failure || job.error || data.error || '';
    error.hidden = !error.textContent;
  }

  async function poll() {
    if (!repo || polling) return;
    const requested = repo;
    polling = true;
    try {
      const response = await fetch('/api/data', { cache: 'no-store' });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || body.error || 'HTTP ' + response.status);
      if (repo !== requested || body.repo !== repo) return;
      state = body;
      failure = '';
      draw();
      const job = body.operation;
      if (job?.id && job.id !== handled && job.status === 'done') {
        handled = job.id;
        await reload();
      }
    } catch (e) {
      if (repo === requested) { failure = String(e.message || e); draw(); }
    } finally {
      polling = false;
    }
  }

  async function run(action) {
    const requested = repo;
    if (action === 'delete' && !window.confirm(t('data.confirm', { path: state?.data?.path || '' }))) return;
    pending = true;
    failure = '';
    draw();
    try {
      const response = await fetch('/api/data/' + action, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-EABK-Studio': '1' },
        body: JSON.stringify({ repo: requested, confirm: action === 'delete' }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || body.error || 'HTTP ' + response.status);
      if (repo !== requested) return;
      state.operation = { status: 'running', action, progress: { phase: 'prepare', completed: 0, total: 1 } };
    } catch (e) {
      if (repo === requested) failure = String(e.message || e);
    } finally {
      pending = false;
      draw();
    }
    await poll();
  }

  store.on('model', () => {
    const next = store.model.meta.repo;
    if (next !== repo) {
      repo = next;
      failure = '';
      handled = '';
      state = { repo, data: store.model.meta.generatedData, operation: {} };
    } else {
      state.data = store.model.meta.generatedData;
    }
    draw();
    poll();
  });
  onLang(draw);
  draw();
  const tick = async () => {
    if (!document.hidden) await poll();
    setTimeout(tick, pending || state?.operation?.status === 'running' ? 250 : 4000);
  };
  setTimeout(tick, 1000);
}
