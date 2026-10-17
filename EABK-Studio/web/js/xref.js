// FR-1031: every ID / file path / term that exists in the managed data becomes a link to its detail.
// Unknown paths and names are left as plain text (AC-189: no dead links); unknown IDs in tables / integrations show 「未解決」 (FR-1050 AC-279).
import { store } from './store.js';
import { t } from './i18n.js';
import { typeLabel } from './ui.js';

export const ID_RE = /\b(?:G|FR|NFR(?:-[A-Z]+)?|AC|Q|PARAM|SRC|E2E|IT|INT)-\d+\b/g;
const PATH_RE = /(?:[A-Za-z0-9_.-]+\/)+[A-Za-z0-9_.-]+/g;
const SKIP = 'a,button,script,style,textarea,input,select,title,desc,[data-noxref],[role=link],[contenteditable]';
const NAMED = new Set(['part', 'api', 'table', 'entity', 'component', 'term']);
const SVG_NS = 'http://www.w3.org/2000/svg';
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
let nameRe = null;

let pathIndex = null;
let nameIndex = null;
function indexes() {
  if (pathIndex && pathIndex.model === store.model) return;
  pathIndex = new Map(); pathIndex.model = store.model;
  nameIndex = new Map();
  for (const n of store.nodes.values()) {
    if (n.type === 'file') { pathIndex.set(n.id, n.id); if (n.path) pathIndex.set(n.path, n.id); }
    if (NAMED.has(n.type) && n.label && n.label.length >= 2) nameIndex.set(n.label, n.id);
  }
  for (const tm of store.model.terms || []) if (tm.term && tm.term.length >= 2 && store.nodes.has('ent:' + tm.term)) nameIndex.set(tm.term, 'ent:' + tm.term);
  const names = [...nameIndex.keys()].sort((a, b) => b.length - a.length);
  nameRe = names.length ? new RegExp(names.map((x) => (/^[\w-]/.test(x) ? '\\b' : '') + esc(x) + (/[\w-]$/.test(x) ? '\\b' : '')).join('|'), 'g') : null;
}

// Link element for a managed-data object; the kind and ID are read out by screen readers (AC-190).
export function xrefLink(id, text, svg = false) {
  const n = store.node(id);
  if (!n) return document.createTextNode(text ?? id);
  const a = svg ? document.createElementNS(SVG_NS, 'a') : document.createElement('a');
  a.setAttribute('class', 'xref');
  a.setAttribute('href', `#/map2d?select=${encodeURIComponent(id)}`);
  if (svg) a.setAttribute('tabindex', '0');
  a.textContent = text ?? id;
  a.dataset.xref = id;
  a.setAttribute('aria-label', `${typeLabel(n)} ${n.id}`);
  if (!svg) a.title = `${typeLabel(n)} ${n.id}${n.title ? ' — ' + String(n.title).slice(0, 80) : ''}`;
  return a;
}

// FR-1050 AC-279: an ID absent from the managed data is not a link; it carries the word 「未解決」 (not colour alone).
export function unresolvedRef(id) {
  const s = document.createElement('span');
  s.className = 'xref-unresolved mono';
  s.dataset.unresolved = '';
  s.setAttribute('aria-label', `${id} ${t('xref.unresolved')}`);
  s.title = t('xref.unresolved');
  s.append(id, Object.assign(document.createElement('small'), { textContent: ' ⚠ ' + t('xref.unresolved') }));
  return s;
}

// One ID → link when it exists, otherwise the unresolved display.
export function idRef(id, text) {
  return store.node(id) ? xrefLink(id, text ?? id) : unresolvedRef(id);
}

// Text → nodes: every ID-like token becomes a link (exists) or an unresolved mark (does not exist).
export function idsToNodes(text) {
  const s = String(text ?? '');
  const out = [];
  let pos = 0;
  for (const m of s.matchAll(ID_RE)) {
    if (m.index > pos) out.push(s.slice(pos, m.index));
    out.push(idRef(m[0]));
    pos = m.index + m[0].length;
  }
  if (pos < s.length) out.push(s.slice(pos));
  return out;
}

function linkifyText(node) {
  const s = node.nodeValue;
  if (!s || !s.trim()) return;
  const hits = [];
  for (const m of s.matchAll(ID_RE)) if (store.nodes.has(m[0])) hits.push({ i: m.index, len: m[0].length, id: m[0] });
  for (const m of s.matchAll(PATH_RE)) {
    const id = pathIndex.get(m[0]);
    if (id && !hits.some((h) => m.index < h.i + h.len && h.i < m.index + m[0].length)) hits.push({ i: m.index, len: m[0].length, id });
  }
  if (nameRe) for (const m of s.matchAll(nameRe)) if (!hits.some((h) => m.index < h.i + h.len && h.i < m.index + m[0].length)) hits.push({ i: m.index, len: m[0].length, id: nameIndex.get(m[0]) });
  if (!hits.length) return;
  // 除外対象（リンク・ボタンなど）かどうかは、ヒットがあったノードだけで調べる（closest は高価）
  if (!node.parentElement || node.parentElement.closest(SKIP)) return;
  hits.sort((a, b) => a.i - b.i);
  const svg = node.parentElement.namespaceURI === SVG_NS;
  const frag = document.createDocumentFragment();
  let pos = 0;
  for (const h of hits) {
    if (h.i < pos) continue;
    if (h.i > pos) frag.append(s.slice(pos, h.i));
    frag.append(xrefLink(h.id, s.slice(h.i, h.i + h.len), svg));
    pos = h.i + h.len;
  }
  if (pos < s.length) frag.append(s.slice(pos));
  node.replaceWith(frag);
}

export function linkify(root) {
  if (!store.model || !root || root.nodeType !== 1) return;
  indexes();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(linkifyText);
}

// Click and Enter (native link behaviour) open the detail; the page does not navigate (AC-190, AC-204).
document.addEventListener('click', (e) => {
  const a = e.target.closest?.('a.xref');
  if (!a || e.defaultPrevented) return;
  e.preventDefault();
  e.stopPropagation();
  store.select(a.dataset.xref, { fly: false });
}, true);

export function installXref() {
  const targets = ['view', 'drawer'].map((id) => document.getElementById(id)).filter(Boolean);
  let queued = new Set();
  const flush = () => { const q = queued; queued = new Set(); q.forEach((n) => n.isConnected && linkify(n.nodeType === 1 ? n : n.parentElement)); };
  const mo = new MutationObserver((muts) => {
    for (const m of muts) {
      m.addedNodes.forEach((n) => queued.add(n.nodeType === 1 ? n : n.parentElement || n));
      if (m.type === 'characterData') queued.add(m.target);
    }
    queued.delete(null);
    queueMicrotask(flush);
  });
  for (const t of targets) { mo.observe(t, { childList: true, subtree: true }); linkify(t); }
}
