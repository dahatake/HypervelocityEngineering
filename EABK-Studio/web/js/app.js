import { t, lang, setLang, onLang, applyI18n } from './i18n.js';
import { store } from './store.js';
import { el, esc, colorOf, typeLabel, toast, businessIcon } from './ui.js';
import { initDrawer } from './drawer.js';
import { installXref } from './xref.js';
import { decorate, mountStructure, mountConsistency, mountMaintenance } from './insights.js';
import { dimToggle, dimState, registerDim, hasDimHandler, runDim } from './dim.js';

// FR-1041: the top navigation, organised by "what data can be viewed" (9 items, MECE).
// Old screen ids (map2d / map3d / placement) stay as aliases and move to the item that now holds them (AC-226).
const ROUTES = {
  dashboard: { icon: 'dashboard', load: () => import('./dashboard.js') },
  implstatus: { icon: 'progress', load: () => import('./implstatus.js') },
  map2d: { navKey: 'map', icon: 'map2d', dim: '2d', load: () => import('./map2d.js') },
  map3d: { navKey: 'map', icon: 'map3d', dim: '3d', load: () => import('./map3d.js') },
  diagrams: { icon: 'diagrams', load: () => import('./diagrams.js') },
  placement: { navKey: 'diagrams', alias: 'diagrams', load: () => import('./diagrams.js') },
  entities: { icon: 'entities', load: () => import('./entities.js') },
  integrations: { icon: 'integrations', load: () => import('./integrations.js') },
  source: { icon: 'source', load: () => import('./source.js') },
  tables: { icon: 'tables', load: () => import('./tables.js') },
  maintenance: { icon: 'maintenance', mount: mountMaintenance },
  structure: { navKey: 'maintenance', hidden: true, mount: mountStructure },
  consistency: { navKey: 'maintenance', hidden: true, mount: mountConsistency },
};
// nav items in display order: key → route it opens (the map opens in the dimension chosen last)
const NAV = ['dashboard', 'implstatus', 'map', 'diagrams', 'entities', 'integrations', 'source', 'tables', 'maintenance'];
const navTarget = (k) => (k === 'map' ? (dimState.map === '3d' ? 'map3d' : 'map2d') : k);
const navKeyOf = (route) => ROUTES[route]?.navKey || route;
const view = document.getElementById('view');
const nav = document.getElementById('nav');
const navDesc = document.getElementById('navDesc');
let current = null, token = 0, fingerprint = null;

const personaBar = document.getElementById('personaBar');
for (const [name, icon] of [['Product Manager', '🎯'], ['Architect', '🏗️'], ['Software Engineer', '💻']]) {
  personaBar.append(el('button', { class: 'chip persona', 'aria-label': `${name} view`, onclick: () => {
    if (name === 'Architect') location.hash = '#/map2d';
    else if (name === 'Software Engineer') location.hash = '#/tables';
    else location.hash = '#/dashboard';
  } }, el('span', { class: 'biz-icon', role: 'img', 'aria-hidden': 'true' }, icon), name));
}

