import { t, lang, setLang, onLang, applyI18n } from './i18n.js';
import { store } from './store.js';
import { el, esc, colorOf, typeLabel, toast } from './ui.js';
import { initDrawer } from './drawer.js';

const ROUTES = {
  dashboard: { icon: '◉', load: () => import('./dashboard.js') },
  map2d: { icon: '▦', load: () => import('./map2d.js') },
  map3d: { icon: '◈', load: () => import('./map3d.js') },
  diagrams: { icon: '⬡', load: () => import('./diagrams.js') },
  placement: { icon: '⊞', load: () => import('./placement.js') },
  source: { icon: '⌘', load: () => import('./source.js') },
  tables: { icon: '☰', load: () => import('./tables.js') },
};
const view = document.getElementById('view');
const nav = document.getElementById('nav');
let current = null, token = 0, fingerprint = null;

const routeName = () => { const r = (location.hash.replace(/^#\/?/, '') || 'dashboard').split('?')[0]; return ROUTES[r] ? r : 'dashboard'; };

// Deep links: #/map2d?select=FR-001 or #/tables?q=keyword (applied once per navigation).
let linkDone = '';
function applyDeepLink() {
  const raw = location.hash;
  if (linkDone === raw || !raw.includes('?')) return;
  linkDone = raw;
  const p = new URLSearchParams(raw.split('?')[1]);
  if (p.get('select') && store.nodes.has(p.get('select'))) setTimeout(() => store.select(p.get('select'), { fly: true }), 50);
  else if (p.get('q')) {
    const r = store.search(p.get('q'));
    if (r.total) setTimeout(() => store.setFocus(r.all, `“${p.get('q')}”`), 50);
  }
}

function renderNav() {
  const r = routeName();
  nav.replaceChildren(...Object.entries(ROUTES).map(([k, v]) => el('a', { href: '#/' + k, class: k === r ? 'on' : '' }, el('span', {}, v.icon), t('nav.' + k))));
}

async function route() {
  const name = routeName();
  renderNav();
  if (!store.model) return;
  const my = ++token;
  current?.destroy?.();
  current = null;
  const host = el('div', { class: 'fill' });
  view.replaceChildren(host);
  try {
    const mod = await ROUTES[name].load();
    if (my !== token) return;
    current = mod.mount(host);
    applyDeepLink();
  } catch (e) {
    console.error(e);
    host.replaceChildren(el('div', { class: 'page' }, el('div', { class: 'warnbox' }, String((e && e.message) || e))));
  }
}

async function loadModel(quiet) {
  const res = await fetch('/api/model', { cache: 'no-store' });
  const model = await res.json();
  store.load(model);
  document.title = `EABK Studio · ${model.meta.name}`;
  document.getElementById('repoBtn').textContent = '📁 ' + model.meta.name;
  document.getElementById('repoBtn').title = model.meta.repo;
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
function renderResults() {
  const val = q.value.trim();
  if (!val || !store.model) { box.hidden = true; lastResult = null; return; }
  lastResult = store.search(val, 40);
  hits = lastResult.hits;
  active = Math.min(active, Math.max(0, hits.length - 1));
  box.hidden = false;
  box.replaceChildren(
    el('div', { class: 'hd' }, el('span', {}, `${lastResult.total} ${lang() === 'ja' ? '件' : 'hits'}`),
      lastResult.total ? el('button', { onclick: highlightAll }, '✦ ' + (lang() === 'ja' ? 'すべて図で強調' : 'Highlight all')) : ''),
    ...hits.map((n, i) => el('div', { class: 'res' + (i === active ? ' on' : ''), onmouseenter: () => { active = i; mark(); }, onclick: () => choose(n.id) },
      el('i', { class: 'dot', style: { background: colorOf(n) } }),
      el('span', { class: 't', html: `<b>${hl(n.label, lastResult.toks)}</b><small>${esc(typeLabel(n))}${n.title && n.title !== n.label ? ' · ' + hl(String(n.title).slice(0, 90), lastResult.toks) : ''}</small>` }))));
}
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
  else if (e.key === 'Enter') { e.preventDefault(); if (e.shiftKey) highlightAll(); else if (hits[active]) choose(hits[active].id); }
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
document.getElementById('repoBtn').addEventListener('click', async () => {
  const cur = store.model?.meta.repo || '';
  const path = window.prompt(t('repo.prompt'), cur);
  if (!path || path === cur) return;
  const res = await fetch('/api/repo', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-EABK-Studio': '1' }, body: JSON.stringify({ path }) });
  if (!res.ok) { const j = await res.json().catch(() => ({})); toast(j.error === 'no-data-layer' ? t('repo.nodata') : t('repo.bad')); return; }
  store.clear();
  await loadModel();
});
window.addEventListener('hashchange', route);

setInterval(async () => {
  if (document.hidden || !store.model) return;
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
loadModel().catch((e) => { view.replaceChildren(el('div', { class: 'page' }, el('div', { class: 'warnbox' }, 'Failed to load: ' + e.message))); });
