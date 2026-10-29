// Small DOM and presentation helpers shared by every view.
import { t, lang } from './i18n.js';
import { store } from './store.js';

// 系列色はデザイントークン（tokens.css の --viz-* / --color-status-*）から現在のテーマの値を読む（直値を持たない。FR-1048）。
// 値はテーマが変わるまで保持し、変わったら読み直す（描画の性能を保つ）。
let tokenCache = {};
if (typeof window !== 'undefined' && window.eabkTheme) window.eabkTheme.onChange(() => { tokenCache = {}; });
export function token(name) {
  return tokenCache[name] ??= getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
function tokenMap(map) {
  const o = {};
  for (const [k, name] of Object.entries(map)) Object.defineProperty(o, k, { enumerable: true, get: () => token(name) });
  return o;
}
export const TYPE_COLOR = tokenMap({
  goal: '--viz-goal', req: '--viz-req', nfr: '--viz-nfr', ac: '--viz-ac', part: '--viz-part', api: '--viz-api', table: '--viz-table',
  entity: '--viz-entity', file: '--viz-file', test: '--viz-test', component: '--viz-comp', case: '--viz-case', param: '--viz-param',
  question: '--viz-question', persona: '--viz-persona', external: '--viz-external', integration: '--viz-external',
});
export const IMPL_COLOR = tokenMap({ done: '--color-status-success-icon', none: '--color-status-danger-icon', unlisted: '--color-status-neutral-icon' });
export const TYPE_ORDER = ['goal', 'req', 'ac', 'entity', 'part', 'api', 'table', 'param', 'question', 'file', 'component', 'case', 'persona', 'external', 'integration'];
export const STATUS_COLOR = tokenMap({
  approved: '--color-status-success-icon', proposed: '--color-status-warning-icon', hold: '--color-status-neutral-icon',
  rejected: '--color-status-danger-icon', retired: '--color-status-neutral-icon', unknown: '--color-status-neutral-icon',
});
// 同梱のアイコンセット（1 セットのみ。外部取得しない。FR-1048 AC-268）: 線画・currentColor・24 の格子で描き、16・20・24px のどれかで表示する。
const ICON_PATHS = {
  dashboard: 'M4 4h6v7H4zM14 4h6v4h-6zM14 12h6v8h-6zM4 15h6v5H4z',
  progress: 'M5 20V12M12 20V5M19 20v-5M3 20h18',
  map2d: 'M12 5a2 2 0 1 0 0 .01M5 17a2 2 0 1 0 0 .01M19 17a2 2 0 1 0 0 .01M11 7l-5 8M13 7l5 8M7 17h10',
  map3d: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9',
  diagrams: 'M3 5h7v5H3zM14 5h7v5h-7zM8.5 14h7v5h-7zM6.5 10v2h11v-2M12 12v2',
  placement: 'M12 21s7-6 7-11a7 7 0 0 0-14 0c0 5 7 11 7 11zM12 10m-2.5 0a2.5 2.5 0 1 0 5 0a2.5 2.5 0 1 0-5 0',
  entities: 'M9.5 14.5l5-5M8 11l-2 2a3.5 3.5 0 0 0 5 5l2-2M16 13l2-2a3.5 3.5 0 0 0-5-5l-2 2',
  integrations: 'M9 3v5M15 3v5M6 8h12v4a6 6 0 0 1-12 0zM12 18v3',
  source: 'M9 7l-5 5 5 5M15 7l5 5-5 5M13.5 5l-3 14',
  tables: 'M3 5h18v14H3zM3 10h18M3 15h18M9 5v14',
  maintenance: 'M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4',
  structure: 'M12 3l9 5-9 5-9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
  consistency: 'M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13M15.5 16l5 5M8 10.5l2 2 3.5-4',
  goal: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 7a5 5 0 1 0 0 10a5 5 0 1 0 0-10M12 11a1 1 0 1 0 0 2a1 1 0 1 0 0-2',
  req: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7',
  entity: 'M9.5 14.5l5-5M8 11l-2 2a3.5 3.5 0 0 0 5 5l2-2M16 13l2-2a3.5 3.5 0 0 0-5-5l-2 2',
  api: 'M4 8h14M14 4l4 4-4 4M20 16H6M10 12l-4 4 4 4',
  test: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M8 12.5l3 3 5-6',
  history: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 7v5l3 2',
  risk: 'M12 3l10 18H2zM12 10v5M12 18v.5',
  folder: 'M3 6h6l2 2h10v11H3z',
  person: 'M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8M4 21a8 8 0 0 1 16 0',
  empty: 'M3 7h18v13H3zM3 7l3-4h12l3 4M9 12h6',
  error: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M9 9l6 6M15 9l-6 6',
  stale: 'M12 3l10 18H2zM12 10v5M12 18v.5',
  info: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 11v6M12 7.5v.5',
  rpg: 'M4 20V9h3V6h2v3h2V6h2v3h2V6h2v3h3v11zM10 20v-5h4v5',
  search: 'M10.5 4a6.5 6.5 0 1 0 0 13a6.5 6.5 0 1 0 0-13M15.5 16l5 5',
  // FR-1079: Graph の切替アイコンと、ノードの種類の図柄（同じ様式の線画）
  graph: 'M6 4a2 2 0 1 0 0 4a2 2 0 1 0 0-4M6 16a2 2 0 1 0 0 4a2 2 0 1 0 0-4M18 10a2 2 0 1 0 0 4a2 2 0 1 0 0-4M6 8v8M8 7l8 4M8 17l8-4',
  ac: 'M4 6l2 2 3-3M4 14l2 2 3-3M12 7h8M12 15h8',
  state: 'M7 5a3 3 0 1 0 0 6a3 3 0 1 0 0-6M17 13a3 3 0 1 0 0 6a3 3 0 1 0 0-6M9.5 11l5 2',
  component: 'M4 4h7v7H4zM13 13h7v7h-7zM13 4h7v4h-7zM4 15h4v5H4z',
};
// The icon's accessible name when no label is given: dictionary keys bizicon.<kind>.
export const BUSINESS_ICON = Object.fromEntries(['dashboard', 'map2d', 'map3d', 'diagrams', 'placement', 'entities', 'integrations', 'source', 'tables', 'maintenance',
  'structure', 'consistency', 'goal', 'req', 'entity', 'api', 'test', 'progress', 'history', 'risk'].map((k) => [k, 'bizicon.' + k]));

// 線画のアイコン 1 つ（svg）。size は 16・20・24 のどれか。decorative のときは支援技術から隠す。
export function icon(name, { size = 20, label = '' } = {}) {
  const svg = svgEl('svg', { viewBox: '0 0 24 24', width: size, height: size, class: 'icon', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.75,
    'stroke-linecap': 'round', 'stroke-linejoin': 'round', focusable: 'false', 'aria-hidden': label ? null : 'true', role: label ? 'img' : null, 'aria-label': label || null });
  svg.append(svgEl('path', { d: ICON_PATHS[name] || ICON_PATHS.info }));
  return svg;
}

export function businessIcon(kind, label) {
  const name = label || (BUSINESS_ICON[kind] ? t(BUSINESS_ICON[kind]) : kind);
  return el('span', { class: 'biz-icon', role: 'img', 'aria-label': name, title: name }, icon(ICON_PATHS[kind] ? kind : 'info'));
}

export function colorOf(n) {
  if (!n) return token('--viz-file');
  if (n.type === 'req') return n.kind === 'NFR' ? TYPE_COLOR.nfr : TYPE_COLOR.req;
  if (n.type === 'file' && n.role === 'test') return TYPE_COLOR.test;
  return TYPE_COLOR[n.type] || token('--viz-file');
}
export const typeLabel = (n) => t(n.type === 'req' && n.kind === 'NFR' ? 'type.nfr' : n.type === 'file' && n.role === 'test' ? 'type.test' : 'type.' + n.type);

export function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on')) { e.addEventListener(k.slice(2), v); (e._on ||= []).push([k.slice(2), v, undefined]); } // _on: 動的可視化（viz.js）が要素を再利用するときの付け替え用
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// 状態表示（読込中・空・エラー・古い）の共通の形（FR-1047 / NFR-A11Y-001 AC-274）: アイコン・見出し・説明・操作。
// 色だけで示さず、アイコンの形と見出しの文言でも伝える。変更を伴う通知は role=alert / status で支援技術に伝える。
export function statePanel({ state, heading, description, action }) {
  const mark = state === 'loading'
    ? el('span', { 'data-part': 'icon', role: 'progressbar', 'aria-label': heading }, el('span', { class: 'spin' }))
    : el('span', { 'data-part': 'icon', 'aria-hidden': 'true' }, icon(['empty', 'error', 'stale'].includes(state) ? state : 'info', { size: 24 }));
  const panel = el('div', {
    class: 'state-panel', 'data-testid': 'state-panel', 'data-state': state,
    role: state === 'error' ? 'alert' : 'status', 'aria-live': state === 'error' ? 'assertive' : 'polite',
    'aria-busy': state === 'loading' ? 'true' : null,
  }, mark, el('p', { 'data-part': 'heading' }, heading), el('p', { 'data-part': 'description' }, description || ''),
  el('div', { 'data-part': 'action' }, action || ''));
  return panel;
}
export const svgEl = (tag, attrs, ...kids) => {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, v);
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};

