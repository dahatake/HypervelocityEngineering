// FR-1099 (repository group) and FR-1100 (relations between its repositories).
// The header keeps FR-010's button (switch = replace the group with one repository); beside it, the "Repository list"
// button opens the group with each one's state, where a repository is added (same OS folder dialog) or removed.
// Only the list of paths is kept in the browser (localStorage `hve-studio.repos`) and restored on the next start.
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, icon, toast, vscodeUrl } from './ui.js';
import { xrefLink } from './xref.js';
import { sourceTabs } from './srctabs.js';

const KEY = 'hve-studio.repos';
const HDR = { 'Content-Type': 'application/json', 'X-HVE-Studio': '1' };
export const savePaths = (paths) => { try { localStorage.setItem(KEY, JSON.stringify(paths)); } catch { /* the group still applies now */ } };
const savedPaths = () => { try { const v = JSON.parse(localStorage.getItem(KEY) || '[]'); return Array.isArray(v) ? v.map(String) : []; } catch { return []; } };

let reload = async () => {};
let listPanel = null;

async function post(path, body) {
  const res = await fetch(path, { method: 'POST', headers: HDR, body: JSON.stringify(body || {}) });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

const statusText = (r) => t('repos.st.' + r.status) + (r.error ? ' — ' + r.error : '');

function remember(repos) { savePaths(repos.map((r) => r.path)); }

export async function addRepository() {
  const { ok, status, data } = await post('/api/repos/add', {});
  if (status === 501) { toast(t('repo.nopicker')); return; }
  if (data.cancelled) return;   // cancelled: change nothing (AC-536)
  if (!ok) { toast(t('repos.err.' + (data.error || 'bad'), { n: data.limit || 10 })); return; }
  remember(data.repos);
  await reload();
  renderList();
}

async function removeRepository(path) {
  const { ok, data } = await post('/api/repos/remove', { path });
  if (!ok) { toast(t('repos.err.' + (data.error || 'bad'))); return; }
  remember(data.repos);
  store.clear();
  await reload();
  renderList();
}

function renderList() {
  if (!listPanel) return;
  const repos = store.model?.meta?.repos || [];
  listPanel.body.replaceChildren(
    el('table', { class: 't', 'data-testid': 'repo-list' },
      el('thead', {}, el('tr', {}, [t('repos.col.name'), t('repos.col.path'), t('repos.col.mode'), t('repos.col.status'), ''].map((h) => el('th', {}, h)))),
      el('tbody', {}, repos.map((r) => el('tr', { 'data-testid': 'repo-row', 'data-path': r.path, 'data-status': r.status },
        el('td', {}, el('b', {}, r.name), r.primary ? el('small', {}, ' ' + t('repos.primary')) : null),
        el('td', { class: 'mono mini' }, r.path),
        el('td', {}, r.mode ? t('repos.mode.' + r.mode) : '—'),
        el('td', {}, el('span', { 'data-testid': 'repo-status' }, statusText(r)),
          r.status === 'error' ? el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'repo-retry', onclick: () => reload().then(renderList) }, icon('retry', { size: 16 }), t('repos.retry')) : null),
        el('td', {}, repos.length > 1 ? el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'repo-remove', 'aria-label': t('repos.remove.aria', { name: r.name }), onclick: () => removeRepository(r.path) }, icon('close', { size: 16 }), t('repos.remove')) : null))))),
    el('p', { class: 'mini' }, t('repos.limit', { n: repos.length, max: 10 })),
    el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn', 'data-testid': 'repo-add-in-list', onclick: addRepository }, icon('plus', { size: 16 }), t('repos.add')),
      repos.length > 1 ? el('a', { class: 'btn ghost', href: '#/xrepo' }, t('repos.relations')) : null));
}

export function openRepoList() {
  if (listPanel) { listPanel.close(); return; }
  const body = el('div', {});
  const box = el('section', { class: 'repo-panel card', role: 'region', 'aria-labelledby': 'repoPanelH', 'data-testid': 'repo-panel', tabindex: '-1' },
    el('div', { class: 'ai-dialog-head' }, icon('repos', { size: 20 }), el('h2', { id: 'repoPanelH' }, t('repos.title')),
      el('button', { type: 'button', class: 'btn ghost', 'aria-label': t('ai.close'), onclick: () => listPanel?.close() }, icon('close', { size: 16 }))),
    el('p', { class: 'mini' }, t('repos.d')), body);
  const onKey = (e) => { if (e.key === 'Escape' && box.contains(document.activeElement)) listPanel?.close(); };
  const off = onLang(renderList);
  listPanel = { body, close: () => { box.remove(); window.removeEventListener('keydown', onKey); off(); listPanel = null; document.getElementById('repoListBtn')?.focus(); } };
  document.body.append(box);
  window.addEventListener('keydown', onKey);
  renderList();
  box.focus();
}

export function renderRepoListBtn() {
  const b = document.getElementById('repoListBtn');
  if (!b) return;
  const n = store.model?.meta?.repos?.length || 1;
  b.replaceChildren(icon('repos', { size: 16 }), ' ' + t('repos.listBtn'));
  b.setAttribute('aria-label', t('repos.list.aria', { n }));
  b.title = t('repos.list.aria', { n });
  renderList();
}