const routeName = () => { const r = (location.hash.replace(/^#\/?/, '') || 'dashboard').split('?')[0]; return ROUTES[r] ? r : 'dashboard'; };
const isSnapshotLink = () => new URLSearchParams(location.hash.split('?')[1] || '').has('select');

// Deep links: #/map2d?select=FR-001 or #/tables?q=keyword (applied once per navigation).
let linkDone = '';
function applyDeepLink() {
  const raw = location.hash;
  if (linkDone === raw || !raw.includes('?')) return;
  linkDone = raw;
  const p = new URLSearchParams(raw.split('?')[1]);
  if (p.get('q')) q.value = p.get('q');
  if (p.get('select') && store.nodes.has(p.get('select'))) store.select(p.get('select'), { fly: !isSnapshotLink() });
  else if (p.get('q')) {
    const r = store.search(p.get('q'));
    if (r.total) setTimeout(() => store.setFocus(r.all, `“${p.get('q')}”`), 50);
  }
}

function renderNav() {
  const r = navKeyOf(routeName());
  nav.replaceChildren(...NAV.map((k) => {
    const label = t('nav.' + k), desc = t('navd.' + k);
    return el('a', { href: '#/' + navTarget(k), class: k === r ? 'on' : '', 'aria-current': k === r ? 'page' : null, title: desc, 'data-nav': k, 'aria-describedby': 'navDesc' }, businessIcon(ROUTES[navTarget(k)].icon, label), el('span', {}, label));
  }));
  // each screen opens with the same one-line description (AC-224)
  navDesc.textContent = ROUTES[routeName()]?.hidden && !NAV.includes(r) ? '' : t('navd.' + r);
}

// Old URLs move to the item that holds the view now, keeping the kind / dimension / ?select / ?q (FR-1041 AC-226).
function legacyRedirect(name) {
  if (name !== 'placement') return false;
  const p = new URLSearchParams(location.hash.split('?')[1] || '');
  const out = new URLSearchParams();
  out.set('kind', 'layers');
  if (p.get('kind') === 'runtime') out.set('view', 'runtime'); else out.set('view', 'matrix');
  for (const k of ['tab', 'select', 'q']) if (p.get(k)) out.set(k, p.get(k));
  location.replace('#/diagrams?' + out.toString());
  return true;
}

async function route() {
  const name = routeName();
  if (legacyRedirect(name)) return;
  document.documentElement.dataset.route = name;
  document.documentElement.classList.toggle('snapshot', isSnapshotLink());
  if (ROUTES[name].dim) dimState.map = ROUTES[name].dim;
  renderNav();
  if (!store.model) return;
  const my = ++token;
  current?.destroy?.();
  current = null;
  const host = el('div', { class: 'fill' });
  view.replaceChildren(host);
  host.append(el('div', { class: 'sr-only', role: 'status' }, t('loading'))); // never leave the view empty while the module loads
  try {
    const mod = ROUTES[name].mount ? { mount: ROUTES[name].mount } : await ROUTES[name].load();
    if (my !== token) return;
    host.querySelector(':scope > [role=status].sr-only')?.remove();
    current = mod.mount(host);
    if (ROUTES[name].dim) mountMapDim(host, name, current);
    decorate(name, host);
    applyDeepLink();
    if (isSnapshotLink()) {
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      host.append(el('span', { class: 'sr-only' }, `Snapshot ready: ${name}`));
    }
  } catch (e) {
    console.error(e);
    host.replaceChildren(el('div', { class: 'page' }, el('div', { class: 'warnbox' }, String((e && e.message) || e))));
  }
}

// The map is one item: 2D (map2d) and 3D (map3d) are two displays of it, switched here (FR-1040).
// Selection, filter and the search box live in the store / shared view state, so they survive the switch (AC-221).
function mountMapDim(host, name, inner) {
  const go = (d) => {
    const q = location.hash.includes('?') ? '?' + location.hash.split('?')[1] : '';
    location.hash = '#/' + (d === '3d' ? 'map3d' : 'map2d') + q;
  };
  host.append(el('div', { class: 'dim-float' }, dimToggle({ current: ROUTES[name].dim, onPick: go })));
  const off = registerDim((d) => go(d || (ROUTES[name].dim === '2d' ? '3d' : '2d')));
  const orig = inner?.destroy;
  if (inner) inner.destroy = () => { off(); orig?.call(inner); };
}

async function loadModel(quiet) {
  const res = await fetch('/api/model', { cache: 'no-store' });
  const model = await res.json();
  store.load(model);
  document.title = `EABK Studio · ${model.meta.name}`;
  document.getElementById('repoBtn').textContent = '📁 ' + model.meta.name;
  document.getElementById('repoBtn').title = model.meta.repo;
  const modelTime = document.getElementById('modelTime');
  modelTime.dateTime = model.meta.generatedAt;
  modelTime.textContent = model.meta.generatedAt;
  const f = await (await fetch('/api/fingerprint')).json();
  fingerprint = f.fingerprint;
  if (!quiet) route();
}

// ---------------------------------------------------------------- search
const q = document.getElementById('q');
const box = document.getElementById('results');
let hits = [], active = 0, lastResult = null;

function hl(text, toks) {
  let s = esc(text);
  for (const tk of toks) if (tk) s = s.replace(new RegExp('(' + esc(tk).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')', 'ig'), '<mark>$1</mark>');
  return s;
}
// FR-1041 AC-226: every nav item (and the 2D / 3D switch) is reachable from the command box.
function navCommands() {
  const list = NAV.map((k) => ({ cmd: true, id: 'cmd:nav:' + k, label: t('cmd.goto') + t('nav.' + k), key: t('nav.' + k), run: () => { location.hash = '#/' + navTarget(k); } }));
  if (hasDimHandler()) list.push({ cmd: true, id: 'cmd:dim', label: t('cmd.dim'), key: '2D 3D', run: () => runDim() });
  return list;
}
// FR-1033 AC-197: command box. ">" followed by text lists commands; Enter runs one.
function commandHits(val) {
  const ja = lang() === 'ja';
  const needle = val.slice(1).trim().toLowerCase();
  const states = store.model.implStatus?.states || [];
  const list = states.map((s) => ({ cmd: true, id: 'cmd:select:' + s, label: (ja ? '実装状態の区間を選択: ' : 'Select impl-status segment: ') + s,
    run: () => { location.hash = '#/implstatus'; store.setImplFilter({ state: s, scope: null, group: null }); } }));
  list.push({ cmd: true, id: 'cmd:clear', label: ja ? '実装状態の絞り込みを解除' : 'Clear impl-status filter', run: () => store.setImplFilter(null) });
  return [...list, ...navCommands()].filter((c) => c.label.toLowerCase().includes(needle));
}
function renderResults() {
  const val = q.value.trim();
  if (!val || !store.model) { box.hidden = true; lastResult = null; return; }
  if (/^[>＞]/.test(val)) {
    hits = commandHits(val); lastResult = null; active = Math.min(active, Math.max(0, hits.length - 1)); box.hidden = false;
    box.replaceChildren(el('div', { class: 'result-body', role: 'listbox', 'data-testid': 'command-list' }, ...hits.map((c, i) => el('div', { class: 'res' + (i === active ? ' on' : ''), role: 'option', 'data-testid': 'command-item', onclick: () => runCommand(c) }, el('span', { class: 't' }, c.label)))));
    return;
  }
  lastResult = store.search(val, 40);
  // a nav item whose name matches the typed text comes first (moves to that screen on Enter)
  const navHits = val.length >= 2 ? navCommands().filter((c) => c.key.toLowerCase().includes(val.toLowerCase())) : [];
  hits = [...navHits, ...lastResult.hits];
  active = Math.min(active, Math.max(0, hits.length - 1));
  box.hidden = false;
  const resultBody = el('div', { class: 'result-body' },
    el('div', { class: 'hd' }, el('span', {}, `${lastResult.total} ${lang() === 'ja' ? '件' : 'hits'}`),
      lastResult.total ? el('button', { onclick: highlightAll }, '✦ ' + (lang() === 'ja' ? 'すべて図で強調' : 'Highlight all')) : ''),
    ...hits.map((n, i) => n.cmd
      ? el('div', { class: 'res' + (i === active ? ' on' : ''), 'data-testid': 'command-item', onmouseenter: () => { active = i; mark(); }, onclick: () => runCommand(n) }, el('span', { class: 't' }, n.label))
      : el('div', { class: 'res' + (i === active ? ' on' : ''), onmouseenter: () => { active = i; mark(); }, onclick: () => choose(n.id) },
        el('i', { class: 'dot', style: { background: colorOf(n) } }),
        el('span', { class: 't', html: `<b>${hl(n.label, lastResult.toks)}</b><small>${esc(typeLabel(n))}${n.title && n.title !== n.label ? ' · ' + hl(String(n.title).slice(0, 90), lastResult.toks) : ''}</small>` }))));
  box.replaceChildren(resultBody);
}
function runCommand(c) { box.hidden = true; q.value = ''; c.run(); }
function mark() { [...box.querySelectorAll('.res')].forEach((e, i) => e.classList.toggle('on', i === active)); }
function ensureGraphView() { if (routeName() === 'dashboard') location.hash = '#/map2d'; }
function choose(id) { box.hidden = true; ensureGraphView(); store.select(id, { fly: true }); }
function highlightAll() {
  if (!lastResult) return;
  box.hidden = true; ensureGraphView();
  const ids = new Set(lastResult.all);
  if (lastResult.total <= 30) for (const id of lastResult.all) for (const a of store.adj.get(id) || []) ids.add(a.id);
  store.setFocus([...ids], `“${q.value.trim()}”`);
}
q.addEventListener('input', () => { active = 0; renderResults(); });
q.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { active = Math.min(hits.length - 1, active + 1); mark(); e.preventDefault(); box.querySelectorAll('.res')[active]?.scrollIntoView({ block: 'nearest' }); }
  else if (e.key === 'ArrowUp') { active = Math.max(0, active - 1); mark(); e.preventDefault(); box.querySelectorAll('.res')[active]?.scrollIntoView({ block: 'nearest' }); }
  else if (e.key === 'Enter') { e.preventDefault(); if (e.shiftKey) highlightAll(); else if (hits[active]?.cmd) runCommand(hits[active]); else if (hits[active]) choose(hits[active].id); }
  else if (e.key === 'Escape') { box.hidden = true; q.blur(); }
});
q.addEventListener('focus', renderResults);
document.addEventListener('pointerdown', (e) => { if (!e.target.closest('.search')) box.hidden = true; });
document.addEventListener('keydown', (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '');
  if ((e.key === '/' && !typing) || ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k')) { e.preventDefault(); q.focus(); q.select(); }
  else if (e.key === 'Escape' && !typing && (store.selected || store.focus)) store.clear();
});

// ---------------------------------------------------------------- chrome
document.getElementById('lang').addEventListener('click', () => setLang(lang() === 'ja' ? 'en' : 'ja'));
function renderLangBtn() { document.getElementById('lang').innerHTML = lang() === 'ja' ? '<b>JA</b> | EN' : 'JA | <b>EN</b>'; }
onLang(() => { renderLangBtn(); renderNav(); if (!box.hidden) renderResults(); });
async function chooseRepository(cur) {
  const modal = el('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true' },
    el('form', { class: 'card', onsubmit: (e) => e.preventDefault() },
      el('h3', {}, t('repo.prompt')),
      el('input', { type: 'text', value: cur, autofocus: true }),
      el('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: '12px' } },
        el('button', { type: 'button', class: 'btn ghost', onclick: () => modal.remove() }, 'Cancel'),
        el('button', { type: 'submit', class: 'btn', onclick: () => modal.dispatchEvent(new CustomEvent('chosen', { detail: modal.querySelector('input').value })) }, 'OK'))));
  document.body.append(modal);
  return await new Promise((resolve) => {
    modal.addEventListener('chosen', (e) => { const value = e.detail.trim(); modal.remove(); resolve(value); });
  });
}
document.getElementById('repoBtn').addEventListener('click', async () => {
  const cur = store.model?.meta.repo || '';
  await switchRepository(cur, await chooseRepository(cur));
});
// NFR-OPS-003 AC-028: on failure keep the current model, show cause + Retry / Back.
async function switchRepository(cur, path) {
  if (!path || path === cur) return;
  const res = await fetch('/api/repo', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-EABK-Studio': '1' }, body: JSON.stringify({ path }) });
  if (!res.ok) {
    const j = await res.json().catch(() => ({}));
    toast(j.error === 'no-data-layer' ? t('repo.nodata') : t('repo.bad'), [
      { label: t('repo.retry'), run: async () => switchRepository(cur, await chooseRepository(path)) },
      { label: t('repo.back'), run: () => {} },
    ]);
    return;
  }
  store.clear();
  await loadModel();
}
window.addEventListener('hashchange', route);

setInterval(async () => {
  if (document.hidden || !store.model || routeName() === 'maintenance') return;
  try {
    const f = await (await fetch('/api/fingerprint', { cache: 'no-store' })).json();
    if (fingerprint && f.fingerprint !== fingerprint) { toast(t('update.avail')); await loadModel(true); route(); }
  } catch { /* server stopped */ }
}, 4000);

const headerEl = document.querySelector('.top');
new ResizeObserver(() => document.documentElement.style.setProperty('--hh', headerEl.offsetHeight + 'px')).observe(headerEl);
applyI18n(document);
renderLangBtn();
renderNav();
view.replaceChildren(el('div', { class: 'splash' }, el('div', { class: 'spin' }), t('loading')));
initDrawer(document.getElementById('drawer'));
installXref();
for (const k of ['dashboard', 'implstatus', 'diagrams', 'map2d']) ROUTES[k].load().catch(() => {}); // warm the module cache (the 2D map is the default map target)
loadModel().catch((e) => { view.replaceChildren(el('div', { class: 'page' }, el('div', { class: 'warnbox' }, 'Failed to load: ' + e.message))); });