export function statusText(kind, raw) {
  // i18n-data: the status text is a managed-data value ("承認済み（…）" → its first part) and is shown as written in Japanese
  if (lang() === 'ja' && raw) return raw.split('（')[0];
  return t('status.' + (kind || 'unknown'));
}
export const statusBadge = (kind, raw) => el('span', { class: 'badge ' + kind }, statusText(kind, raw));

export function nodeChip(id, label) {
  const n = store.node(id);
  if (!n) return el('span', { class: 'nchip' }, label || id);
  return el('span', { class: 'nchip', title: n.title || n.id, onclick: (e) => { e.stopPropagation(); store.select(id, { fly: true }); } },
    el('i', { class: 'dot', style: { background: colorOf(n) } }), el('span', { class: 'l' }, label || n.label));
}

export function vscodeUrl(path, line) {
  const base = store.model.meta.repo.replace(/\\/g, '/');
  const p = path.startsWith('/') || /^[A-Za-z]:/.test(path) ? path : base + '/' + path;
  return 'vscode://file/' + encodeURI(p) + (line ? ':' + line : '');
}

let toastTimer;
// NFR-OPS-003 AC-028: with `actions` ([{label, run}]) the toast stays until an action is taken.
export function toast(msg, actions) {
  const e = document.getElementById('toast');
  clearTimeout(toastTimer);
  e.textContent = msg; e.hidden = false;
  // A toast with recovery actions reports a failure (AC-028 / AC-335): announce it assertively.
  e.setAttribute('role', actions && actions.length ? 'alert' : 'status');
  e.setAttribute('aria-live', actions && actions.length ? 'assertive' : 'polite');
  if (actions && actions.length) {
    for (const a of actions) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'btn ghost'; b.textContent = a.label;
      b.addEventListener('click', () => { e.hidden = true; a.run?.(); });
      e.append(b);
    }
    return;
  }
  toastTimer = setTimeout(() => (e.hidden = true), 2600);
}

