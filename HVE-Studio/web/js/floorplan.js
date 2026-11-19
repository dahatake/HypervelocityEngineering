// FR-1092: the floorplan viewer — the same kind of map as Floorplan's Brewline demo, made from the repository itself (no AI).
// Parts, files and endpoints as cards; "used by | inside | uses" columns; Screens, Health, Recent work, Flows and a tour;
// a question box that answers from the map (a path between two things); links you can share (#/floorplan?v=…&s=…).
// Data: GET /api/floorplan (read only) and, inside a file, GET /api/codegraph for its functions.
import { t, onLang } from './i18n.js';
import { el, esc, toast, showTip, hideTip } from './ui.js';
import { sourceTabs } from './srctabs.js';
import { createBoard, icon } from './fp-board.js';
import { indexModel, boardOf, membersOf, chain, parentOf, memberFor, outsideFor, describe, labelOf, shortestPath, allFiles, folderFiles, KIND_ORDER } from './fp-data.js';
import { mountPanels } from './fp-panels.js';

const EDITORS = { vscode: 'vscode://file/{path}:{line}', 'vscode-insiders': 'vscode-insiders://file/{path}:{line}', vscodium: 'vscodium://file/{path}:{line}', cursor: 'cursor://file/{path}:{line}', windsurf: 'windsurf://file/{path}:{line}', zed: 'zed://file/{path}:{line}', idea: 'idea://open?file={path}&line={line}', phpstorm: 'phpstorm://open?file={path}&line={line}' };
const STRENGTH = { http: 5, data: 4, event: 3, queue: 3, rpc: 3, call: 2, config: 1, import: 0 };
const STOP = new Set('the a an of to in on for and or how does do is are what where which when who why from into with by it its this that these those me my i we you reach reaches get gets go goes work works use uses used'.split(' '));

