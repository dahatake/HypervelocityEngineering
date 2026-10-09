// Small DOM and presentation helpers shared by every view.
import { t, lang } from './i18n.js';
import { store } from './store.js';

export const TYPE_COLOR = {
  goal: '#ffb020', req: '#4f9dff', nfr: '#2fd3c9', ac: '#9b8cff', part: '#ff6bd6', api: '#34e0a1', table: '#ffd166',
  entity: '#ff8a5c', file: '#8aa1b5', test: '#7ee7a8', component: '#e4e9f0', case: '#ff5c7a', param: '#c3a6ff',
  question: '#ff4d6d', persona: '#f5a3ff', external: '#7dd3fc',
};
export const TYPE_ORDER = ['goal', 'req', 'ac', 'entity', 'part', 'api', 'table', 'param', 'question', 'file', 'component', 'case', 'persona', 'external'];
export const STATUS_COLOR = { approved: '#34e0a1', proposed: '#ffb020', hold: '#8aa1b5', rejected: '#ff5c7a', retired: '#62708f', unknown: '#62708f' };
export const BUSINESS_ICON = {
  dashboard: ['📊', 'Dashboard'],
  map2d: ['🗺️', '2D relationship map'],
  map3d: ['🧊', '3D relationship map'],
  diagrams: ['🧩', 'Diagrams'],
  placement: ['🧭', 'Data placement'],
  source: ['💻', 'Source'],
  tables: ['📋', 'Data tables'],
  maintenance: ['🛠️', 'Integrity maintenance'],
  structure: ['🏗️', 'Data-layer structure'],
  consistency: ['🔎', 'Consistency viewer'],
  goal: ['🎯', 'Business goal'],
  req: ['📝', 'Requirement'],
  entity: ['🔗', 'Entity'],
  api: ['🔌', 'API'],
  test: ['✅', 'Test'],
  progress: ['🚀', 'Progress'],
  history: ['🕘', 'History'],
  risk: ['⚠️', 'Risk'],
};

export function businessIcon(kind, label) {
  const [glyph, fallback] = BUSINESS_ICON[kind] || ['•', kind];
  return el('span', { class: 'biz-icon', role: 'img', 'aria-label': label || fallback, title: label || fallback }, glyph);
}

export function colorOf(n) {
  if (!n) return '#888';
  if (n.type === 'req') return n.kind === 'NFR' ? TYPE_COLOR.nfr : TYPE_COLOR.req;
  if (n.type === 'file' && n.role === 'test') return TYPE_COLOR.test;
  return TYPE_COLOR[n.type] || '#888';
}
export const typeLabel = (n) => t(n.type === 'req' && n.kind === 'NFR' ? 'type.nfr' : n.type === 'file' && n.role === 'test' ? 'type.test' : 'type.' + n.type);

export function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'html') e.innerHTML = v;
    else if (k === 'style' && typeof v === 'object') Object.assign(e.style, v);
    else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
}
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const svgEl = (tag, attrs, ...kids) => {
  const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null) e.setAttribute(k, v);
  for (const c of kids.flat()) if (c != null) e.append(c.nodeType ? c : document.createTextNode(c));
  return e;
};

export function statusText(kind, raw) {
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
export function toast(msg) {
  const e = document.getElementById('toast');
  e.textContent = msg; e.hidden = false;
  clearTimeout(toastTimer);
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