let tipEl;
export function showTip(html, x, y) {
  if (!tipEl) { tipEl = el('div', { class: 'tip' }); document.body.append(tipEl); }
  tipEl.innerHTML = html; tipEl.hidden = false;
  const w = tipEl.offsetWidth, h = tipEl.offsetHeight;
  tipEl.style.left = Math.min(x + 16, innerWidth - w - 8) + 'px';
  tipEl.style.top = Math.min(y + 16, innerHeight - h - 8) + 'px';
}
export function hideTip() { if (tipEl) tipEl.hidden = true; }
export function nodeTip(n) {
  // i18n-data: the status text is a managed-data value; only its first part is shown
  return `<b style="color:${colorOf(n)}">${esc(n.label)}</b><div class="mini">${esc(typeLabel(n))}${n.status ? ' · ' + esc(n.status.split('（')[0]) : ''}</div>${n.title ? `<div>${esc(String(n.title).slice(0, 180))}</div>` : ''}`;
}

export function animateNumber(node, to, ms = 900) {
  if (document.documentElement.classList.contains('snapshot')) {
    node.textContent = String(to);
    return;
  }
  const t0 = performance.now();
  const dec = String(to).includes('.') ? 1 : 0;
  const step = (now) => {
    const p = Math.min(1, (now - t0) / ms), e = 1 - Math.pow(1 - p, 3);
    node.textContent = (to * e).toFixed(dec);
    if (p < 1) requestAnimationFrame(step); else node.textContent = String(to);
  };
  requestAnimationFrame(step);
}

export function legendEl(types) {
  return el('div', { class: 'legend' }, types.map((ty) => el('span', {}, el('i', { class: 'dot', style: { background: TYPE_COLOR[ty] } }), t('type.' + ty))));
}
