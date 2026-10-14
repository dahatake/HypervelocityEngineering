// FR-1031: every ID / file path / term that exists in the managed data becomes a link to its detail.
// Unknown IDs, paths and names are left as plain text (AC-189: no dead links).
import { store } from './store.js';
import { typeLabel } from './ui.js';

export const ID_RE = /\b(?:G|FR|NFR(?:-[A-Z]+)?|AC|Q|PARAM|SRC|E2E|IT)-\d+\b/g;
const PATH_RE = /(?:[A-Za-z0-9_.-]+\/)+[A-Za-z0-9_.-]+/g;
const SKIP = 'A,BUTTON,SCRIPT,STYLE,TEXTAREA,INPUT,SELECT,SVG,svg,CODE-EDIT,[data-noxref],[role=button],[role=link],[contenteditable]';
const NAMED = new Set(['part', 'api', 'table', 'entity', 'component']);

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
}

// Link element for a managed-data object; the kind and ID are read out by screen readers (AC-190).
export function xrefLink(id, text) {
  const n = store.node(id);
  if (!n) return document.createTextNode(text ?? id);
  const a = document.createElement('a');
  a.className = 'xref';
  a.href = `#/map2d?select=${encodeURIComponent(id)}`;
  a.textContent = text ?? id;
  a.dataset.xref = id;
  a.setAttribute('aria-label', `${typeLabel(n)} ${n.id}`);
  a.title = `${typeLabel(n)} ${n.id}${n.title ? ' — ' + String(n.title).slice(0, 80) : ''}`;
  return a;
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
  const whole = s.trim();
  if (!hits.length && nameIndex.has(whole)) hits.push({ i: s.indexOf(whole), len: whole.length, id: nameIndex.get(whole) });
  if (!hits.length) return;
  hits.sort((a, b) => a.i - b.i);
  const frag = document.createDocumentFragment();
  let pos = 0;
  for (const h of hits) {
    if (h.i < pos) continue;
    if (h.i > pos) frag.append(s.slice(pos, h.i));
    frag.append(xrefLink(h.id, s.slice(h.i, h.i + h.len)));
    pos = h.i + h.len;
  }
  if (pos < s.length) frag.append(s.slice(pos));
  node.replaceWith(frag);
}

export function linkify(root) {
  if (!store.model || !root || root.nodeType !== 1) return;
  indexes();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (t) => (t.parentElement && !t.parentElement.closest(SKIP) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
  });
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
