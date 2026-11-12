// Repository facts and Studio-owned task management (FR-1088).
import { store } from './store.js';
import { el } from './ui.js';
import { t, onLang } from './i18n.js';
import { xrefLink } from './xref.js';

const HDR = { 'Content-Type': 'application/json', 'X-EABK-Studio': '1' };
const STATES = ['todo', 'doing', 'done'];
const PAGE_SIZE = 100;
const COLUMNS = {
  files: ['path', 'kind', 'bytes', 'analysis'],
  dependencies: ['name', 'version', 'kind', 'file'],
  history: ['commit', 'date', 'subject'],
  submodules: ['path', 'commit', 'state'],
  issues: ['number', 'title', 'state', 'labels', 'assignees', 'updatedAt', 'url'],
  pulls: ['number', 'title', 'state', 'headRefName', 'author', 'updatedAt', 'url'],
  runs: ['workflowName', 'displayTitle', 'status', 'conclusion', 'headBranch', 'createdAt', 'url'],
  diagnostics: ['path', 'reason'],
};

export function mount(host) {
  const page = el('div', { class: 'page workspace', 'data-testid': 'workspace' });
  host.append(page);
  let title = '', query = '', section = 'files', offset = 0, taskOffset = 0, error = '', busy = false;
  const edits = new Map();
  let repo = store.model.meta.repo, alive = true;

  async function save(payload) {
    if (busy) return;
    const target = repo;
    busy = true; error = ''; render();
    try {
      const response = await fetch('/api/tasks', { method: 'POST', headers: HDR, body: JSON.stringify({ ...payload, repo: target }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || result.error);
      const next = await fetch('/api/model', { cache: 'no-store' });
      const model = await next.json();
      if (!next.ok) throw new Error(model.detail || model.error);
      if (alive && store.model.meta.repo === target && model.meta.repo === target) {
        if (payload.action === 'create') title = '';
        store.load(model);
      }
    } catch (e) {
      if (alive && repo === target) error = String(e.message || e);
    } finally {
      busy = false;
      if (alive) render();
    }
  }

  function refreshRemote() {
    fetch('/api/remote/refresh', { method: 'POST', headers: HDR, body: '{}' })
      .then(() => { if (alive) render(); }).catch(() => {});
  }

  function render() {
    const model = store.model, inv = model.repository || {}, remote = model.remote || { status: 'disabled' };
    const data = { ...inv, issues: remote.issues || [], pulls: remote.pulls || [], runs: remote.runs || [] };
    if (repo !== model.meta.repo) { repo = model.meta.repo; title = ''; query = ''; offset = taskOffset = 0; error = ''; edits.clear(); }
    const summary = Object.entries(inv.counts || {}).map(([kind, count]) => `${t('ws.kind.' + kind)}: ${count}`).join(' · ');
    const input = el('input', { value: title, maxlength: 2000, 'aria-label': t('ws.new'), placeholder: t('ws.new'),
      oninput: (e) => { title = e.target.value; } });
    const filter = el('input', { value: query, 'aria-label': t('ws.filter'), placeholder: t('ws.filter'),
      oninput: (e) => { query = e.target.value; offset = taskOffset = 0; renderLists(); } });
    const tasks = el('div', { 'data-testid': 'workspace-tasks' });
    const inventory = el('div', { 'data-testid': 'workspace-inventory' });
    const taskSummary = el('p', { class: 'sub', 'data-testid': 'task-summary' });
    page.replaceChildren(
      el('h1', {}, t('ws.title')),
      el('p', { class: 'sub' }, model.meta.repo),
      el('p', {}, t('ws.scope')),
      el('p', { 'data-testid': 'inventory-counts' }, summary || t('none')),
      el('p', {}, t('ws.storage'), ' ', el('code', {}, model.meta.taskStorage || '')),
      el('p', { 'data-testid': 'remote-status' }, t('ws.remote'), ' ', t('ws.remote.' + remote.status),
        remote.repo ? [' ', el('code', {}, remote.repo)] : null,
        remote.reason ? ` — ${remote.reason}` : null,
        remote.loading ? ` (${t('ws.loading')})` : null,
        (remote.truncated || []).length ? ` — ${t('ws.truncated', { n: remote.limit, sections: remote.truncated.map((s) => t('ws.' + s)).join(', ') })}` : null,
        Object.entries(remote.errors || {}).map(([s, msg]) => ` — ${t('ws.' + s)}: ${msg}`),
        remote.status !== 'disabled' ? [' ', el('button', { class: 'btn ghost', type: 'button', disabled: !!remote.loading, onclick: refreshRemote }, t('ws.refresh'))] : null),
      el('a', { href: '#/map2d' }, t('nav.map')), ' · ', el('a', { href: '#/source' }, t('nav.source')),
      el('p', {}, filter),
      el('section', { class: 'card' },
        el('h2', {}, t('ws.tasks')),
        el('p', {}, t('ws.tasknote')),
        el('form', { class: 'row', onsubmit: (e) => { e.preventDefault(); save({ action: 'create', title }); } },
          input, el('button', { type: 'submit', class: 'btn', disabled: busy }, t('ws.add'))),
        error ? el('p', { role: 'alert', class: 'warnbox' }, t('ws.failed'), ' ', error) : null,
        taskSummary, tasks),
      el('section', { class: 'card' }, el('h2', {}, t('ws.inventory')),
        el('div', { class: 'row' }, ['files', 'dependencies', 'history', 'submodules', 'issues', 'pulls', 'runs', 'diagnostics'].map((key) =>
          el('button', { class: 'chip', type: 'button', 'aria-pressed': section === key,
            onclick: () => { section = key; offset = 0; render(); } }, t('ws.' + key)))),
        inventory),
      el('section', { class: 'card' }, el('h2', {}, t('ws.unavailable')),
        el('ul', {}, (inv.unavailable || []).map((text) => el('li', {}, text))),
        el('p', {}, t('ws.noguess'))));

    function renderLists() {
      const matches = (model.tasks || []).filter((task) => (task.title + ' ' + task.file).toLowerCase().includes(query.toLowerCase()));
      taskSummary.textContent = STATES.map((state) => `${t('ws.' + state)}: ${matches.filter((task) => task.status === state).length}`).join(' · ');
      taskOffset = Math.min(taskOffset, Math.max(0, Math.floor((matches.length - 1) / PAGE_SIZE) * PAGE_SIZE));
      tasks.replaceChildren(...matches.slice(taskOffset, taskOffset + PAGE_SIZE).map((task) => {
        const status = el('select', { 'aria-label': t('ws.status') + ': ' + task.title, disabled: busy,
          onchange: (e) => save({ action: 'update', id: task.id, status: e.target.value }) },
        STATES.map((state) => el('option', { value: state, selected: state === task.status }, t('ws.' + state))));
        const name = el('input', { value: edits.get(task.id) ?? task.title, maxlength: 2000, 'aria-label': t('ws.name'), disabled: busy,
          oninput: (e) => edits.set(task.id, e.target.value) });
        return el('div', { class: 'workspace-task', 'data-task-id': task.id },
          task.origin === 'studio' ? name : el('span', {}, task.title),
          status,
          task.file ? el('code', {}, `${task.file}:${task.line}`)
            : /^https:\/\//.test(task.url || '') ? el('a', { href: task.url, target: '_blank', rel: 'noopener noreferrer' }, t('ws.github'))
              : el('span', { class: 'badge' }, t('ws.local')),
          task.origin === 'studio' ? el('button', { class: 'btn ghost', disabled: busy,
            onclick: () => save({ action: 'update', id: task.id, title: name.value }) }, t('ws.save')) : null,
          el('button', { class: 'btn ghost', disabled: busy,
            onclick: () => {
              if (task.origin !== 'studio' || window.confirm(t('ws.confirmDelete', { title: task.title }))) {
                save({ action: task.origin === 'studio' ? 'delete' : 'reset', id: task.id });
              }
            } },
          t(task.origin === 'studio' ? 'ws.delete' : 'ws.reset')));
      }));
      if (!matches.length) tasks.append(el('p', {}, t('ws.empty')));
      if (matches.length > PAGE_SIZE) tasks.append(pager(matches.length, taskOffset, true));
      const rows = (data[section] || []).filter((item) => JSON.stringify(item).toLowerCase().includes(query.toLowerCase()));
      offset = Math.min(offset, Math.max(0, Math.floor((rows.length - 1) / PAGE_SIZE) * PAGE_SIZE));
      const columns = COLUMNS[section];
      const cell = (item, key) => {
        const value = item[key];
        if (key === 'path' && store.nodes.has('file:' + value)) return xrefLink('file:' + value, value);
        if (key === 'url' && /^https:\/\//.test(value || '')) return el('a', { href: value, target: '_blank', rel: 'noopener noreferrer' }, t('ws.github'));
        return Array.isArray(value) ? value.join(', ') : String(value ?? '');
      };
      inventory.replaceChildren(
        el('p', {}, t('ws.count', { n: rows.length })),
        el('div', { class: 'table-wrap' }, el('table', {},
          el('thead', {}, el('tr', {}, columns.map((key) => el('th', { scope: 'col' }, t('ws.col.' + key))))),
          el('tbody', {}, rows.slice(offset, offset + PAGE_SIZE).map((item) => el('tr', {}, columns.map((key) =>
            el('td', {}, cell(item, key)))))))),
        pager(rows.length, offset));
    }
    function pager(total, start, taskPage = false) {
      const move = (next) => { if (taskPage) taskOffset = next; else offset = next; renderLists(); };
      return el('div', { class: 'row' },
        el('button', { class: 'btn ghost', disabled: start === 0, onclick: () => move(Math.max(0, start - PAGE_SIZE)) }, t('ws.previous')),
        el('span', {}, `${total ? start + 1 : 0}–${Math.min(start + PAGE_SIZE, total)} / ${total}`),
        el('button', { class: 'btn ghost', disabled: start + PAGE_SIZE >= total, onclick: () => move(start + PAGE_SIZE) }, t('ws.next')));
    }
    renderLists();
  }
  render();
  const offs = [store.on('model', render), onLang(render)];
  return { destroy() { alive = false; offs.forEach((off) => off()); } };
}