export function initRepos(reloadModel) {
  reload = reloadModel;
  document.getElementById('repoListBtn').addEventListener('click', openRepoList);
  onLang(renderRepoListBtn);
  store.on('model', renderRepoListBtn);
}

// On start: restore the saved group when it begins with the repository the server opened.
export async function restoreRepos() {
  const saved = savedPaths();
  const cur = store.model?.meta?.repo;
  if (saved.length < 2 || !cur || saved[0].toLowerCase() !== cur.toLowerCase()) return false;
  const have = (store.model.meta.repos || []).length;
  if (have >= saved.length) return false;
  const { ok, data } = await post('/api/repos/restore', { paths: saved });
  if (ok && data.added?.length) { await reload(); return true; }
  return false;
}

// ---------------------------------------------------------------- FR-1100: relations between the repositories
const KIND_ICON = { package: 'component', function: 'source', api: 'api', data: 'tables' };

function codeLink(repoPath, side) {
  const p = repoPath.replace(/\\/g, '/') + '/' + side.file;
  return el('a', { href: vscodeUrl(p, side.line), class: 'mono', title: t('xr.open') }, `${side.repo}:${side.file}:${side.line}`);
}

function reqsFor(side) {
  const id = `${side.repo}:file:${side.file}`;
  const n = store.node(id) || store.node('file:' + side.file);
  if (!n) return [];
  return store.neighbors(n.id, ['req']).map((x) => x.id);
}