export function mount(host) {
  const page = el('div', { class: 'page fp-page' });
  host.append(page);
  const S = { g: null, m: null, view: '', sel: null, answer: null, kinds: new Set(KIND_ORDER), technical: false, recentOn: true, panelOpen: true, flow: null, marks: null, dismissed: new Set(), cg: null, noTour: false };
  let board = null, panelEl, headerEl, flowBar, hoverId = null, destroyed = false, menuEl = null, modalCtl = null, tabsEl = null;
  const stateKey = () => 'hve-floorplan.dismissed:' + (S.g?.meta.repo || '');

  // ------------------------------------------------------------ load
  async function load() {
    page.replaceChildren(sourceTabs('functions'), el('div', { class: 'fp-loading mini', role: 'status' }, t('cg.loading')));
    try {
      const r = await fetch('/api/floorplan', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      S.g = await r.json();
    } catch (e) { if (!destroyed) page.replaceChildren(sourceTabs('functions'), el('div', { class: 'warnbox' }, t('cg.error') + ' ' + String(e.message || e))); return false; }
    S.m = indexModel(S.g);
    try { S.dismissed = new Set(JSON.parse(localStorage.getItem(stateKey()) || '[]')); } catch { S.dismissed = new Set(); }
    return true;
  }
  async function codegraph() {
    if (S.cg) return S.cg;
    try { const r = await fetch('/api/codegraph', { cache: 'no-store' }); S.cg = r.ok ? await r.json() : { nodes: [], edges: [] }; } catch { S.cg = { nodes: [], edges: [] }; }
    return S.cg;
  }
  /** Functions of one file and the calls in and out of them (from the code graph), added to the model on demand. */
  async function loadSymbols(view) {
    const m = S.m, file = view.slice(2);
    m.fileSyms ||= new Map(); m.symLinks ||= new Map(); m.symInfo ||= new Map();
    if (m.fileSyms.has(view)) return;
    const cg = await codegraph();
    const mine = cg.nodes.filter((n) => n.file === file && n.kind !== 'module').sort((a, b) => b.deg - a.deg || a.line - b.line).slice(0, 24);
    const ids = new Set(mine.map((n) => 's:' + n.id));
    for (const n of mine) m.symInfo.set('s:' + n.id, n);
    const links = [];
    for (const e of cg.edges) {
      if (e.conf === 'name') continue;
      const sf = e.s.split('::')[0], tf = e.t.split('::')[0];
      if (sf !== file && tf !== file) continue;
      const a = 's:' + e.s, b = 's:' + e.t;
      const A = sf === file ? (ids.has(a) ? a : null) : 'f:' + sf, B = tf === file ? (ids.has(b) ? b : null) : 'f:' + tf;
      if (A && B && A !== B && m.files.has(A.startsWith('f:') ? A : 'f:' + file) && (A.startsWith('s:') || B.startsWith('s:'))) links.push({ a: A, b: B, k: 'call', w: e.n || 1 });
    }
    m.fileSyms.set(view, [...ids]);
    m.symLinks.set(view, links);
  }

  // ------------------------------------------------------------ url
  function readUrl() {
    const p = new URLSearchParams(location.hash.split('?')[1] || '');
    S.noTour = p.get('tour') === '0';
    return { v: p.get('v') || '', s: p.get('s') || null };
  }
  function writeUrl(push = true) {
    const p = new URLSearchParams();
    if (S.view) p.set('v', S.view);
    if (S.sel) p.set('s', S.sel);
    if (S.noTour) p.set('tour', '0');
    const url = '#/floorplan' + (p.toString() ? '?' + p : '');
    if (location.hash === url) return;
    if (push) history.pushState(null, '', url); else history.replaceState(null, '', url);
  }
  const validView = (v) => v === '' || (v.startsWith('n:') && S.m.nodes.has(v)) || (v.startsWith('f:') && S.m.files.has(v)) || (v.startsWith('d:') && S.m.nodes.has('n:' + v.slice(2).split('|')[0]));
  const exists = (id) => !!id && (S.m.nodes.has(id) || S.m.files.has(id) || S.m.routes.has(id) || id.startsWith('d:') || id.startsWith('s:'));

  // ------------------------------------------------------------ navigation
  async function go(view, { sel = null, push = true, transition, keep = false, marks = null } = {}) {
    if (!validView(view)) view = '';
    const deeper = view.length > S.view.length || chain(S.m, S.view).includes(view) === false && view !== '';
    S.view = view; S.sel = sel && exists(sel) ? sel : null; S.answer = null; S.marks = marks; hoverId = null;
    if (view.startsWith('f:')) await loadSymbols(view);
    await draw({ transition: transition ?? (deeper ? 'in' : 'out'), keepCamera: keep });
    writeUrl(push);
  }
  const up = () => { if (S.answer) { S.answer = null; draw({}); return; } if (!S.view) return; const from = S.view; go(upView(from), { sel: from }); };
  function upView(v) {
    if (v.startsWith('d:')) { const f = v.slice(2).split('|'); const parent = f[1].includes('/') ? `d:${f[0]}|${f[1].slice(0, f[1].lastIndexOf('/'))}` : ''; return parent && S.m.own.get('n:' + f[0]) && parent.split('|')[1].length ? parentFolder(f[0], parent) : 'n:' + f[0]; }
    return parentOf(S.m, v);
  }
  const parentFolder = (nid, chip) => (membersOf(S.m, 'n:' + nid).includes(chip) ? chip : 'n:' + nid);
  const openItem = (id) => {
    if (id.startsWith('n:') || id.startsWith('d:') || id.startsWith('f:')) return go(id);
    if (id.startsWith('r:')) return go('f:' + S.m.routes.get(id).f, { sel: id });
    if (id.startsWith('s:')) return go('f:' + id.slice(2).split('::')[0], { sel: id });
  };
  /** The view where `id` is a card, so it can be shown and selected. */
  function viewOf(id) {
    if (id.startsWith('n:')) return parentOf(S.m, id);
    if (id.startsWith('f:')) {
      const node = 'n:' + S.m.files.get(id).n, mem = membersOf(S.m, node);
      if (mem.includes(id)) return node;
      const chip = mem.find((x) => x.startsWith('d:') && id.slice(2).startsWith(x.split('|')[1] + '/'));
      return chip ? deepestChip(chip, id) : node;
    }
    if (id.startsWith('r:')) return 'f:' + S.m.routes.get(id).f;
    if (id.startsWith('s:')) return 'f:' + id.slice(2).split('::')[0];
    return '';
  }
  function deepestChip(chip, fileId) {
    const inner = membersOf(S.m, chip).find((x) => x.startsWith('d:') && fileId.slice(2).startsWith(x.split('|')[1] + '/'));
    return inner ? deepestChip(inner, fileId) : chip;
  }
  const reveal = (id) => go(viewOf(id), { sel: id });
  /** The smallest view in which both items are cards (or one holds the other). */
  function lcaView(a, b) {
    if (a === b) return viewOf(a);
    const cb = chain(S.m, b), hit = chain(S.m, a).find((x) => cb.includes(x));
    if (!hit) return '';
    return hit === a || hit === b ? hit : hit;
  }

  // ------------------------------------------------------------ drawing
  function answerBoard() {
    const ids = S.answer.ids;
    const data = boardOf(S.m, '', S.kinds, { ids });
    for (let i = 0; i + 1 < S.answer.steps.length; i++) {
      const a = S.answer.steps[i].id, b = S.answer.steps[i + 1].id;
      if (!data.edges.some((e) => (e.a === a && e.b === b) || (e.a === b && e.b === a))) data.edges.push({ a, b, k: 'import', w: 1, carries: new Map() });
    }
    return data;
  }
  async function draw({ transition, keepCamera = false } = {}) {
    if (!board) return;
    const m = S.m, data = S.answer ? answerBoard() : boardOf(m, S.view, S.kinds);
    const cards = [], partitions = new Map();
    const stepNo = new Map((S.answer?.steps || []).map((s, i) => [s.id, i + 1]));
    const add = (id, pill) => { const d = describe(m, id, t); cards.push({ id, pill, type: d.type, d, no: stepNo.get(id) }); };
    data.members.forEach((id) => add(id, false));
    data.left.forEach((id) => add(id, true)); data.right.forEach((id) => add(id, true));
    for (const c of cards) {
      if (data.left.includes(c.id)) partitions.set(c.id, 0);
      else if (data.right.includes(c.id)) partitions.set(c.id, 2);
      else partitions.set(c.id, !S.view && !S.answer ? board.partOf(m.nodes.get(c.id)?.kind) : 1);
    }
    // one line per pair of cards, drawn in the strongest kind
    const merged = new Map();
    for (const e of data.edges) {
      const k = e.a + '\u0001' + e.b, cur = merged.get(k);
      if (!cur) merged.set(k, { ...e, kinds: new Set([e.k]), carries: new Map(e.carries) });
      else { cur.w += e.w; cur.kinds.add(e.k); if ((STRENGTH[e.k] ?? 0) > (STRENGTH[cur.kind] ?? 0)) cur.kind = e.k; for (const [c, n] of e.carries) cur.carries.set(c, (cur.carries.get(c) || 0) + n); }
      const x = merged.get(k); x.kind ||= e.k;
    }
    const edges = [...merged.values()].map((e) => ({ ...e, kind: e.kind || e.k }));
    const name = S.view ? labelOf(m, S.view, S.technical) : '';
    const brackets = S.answer || !S.view ? [] : [{ label: t('fp.br.used'), ids: data.left }, { label: t('fp.inside', { name }), ids: data.members }, { label: t('fp.br.uses'), ids: data.right }];
    await board.show({ cards, edges, partitions, brackets, state: S, transition, keepCamera, paint: paintArgs() });
    renderHeader(); renderPanel(); renderFlowBar();
    page.dataset.view = S.view; page.dataset.answer = S.answer ? '1' : '';
  }
  const paintArgs = () => ({ focus: hoverId || S.sel, marks: S.marks, dim: null });
  function renderCard(c) {
    const d = c.d, rec = S.recentOn ? S.m.recent.get(c.id) : null, nrec = S.recentOn ? S.m.recentTop.get(c.id) : 0;
    const title = S.technical ? d.dev : d.title, sub = S.technical ? d.title : '';
    if (c.pill) return el('div', { class: 'fp-card pill', role: 'button', tabindex: '0', 'data-testid': 'fp-card', 'data-type': c.type, 'aria-label': title }, icon(d.icon, 14), el('span', { class: 'fp-title' }, title));
    const foot = [d.foot ? el('span', {}, d.foot) : '', rec ? el('span', { class: 'fp-tag new' }, t(rec.change === 'new' ? 'fp.tag.new' : 'fp.tag.changed')) : nrec ? el('span', { class: 'fp-tag new' }, t('fp.tag.n', { n: nrec })) : '',
      d.note ? el('span', { class: 'fp-dot', title: d.note }) : ''];
    return el('div', { class: 'fp-card ' + c.type + (rec ? ' changed' : ''), role: 'button', tabindex: '0', 'data-testid': 'fp-card', 'data-type': c.type, 'aria-label': `${title}. ${d.desc || d.foot || ''}` },
      c.no ? el('span', { class: 'fp-step' }, String(c.no)) : '',
      d.type === 'route' ? el('div', { class: 'fp-route mono' }, el('b', {}, d.method), ' ', d.urlPath) : '',
      el('div', { class: 'fp-head' }, icon(d.icon, 15), el('span', { class: 'fp-title' }, title)),
      sub ? el('div', { class: 'fp-sub mono' }, sub) : '',
      d.desc ? el('div', { class: 'fp-desc' }, d.desc) : '', el('div', { class: 'fp-foot mini' }, ...foot));
  }

  // ------------------------------------------------------------ selection
  function select(id) {
    S.sel = S.sel === id ? null : id;
    board.paint(paintArgs()); renderPanel(); writeUrl(false);
  }
  const editorUrl = (path, line = 1) => {
    const tpl = EDITORS[S.g.meta.editor] || (String(S.g.meta.editor).includes('{path}') ? S.g.meta.editor : EDITORS.vscode);
    const base = S.g.meta.repo.replace(/\\/g, '/');
    return tpl.replace('{path}', encodeURI(path.startsWith('/') || /^[A-Za-z]:/.test(path) ? path : base + '/' + path)).replace('{line}', String(line || 1)).replace('{column}', '1');
  };
  const copy = async (text) => { try { await navigator.clipboard.writeText(text); toast(t('fp.copied')); } catch { toast(t('fp.copy.failed') + ' ' + text); } };

  // ------------------------------------------------------------ the question box (answers from the map, no AI)
  function index() {
    if (S.index) return S.index;
    const list = [];
    for (const [id, n] of S.m.nodes) list.push({ id, text: [n.label, n.id, n.summary].join(' ').toLowerCase(), name: n.label.toLowerCase(), path: (n.paths || []).join(' ').toLowerCase() });
    for (const [id, f] of S.m.files) list.push({ id, text: [f.name, f.p, f.d].join(' ').toLowerCase(), name: f.name.toLowerCase(), path: f.p.toLowerCase() });
    for (const [id, r] of S.m.routes) list.push({ id, text: [r.name, r.m, r.p, r.d].join(' ').toLowerCase(), name: r.name.toLowerCase(), path: (r.m + ' ' + r.p).toLowerCase() });
    return (S.index = list);
  }
  const tokens = (q) => q.toLowerCase().split(/[^\p{L}\p{N}_./-]+/u).filter((w) => w.length >= 2 && !STOP.has(w));
  function best(q) {
    const tk = tokens(q);
    if (!tk.length) return null;
    let top = null;
    for (const it of index()) {
      let s = 0;
      for (const w of tk) { if (it.name.includes(w)) s += 3; if (it.path.includes(w)) s += 2; if (it.text.includes(w)) s += 1; }
      if (it.name === q.toLowerCase().trim()) s += 6;
      const bonus = it.id.startsWith('r:') ? 0.2 : it.id.startsWith('f:') ? 0.1 : 0;
      if (s && (!top || s + bonus > top.s)) top = { id: it.id, s: s + bonus };
    }
    return top && top.s >= Math.min(3, tk.length * 2) ? top.id : null;
  }
  function ask(text) {
    const q = text.trim();
    if (!q) return;
    const split = q.split(/\s+(?:to|reach(?:es)?|into|until)\s+|\s*(?:->|→|＞)\s*|\s*から\s*|\s*まで\s*/i).map((x) => x.trim()).filter(Boolean);
    let a = null, b = null;
    if (split.length >= 2) { a = best(split[0]); b = best(split.slice(1).join(' ')); }
    if (a && b && a !== b) {
      const path = shortestPath(S.m, a, b);
      if (path) return showAnswer({ title: q, ids: path, steps: path.map((id, i) => ({ id, note: i ? t('fp.ans.then', { a: labelOf(S.m, path[i - 1]), b: labelOf(S.m, id) }) : t('fp.ans.start') })), kind: 'path' });
      return showAnswer({ title: q, ids: [a, b], steps: [], none: true, kind: 'nopath' });
    }
    const one = a || best(q);
    if (!one) return showAnswer({ title: q, ids: [], steps: [], none: true, kind: 'unknown' });
    const links = [...(S.m.out.get(one) || []), ...(S.m.inn.get(one) || [])];
    const ids = [one, ...new Set(links.flatMap((l) => [l.a, l.b]).filter((x) => x !== one))].slice(0, 14);
    showAnswer({ title: q, ids, steps: [{ id: one, note: t('fp.ans.about') }], kind: 'about' });
  }
  async function showAnswer(a) {
    S.answer = a; S.sel = null; S.marks = null;
    await draw({ transition: 'in' });
  }

  // ------------------------------------------------------------ flows and the tour
  function startFlow(flow, kind) {
    const steps = flow.steps.map((s) => ({ id: s.node, note: s.note || '', title: s.title || '' }));
    S.flow = { title: flow.title, steps, i: 0, kind };
    stepFlow(0);
  }
  async function stepFlow(i) {
    const f = S.flow;
    if (!f) return;
    f.i = Math.max(0, Math.min(f.steps.length - 1, i));
    const step = f.steps[f.i], prev = f.steps[f.i - 1];
    if (!exists(step.id)) return;
    const view = f.kind === 'tour' || !prev ? viewOf(step.id) : lcaView(prev.id, step.id);
    S.answer = null;
    await go(view, { sel: null, push: false, transition: 'in' });
    const a = prev ? memberFor(S.m, S.view, prev.id, new Set(board.cards.keys())) || prev.id : null, b = memberFor(S.m, S.view, step.id, new Set(board.cards.keys())) || step.id;
    S.sel = b; board.paint({ focus: b, marks: new Set([a, b].filter(Boolean)) });
    if (a && b && a !== b) board.signal(a, b);
    renderPanel(); renderFlowBar();
  }
  const stopFlow = () => { S.flow = null; renderFlowBar(); };
  function renderFlowBar() {
    flowBar?.remove(); flowBar = null;
    const f = S.flow;
    if (!f) return;
    const s = f.steps[f.i];
    flowBar = el('div', { class: 'fp-flowbar', role: 'status', 'data-testid': 'fp-flowbar' },
      el('div', { class: 'fp-flow-t' }, el('b', {}, f.title), el('span', { class: 'mini' }, ` ${f.i + 1} / ${f.steps.length}`)),
      el('div', { class: 'fp-flow-n' }, s.title ? el('b', {}, s.title + ' ') : '', s.note || labelOf(S.m, s.id)),
      el('div', { class: 'row' }, el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'fp-flow-prev', disabled: f.i === 0 || null, onclick: () => stepFlow(f.i - 1) }, '←'),
        el('button', { type: 'button', class: 'btn', 'data-testid': 'fp-flow-next', onclick: () => (f.i === f.steps.length - 1 ? stopFlow() : stepFlow(f.i + 1)) }, f.i === f.steps.length - 1 ? t('fp.flow.done') : '→'),
        el('button', { type: 'button', class: 'btn ghost', onclick: stopFlow }, t('fp.flow.stop'))));
    stageWrap.append(flowBar);
  }

  // ------------------------------------------------------------ header, panel, modals, menus (fp-panels.js)
  let stageWrap, panelsApi;
  const ctx = {
    S, t, el, icon, go, up, reveal, openItem, select, ask, showAnswer, startFlow, stopFlow, stepFlow, copy, editorUrl, viewOf, draw, lcaView, describe, labelOf, boardOf, memberFor, outsideFor, allFiles, folderFiles,
    refreshPaint: () => board.paint(paintArgs()), saveDismissed: () => localStorage.setItem(stateKey(), JSON.stringify([...S.dismissed])), toggleTechnical: (v) => { S.technical = v; draw({ keepCamera: true }); },
    toggleRecent: (v) => { S.recentOn = v; draw({ keepCamera: true }); }, toggleKind: (k, on) => { if (on) S.kinds.add(k); else S.kinds.delete(k); draw({ keepCamera: true }); },
    togglePanel: () => { S.panelOpen = !S.panelOpen; stageWrap.parentElement.classList.toggle('no-panel', !S.panelOpen); setTimeout(() => board.fit(), 0); },
    fit: () => board.fit(), zoomBy: (f) => board.zoomBy(f), centerOn: (ids) => board.centerOn(ids), setMarks: (marks) => { S.marks = marks; board.paint(paintArgs()); },
    get board() { return board; },
  };
  function renderHeader() { panelsApi.header(); }
  function renderPanel() { panelsApi.panel(); }

  // ------------------------------------------------------------ keyboard
  function onKey(e) {
    if (destroyed) return;
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName);
    if (e.key === 'Escape') { if (panelsApi.closeOverlays()) return; if (S.flow) return stopFlow(); if (S.answer) { S.answer = null; return draw({}); } if (S.sel) return select(S.sel); if (typing) e.target.blur(); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); return panelsApi.focusSearch(); }
    if (typing || e.ctrlKey || e.metaKey || e.altKey || panelsApi.modalOpen()) return;
    if (e.key === '/') { e.preventDefault(); panelsApi.focusSearch(); }
    else if (e.key === 'Enter' && S.sel && !e.target.closest?.('.fp-card')) openItem(S.sel);
    else if (e.key === 'Backspace') { e.preventDefault(); up(); }
    else if (e.key === 'f' || e.key === 'F') board.fit();
    else if (e.key === '+' || e.key === '=') board.zoomBy(1.2);
    else if (e.key === '-' || e.key === '_') board.zoomBy(1 / 1.2);
    else if (e.key === 'p' || e.key === 'P') ctx.togglePanel();
    else if (e.key === 'ArrowRight' && S.flow) stepFlow(S.flow.i + 1);
    else if (e.key === 'ArrowLeft' && S.flow) stepFlow(S.flow.i - 1);
  }
  const onClickAway = (e) => { if (!e.target.closest?.('.fp-menu,.fp-pop')) panelsApi.closeMenus(); };

  // ------------------------------------------------------------ assemble
  function build() {
    stageWrap = el('div', { class: 'fp-main' });
    headerEl = el('header', { class: 'fp-header' });
    panelEl = el('aside', { class: 'fp-panel', 'data-testid': 'fp-side', 'aria-live': 'polite' });
    const body = el('div', { class: 'fp-body' }, stageWrap, panelEl);
    tabsEl = sourceTabs('functions');
    page.replaceChildren(tabsEl, headerEl, body);
    board = createBoard(stageWrap, {
      renderCard, isSelected: (id) => id === S.sel,
      onSelect: (id) => select(id), onOpen: (id) => openItem(id),
      onHover: (id, ev) => { hoverId = id; board.paint(paintArgs()); if (id) { const d = describe(S.m, id, t); showTip(`<b>${esc(d.title)}</b><div class="mini">${esc(d.type)}${d.path ? ' · ' + esc(d.path) : ''}</div>${d.desc ? '<div>' + esc(d.desc) + '</div>' : ''}`, ev.clientX, ev.clientY); } else hideTip(); },
      onEdgeHover: (e, ev) => { if (!e) return hideTip(); const lines = [...e.carries].slice(0, 8).map(([k, n]) => `<div class="mono">${esc(k)}${n > 1 ? ' ×' + n : ''}</div>`).join(''); showTip(`<b>${esc(labelOf(S.m, e.a, S.technical))} → ${esc(labelOf(S.m, e.b, S.technical))}</b><div class="mini">${esc([...e.kinds].map((k) => t('fp.kind.' + k)).join(', '))} · ×${e.w}</div>${lines}`, ev.clientX, ev.clientY); },
      onBackground: () => { if (S.sel) select(S.sel); },
      onContext: (target, ev) => panelsApi.contextMenu(target, ev),
    });
    panelsApi = mountPanels(ctx, { headerEl, panelEl, stageWrap });
  }
  document.addEventListener('keydown', onKey);
  document.addEventListener('pointerdown', onClickAway);
  const offLang = onLang(() => { if (S.g) { S.index = null; const nt = sourceTabs('functions'); tabsEl?.replaceWith(nt); tabsEl = nt; renderHeader(); renderPanel(); draw({ keepCamera: true }); } });
  const view = { mode: 'floorplan', getState: () => ({ view: S.view, selected: S.sel, answer: !!S.answer, cards: board?.cards?.size || 0, technical: S.technical, flow: S.flow ? S.flow.i : null, health: S.g?.health.summary || null, ready: !!board?.cards }),
    go: (v, o) => go(v, o), select: (id) => select(id), reveal, ask };
  window.eabkView = view;

  const apply = async () => {
    const u = readUrl();
    await go(u.v, { sel: u.s, push: false, transition: 'in' });
  };
  load().then(async (ok) => {
    if (!ok || destroyed) return;
    S.index = null;
    build();
    await apply();
  });
  return {
    onHash: () => { if (S.g && board) apply(); },
    destroy() { destroyed = true; document.removeEventListener('keydown', onKey); document.removeEventListener('pointerdown', onClickAway); offLang(); board?.destroy(); hideTip(); if (window.eabkView === view) window.eabkView = undefined; },
  };
}