export function mount(host) {
  const page = el('div', { class: 'page xrepo-page' });
  host.append(page);
  let data = null, error = null, showCand = false, pickEdge = null, pickRepo = null;
  const render = () => {
    const repos = store.model?.meta?.repos || [];
    const head = [sourceTabs('repos'), el('h1', {}, t('xr.title')), el('p', { class: 'sub' }, t('xr.sub'))];
    if (repos.length < 2) {
      page.replaceChildren(...head, el('div', { class: 'card', 'data-testid': 'xr-single' }, el('p', {}, t('xr.single')),
        el('button', { type: 'button', class: 'btn', onclick: addRepository }, icon('plus', { size: 16 }), t('repos.add'))));
      return;
    }
    if (error) { page.replaceChildren(...head, el('div', { class: 'warnbox', role: 'alert' }, error)); return; }
    if (!data) { page.replaceChildren(...head, el('p', { role: 'status' }, t('xr.loading'))); return; }
    const pathOf = Object.fromEntries(data.repos.map((r) => [r.name, r.path]));
    const rels = data.relations.filter((r) => showCand || r.certainty === 'confirmed');
    const stats = el('div', { class: 'tw' }, el('table', { class: 't', 'data-testid': 'xr-stats' },
      el('thead', {}, el('tr', {}, [t('repos.col.name'), t('xr.files'), t('xr.read'), t('xr.unparsed'), t('xr.functions'), t('xr.endpoints')].map((h) => el('th', {}, h)))),
      el('tbody', {}, data.repos.map((r) => el('tr', {}, el('td', {}, r.name), el('td', {}, r.files), el('td', {}, r.read),
        el('td', {}, r.unparsed + r.tooLarge), el('td', {}, r.functions + (r.functionsTruncated ? ' ' + t('xr.truncated') : '')), el('td', {}, r.endpoints))))));
    const toggle = el('label', { class: 'row mini' }, el('input', { type: 'checkbox', checked: showCand || null, 'data-testid': 'xr-candidates', onchange: (e) => { showCand = e.target.checked; render(); } }), t('xr.showCand'));
    // the diagram: repositories on a circle, one edge per pair with the count of each kind
    const W = 640, H = 360, R = 130, cx = W / 2, cy = H / 2;
    const pos = Object.fromEntries(data.repos.map((r, i) => { const a = (i / data.repos.length) * Math.PI * 2 - Math.PI / 2; return [r.name, [cx + R * Math.cos(a), cy + R * Math.sin(a)]]; }));
    const pairs = new Map();
    for (const r of rels) {
      const k = [r.from.repo, r.to.repo].join('→');
      if (!pairs.has(k)) pairs.set(k, { from: r.from.repo, to: r.to.repo, list: [] });
      pairs.get(k).list.push(r);
    }
    const NS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    svg.setAttribute('class', 'xr-svg');
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', t('xr.diagram'));
    svg.setAttribute('data-testid', 'xr-diagram');
    const mk = (tag, attrs, text) => { const n = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v); if (text != null) n.textContent = text; return n; };
    const defs = mk('defs', {});
    defs.append(Object.assign(mk('marker', { id: 'xr-arrow', viewBox: '0 0 10 10', refX: 10, refY: 5, markerWidth: 8, markerHeight: 8, orient: 'auto-start-reverse' }), {}));
    defs.firstChild.append(mk('path', { d: 'M0 0L10 5L0 10z', fill: 'currentColor' }));
    svg.append(defs);
    for (const [key, p] of pairs) {
      const [x1, y1] = pos[p.from], [x2, y2] = pos[p.to];
      const counts = {};
      for (const r of p.list) counts[r.kind + (r.certainty === 'candidate' ? '?' : '')] = (counts[r.kind + (r.certainty === 'candidate' ? '?' : '')] || 0) + 1;
      const label = Object.entries(counts).map(([k, v]) => `${t('xr.kind.' + k.replace('?', ''))}${k.endsWith('?') ? '(' + t('xr.cand') + ')' : ''} ${v}`).join(' · ');
      const onlyCand = p.list.every((r) => r.certainty === 'candidate');
      const dx = x2 - x1, dy = y2 - y1, len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
      const g = mk('g', { class: 'xr-edge' + (pickEdge === key ? ' on' : ''), tabindex: '0', role: 'button', 'data-edge': key, 'aria-label': `${p.from} → ${p.to}: ${label}` });
      g.append(mk('line', { x1: x1 + ux * 34, y1: y1 + uy * 34, x2: x2 - ux * 34, y2: y2 - uy * 34, 'stroke-dasharray': onlyCand ? '6 4' : null, 'marker-end': 'url(#xr-arrow)' }));
      g.append(mk('text', { x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 6, 'text-anchor': 'middle' }, label));
      const go = () => { pickEdge = key; pickRepo = null; render(); };
      g.addEventListener('click', go);
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      svg.append(g);
    }
    for (const r of data.repos) {
      const [x, y] = pos[r.name];
      const g = mk('g', { class: 'xr-node' + (pickRepo === r.name ? ' on' : ''), tabindex: '0', role: 'button', 'data-repo': r.name, 'aria-label': r.name });
      g.append(mk('circle', { cx: x, cy: y, r: 32 }), mk('text', { x, y: y + 4, 'text-anchor': 'middle' }, r.name.length > 12 ? r.name.slice(0, 11) + '…' : r.name));
      const go = () => { pickRepo = r.name; pickEdge = null; render(); };
      g.addEventListener('click', go);
      g.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      svg.append(g);
    }
    const listed = pickEdge ? (pairs.get(pickEdge)?.list || []) : pickRepo ? rels.filter((r) => r.from.repo === pickRepo || r.to.repo === pickRepo) : rels;
    const table = listed.length
      ? el('div', { class: 'tw' }, el('table', { class: 't', 'data-testid': 'xr-table' },
        el('thead', {}, el('tr', {}, [t('xr.col.kind'), t('xr.col.certainty'), t('xr.col.label'), t('xr.col.from'), t('xr.col.to'), t('xr.col.reqs')].map((h) => el('th', {}, h)))),
        el('tbody', {}, listed.map((r) => el('tr', { 'data-testid': 'xr-row', 'data-kind': r.kind, 'data-certainty': r.certainty },
          el('td', {}, icon(KIND_ICON[r.kind], { size: 16 }), ' ', t('xr.kind.' + r.kind)),
          el('td', {}, el('span', { class: 'badge ' + (r.certainty === 'confirmed' ? 'ok' : '') }, r.certainty === 'confirmed' ? t('xr.conf') : t('xr.cand'))),
          el('td', { class: 'mono' }, r.label),
          el('td', {}, codeLink(pathOf[r.from.repo], r.from)), el('td', {}, codeLink(pathOf[r.to.repo], r.to)),
          el('td', {}, ...[...reqsFor(r.from), ...reqsFor(r.to)].flatMap((id, i) => [i ? ', ' : '', xrefLink(id, id)])))))))
      : el('p', { 'data-testid': 'xr-none' }, t('xr.none', { kinds: data.kinds.map((k) => t('xr.kind.' + k)).join(t('ins.sep')), files: data.repos.map((r) => `${r.name} ${r.files}`).join(t('ins.sep')) }));
    const repoEntry = pickRepo ? el('p', { class: 'card', 'data-testid': 'xr-repo-entry' }, t('xr.repo.entry', { name: pickRepo }), ' ',
      el('a', { href: '#/source?q=' + encodeURIComponent(pickRepo + ':') }, t('xr.repo.files')), ' · ', el('a', { href: '#/tables?tab=files&q=' + encodeURIComponent(pickRepo + ':') }, t('xr.repo.table'))) : null;
    page.replaceChildren(...[...head, stats, toggle, el('div', { class: 'card xr-board' }, svg), repoEntry,
      pickEdge || pickRepo ? el('button', { type: 'button', class: 'btn ghost', onclick: () => { pickEdge = pickRepo = null; render(); } }, t('xr.all')) : null, table].filter(Boolean));
  };
  const load = () => {
    if ((store.model?.meta?.repos || []).length < 2) { render(); return; }
    fetch('/api/xrepo', { cache: 'no-store' }).then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail || j.error); data = j; error = null; render(); })
      .catch((e) => { error = String(e.message || e); render(); });
  };
  render();
  load();
  const offM = store.on('model', () => { data = null; load(); });
  const offL = onLang(render);
  return { destroy() { offM(); offL(); } };
}
