// FR-1091: the "floorplan" — the code as cards in lanes that you open one level at a time:
// all parts → one part (its files) → one file (its functions). Plain-English names first, technical names one switch away.
// Cards are joined by arrows (a number is how many calls); selecting a card lights up what it uses and what uses it.
// Data: GET /api/codegraph (read only). No external library; prefers-reduced-motion: no flow animation, no zoom transition.
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, svgEl, vscodeUrl } from './ui.js';
import { reduced } from './viz.js';
import { layeredLayout } from './graph.js';

const CARD_W = 252, CARD_H = 104, GAP_X = 132, GAP_Y = 20, PAD = 36, HEAD = 40;
const MAX_MEMBERS = 30, MAX_EXT = 7;
const LANES = ['screens', 'code', 'tests'];
const LANE_VAR = { screens: '--viz-fn', code: '--viz-method', tests: '--viz-test' };
const KIND_VAR = { function: '--viz-fn', method: '--viz-method', class: '--viz-class', module: '--viz-module' };

const groupOf = (file) => { const d = file.split('/').slice(0, -1); return d.length ? d.slice(0, 3).join('/') : '.'; };
const clean = (s) => (s || '').replace(/^(?:(?:NFR|FR|AC)-[\w-]+[\s,、]*)+[:：]\s*/i, '').trim();
export const humanize = (name) => {
  const w = String(name).replace(/\.[a-z]+$/i, '').replace(/^_+/, '').replace(/[_\-.]+/g, ' ').replace(/([a-z0-9])([A-Z])/g, '$1 $2').trim()
    .split(/\s+/).map((x) => (x.length > 1 && x === x.toUpperCase() ? x : x.toLowerCase())).join(' ');
  return w.charAt(0).toUpperCase() + w.slice(1);
};
const last = (p, n = 1) => p.split('/').slice(-n).join(' / ');

export function mount(host) {
  const page = el('div', { class: 'page fp-page' });
  host.append(page);
  const ui = { dev: false, q: '' };
  let data = null, groups = new Map(), byFile = new Map(), byId = new Map(), fileInfo = new Map(), edges = [], out = new Map(), inn = new Map();
  let path = [], sel = null, hover = null, view = null, destroyed = false, raf = 0;
  const cam = { x: 0, y: 0, z: 1 };
  let stage, anim, world, svg, side, crumbs, searchBox, sugg, hotPaths = [];

  // ------------------------------------------------------------ model
  async function load() {
    page.replaceChildren(el('h1', {}, t('fp.title')), el('div', { class: 'mini', role: 'status' }, t('cg.loading')));
    try {
      const r = await fetch('/api/codegraph', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      data = await r.json();
    } catch (e) { if (!destroyed) page.replaceChildren(el('h1', {}, t('fp.title')), el('div', { class: 'warnbox' }, t('cg.error') + ' ' + String(e.message || e))); return false; }
    byId = new Map(data.nodes.map((n) => [n.id, n]));
    edges = data.edges.filter((e) => e.conf !== 'name' && byId.has(e.s) && byId.has(e.t));
    out = new Map(); inn = new Map();
    for (const e of edges) {
      (out.get(e.s) || out.set(e.s, []).get(e.s)).push(e);
      (inn.get(e.t) || inn.set(e.t, []).get(e.t)).push(e);
    }
    fileInfo = new Map(data.files.map((f) => [f.path, f]));
    byFile = new Map();
    for (const n of data.nodes) (byFile.get(n.file) || byFile.set(n.file, []).get(n.file)).push(n);
    groups = new Map();
    for (const f of data.files) {
      const g = groupOf(f.path);
      const grp = groups.get(g) || groups.set(g, { key: g, files: [], funcs: 0, tests: 0, js: 0 }).get(g);
      grp.files.push(f); grp.funcs += (byFile.get(f.path) || []).filter((n) => n.kind !== 'module').length;
      if (f.test) grp.tests++;
      if (f.lang === 'js') grp.js++;
    }
    for (const g of groups.values()) {
      const webish = /(^|\/)(web|static|public|frontend|client|ui|components|pages|views)(\/|$)/i.test(g.key);
      g.lane = g.tests === g.files.length ? 'tests' : (g.js > g.files.length / 2 && webish) ? 'screens' : 'code';
      const best = g.files.map((f) => ({ f, d: (byFile.get(f.path) || []).reduce((s, n) => s + n.deg, 0) })).sort((a, b) => b.d - a.d).find((x) => x.f.doc);
      g.doc = best ? clean(best.f.doc) : '';
    }
    return true;
  }
  const fileGroup = (file) => groupOf(file);
  const funcsOf = (file) => (byFile.get(file) || []).filter((n) => n.kind !== 'module').length;

  // ------------------------------------------------------------ one level → cards and arrows
  function buildView() {
    const cards = new Map();
    let cardOf, members = [], heads = {};
    const level = path.length;
    const addCard = (c) => { cards.set(c.key, c); return c; };
    if (level === 0) {
      for (const g of groups.values()) addCard({ key: g.key, type: 'group', lane: g.lane, title: humanize(last(g.key, 1) === '.' ? 'root' : last(g.key, 1)), dev: g.key, desc: g.doc,
        stats: t('fp.stats.group', { files: g.files.length, funcs: g.funcs }), c: LANE_VAR[g.lane], open: [g.key] });
      cardOf = (n) => groupOf(n.file);
    } else if (level === 1) {
      const g = groups.get(path[0]);
      const rank = g.files.map((f) => ({ f, w: (byFile.get(f.path) || []).reduce((s, n) => s + n.deg, 0) })).sort((a, b) => b.w - a.w || (a.f.path < b.f.path ? -1 : 1));
      const keep = new Set(rank.slice(0, MAX_MEMBERS).map((x) => x.f.path));
      for (const f of g.files) if (keep.has(f.path)) addCard({ key: f.path, type: 'file', title: humanize(f.path.split('/').pop()), dev: f.path.split('/').pop(), desc: clean(f.doc),
        stats: t('fp.stats.file', { funcs: funcsOf(f.path), lines: f.loc }), c: f.test ? LANE_VAR.tests : f.lang === 'py' ? '--viz-class' : '--viz-fn', open: [path[0], f.path], reqs: f.reqs });
      cardOf = (n) => (keep.has(n.file) ? n.file : groupOf(n.file) === path[0] ? null : 'x:' + groupOf(n.file));
      heads.more = rank.length - keep.size;
    } else {
      const f = path[1];
      const syms = (byFile.get(f) || []).slice().sort((a, b) => b.deg - a.deg || a.line - b.line).slice(0, MAX_MEMBERS);
      const keep = new Set(syms.map((n) => n.id));
      for (const n of syms) addCard({ key: n.id, type: 'sym', title: n.kind === 'module' ? t('fp.module') : humanize(n.name), dev: n.qual, desc: clean(n.doc),
        stats: `${t('cg.kind.' + n.kind)} · ${t('cg.lines', { n: n.loc })}`, c: KIND_VAR[n.kind] || '--viz-file', node: n });
      cardOf = (n) => (keep.has(n.id) ? n.id : n.file === f ? null : 'x:' + n.file);
      heads.more = (byFile.get(f) || []).length - syms.length;
    }
    // arrows between cards (calls and references of the whole repository, summed per pair of cards)
    const agg = new Map();
    const bump = (a, b, w) => {
      if (!a || !b || a === b || (a.startsWith('x:') && b.startsWith('x:'))) return;
      const k = a + '\u0001' + b;
      (agg.get(k) || agg.set(k, { a, b, w: 0 }).get(k)).w += w;
    };
    for (const e of edges) bump(cardOf(byId.get(e.s)), cardOf(byId.get(e.t)), e.n || 1);
    // between parts and between files, "this file imports that file" counts as a use as well
    if (level < 2) for (const f of data.files) for (const imp of f.imports || []) bump(cardOf({ file: f.path }), cardOf({ file: imp }), 1);
    const arrows = [...agg.values()];
    // outside neighbours: callers on the left, callees on the right (the strongest few)
    const extScore = new Map();
    for (const ar of arrows) {
      if (ar.a.startsWith('x:')) { const s = extScore.get(ar.a) || { call: 0, used: 0 }; s.call += ar.w; extScore.set(ar.a, s); }
      if (ar.b.startsWith('x:')) { const s = extScore.get(ar.b) || { call: 0, used: 0 }; s.used += ar.w; extScore.set(ar.b, s); }
    }
    const left = [], right = [];
    for (const [k, s] of extScore) (s.call >= s.used ? left : right).push([k, s.call + s.used]);
    const top = (list) => list.sort((a, b) => b[1] - a[1]).slice(0, MAX_EXT).map((x) => x[0]);
    const keepExt = new Set([...top(left), ...top(right)]);
    const leftKeys = new Set(top(left));
    for (const k of keepExt) {
      const raw = k.slice(2);
      const isGroup = level === 1;
      addCard({ key: k, type: 'ext', title: humanize(isGroup ? last(raw, 1) : raw.split('/').pop()), dev: raw, desc: isGroup ? clean(groups.get(raw)?.doc) : clean(fileInfo.get(raw)?.doc),
        stats: isGroup ? t('fp.stats.group', { files: groups.get(raw)?.files.length || 0, funcs: groups.get(raw)?.funcs || 0 }) : t('fp.stats.file', { funcs: funcsOf(raw), lines: fileInfo.get(raw)?.loc || 0 }),
        c: '--color-border-strong', open: isGroup ? [raw] : [groupOf(raw), raw], side: leftKeys.has(k) ? 'left' : 'right' });
    }
    const arr = arrows.filter((ar) => cards.has(ar.a) && cards.has(ar.b));
    // columns
    const cols = [];
    const memberCards = [...cards.values()].filter((c) => c.type !== 'ext');
    if (level === 0) {
      for (const lane of LANES) { const list = memberCards.filter((c) => c.lane === lane); if (list.length) cols.push({ head: t('fp.lane.' + lane), cards: list }); }
      for (const col of cols) {
        const w = (c) => arr.reduce((s, ar) => s + (ar.a === c.key || ar.b === c.key ? ar.w : 0), 0);
        col.cards.sort((a, b) => w(b) - w(a) || (a.key < b.key ? -1 : 1));
      }
    } else {
      const ids = memberCards.map((c) => ({ id: c.key }));
      const lay = layeredLayout(ids, arr.filter((ar) => !ar.a.startsWith('x:') && !ar.b.startsWith('x:')).map((ar) => ({ from: ar.a, to: ar.b })));
      const layers = new Map();
      for (const c of memberCards) { const p = lay.pos.get(c.key); (layers.get(p.layer) || layers.set(p.layer, []).get(p.layer)).push([c, p.y]); }
      const ordered = [...layers.entries()].sort((a, b) => a[0] - b[0]).map(([, v]) => v.sort((a, b) => a[1] - b[1]).map((x) => x[0]));
      const L = [...cards.values()].filter((c) => c.side === 'left');
      if (L.length) cols.push({ head: t('fp.col.callers'), cards: L.sort((a, b) => a.key < b.key ? -1 : 1) });
      ordered.forEach((list, i) => cols.push({ head: i === 0 && ordered.length > 1 ? t('fp.col.start') : i === ordered.length - 1 && ordered.length > 1 ? t('fp.col.shared') : t('fp.col.here'), cards: list }));
      const R = [...cards.values()].filter((c) => c.side === 'right');
      if (R.length) cols.push({ head: t('fp.col.callees'), cards: R.sort((a, b) => a.key < b.key ? -1 : 1) });
    }
    const tall = Math.max(1, ...cols.map((c) => c.cards.length));
    const H = HEAD + tall * (CARD_H + GAP_Y) - GAP_Y + PAD * 2;
    cols.forEach((col, i) => {
      const colH = col.cards.length * (CARD_H + GAP_Y) - GAP_Y, off = (H - HEAD - PAD * 2 - colH) / 2;
      col.x = PAD + i * (CARD_W + GAP_X);
      col.cards.forEach((c, j) => { c.x = col.x; c.y = PAD + HEAD + off + j * (CARD_H + GAP_Y); c.col = i; });
    });
    const W = PAD * 2 + cols.length * CARD_W + Math.max(0, cols.length - 1) * GAP_X;
    for (const c of cards.values()) {
      c.used = arr.filter((ar) => ar.b === c.key).reduce((s, ar) => s + ar.w, 0);
      c.uses = arr.filter((ar) => ar.a === c.key).reduce((s, ar) => s + ar.w, 0);
    }
    return { cards, cols, arrows: arr, W: Math.max(W, 320), H: Math.max(H, 240), more: heads.more || 0, level };
  }

  // ------------------------------------------------------------ drawing
  const pathD = (a, b) => {
    const ax = a.x + CARD_W, ay = a.y + CARD_H / 2, bx = b.x, by = b.y + CARD_H / 2;
    if (b.col > a.col) { const k = Math.max(40, (bx - ax) * 0.5); return `M${ax},${ay} C${ax + k},${ay} ${bx - k},${by} ${bx},${by}`; }
    if (b.col < a.col) { const k = Math.max(40, (ax - bx) * 0.5); const sx = a.x, ex = b.x + CARD_W; return `M${sx},${ay} C${sx - k},${ay} ${ex + k},${by} ${ex},${by}`; }
    const rx = ax + 56; return `M${ax},${ay} C${rx},${ay} ${rx},${by} ${b.x + CARD_W},${by}`;
  };
  const textOf = (c) => (ui.dev ? c.dev : c.title);
  const subOf = (c) => (ui.dev ? c.title : c.dev);

  function neighbours(key) {
    const s = new Set([key]);
    for (const ar of view.arrows) { if (ar.a === key) s.add(ar.b); if (ar.b === key) s.add(ar.a); }
    return s;
  }
  function paint() {
    const focus = hover || sel;
    const near = focus && view.cards.has(focus) ? neighbours(focus) : null;
    const q = ui.q.trim().toLowerCase();
    for (const node of world.querySelectorAll('.fp-card')) {
      const key = node.dataset.key, c = view.cards.get(key);
      node.classList.toggle('sel', key === sel);
      node.classList.toggle('dim', (near && !near.has(key)) || (!!q && !(c.title + ' ' + c.dev + ' ' + c.desc).toLowerCase().includes(q)));
    }
    hotPaths = [];
    for (const p of svg.querySelectorAll('.fp-edge')) {
      const hot = !!focus && (p.dataset.a === focus || p.dataset.b === focus);
      p.classList.toggle('hot', hot); p.classList.toggle('faint', !!focus && !hot);
      p.setAttribute('marker-end', hot ? 'url(#fp-arrow-hot)' : 'url(#fp-arrow)');
      if (hot) hotPaths.push(p); else p.removeAttribute('stroke-dashoffset');
    }
    for (const l of svg.querySelectorAll('.fp-count')) l.classList.toggle('faint', !!focus && l.dataset.a !== focus && l.dataset.b !== focus);
  }

  function renderWorld() {
    view = buildView();
    const { cards, cols, arrows, W, H } = view;
    svg = svgEl('svg', { class: 'fp-svg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, 'aria-hidden': 'true' },
      svgEl('defs', {}, ...[['fp-arrow', 'fp-head'], ['fp-arrow-hot', 'fp-head hot']].map(([id, cls]) => svgEl('marker', { id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, svgEl('path', { d: 'M0,0 L10,5 L0,10 z', class: cls })))));
    for (const ar of arrows) {
      const a = cards.get(ar.a), b = cards.get(ar.b);
      svg.append(svgEl('path', { class: 'fp-edge', d: pathD(a, b), 'data-a': ar.a, 'data-b': ar.b, 'stroke-width': (1.2 + Math.log2(ar.w + 1) * 0.8).toFixed(2), fill: 'none', 'marker-end': 'url(#fp-arrow)', 'data-testid': 'fp-edge' }));
      if (ar.w > 1) {
        const mx = b.col > a.col ? (a.x + CARD_W + b.x) / 2 : (a.x + b.x + CARD_W) / 2 + (b.col === a.col ? 60 : 0), my = (a.y + b.y + CARD_H) / 2;
        svg.append(svgEl('g', { class: 'fp-count', 'data-a': ar.a, 'data-b': ar.b }, svgEl('rect', { x: mx - 13, y: my - 9, width: 26, height: 18, rx: 9 }), svgEl('text', { x: mx, y: my + 4, 'text-anchor': 'middle' }, String(ar.w))));
      }
    }
    world = el('div', { class: 'fp-world', style: { width: W + 'px', height: H + 'px' } }, svg);
    for (const col of cols) world.append(el('div', { class: 'fp-lane-head mini', style: { left: col.x + 'px', top: PAD / 2 + 'px', width: CARD_W + 'px' } }, col.head));
    for (const c of cards.values()) {
      const reqs = (c.reqs || []).filter((id) => store.nodes.has(id)).slice(0, 3);
      const node = el('div', { class: 'fp-card ' + c.type, role: 'button', tabindex: '0', 'data-testid': 'fp-card', 'data-key': c.key, 'data-type': c.type, style: `left:${c.x}px;top:${c.y}px;width:${CARD_W}px;height:${CARD_H}px;--c:var(${c.c})`,
        'aria-label': `${textOf(c)}. ${c.stats}`,
        onclick: () => choose(c.key), ondblclick: () => c.open && go(c.open),
        onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); if (c.open && sel === c.key) go(c.open); else choose(c.key); } else if (e.key === ' ') { e.preventDefault(); choose(c.key); } },
        onpointerenter: () => { hover = c.key; paint(); }, onpointerleave: () => { hover = null; paint(); } },
      el('div', { class: 'fp-title' }, textOf(c)),
      el('div', { class: 'fp-sub mono' }, subOf(c)),
      el('div', { class: 'fp-desc' }, c.desc || c.stats),
      el('div', { class: 'fp-badges mini' }, c.desc ? el('span', {}, c.stats) : '', c.used ? el('span', { class: 'badge' }, t('fp.usedby', { n: c.used })) : '', c.uses ? el('span', { class: 'badge' }, t('fp.uses', { n: c.uses })) : '', ...reqs.map((id) => el('span', { class: 'badge' }, id))));
      world.append(node);
    }
    if (view.more > 0) world.append(el('div', { class: 'fp-more mini', style: { left: PAD + 'px', top: H - 24 + 'px' } }, t('fp.more', { n: view.more })));
    anim.replaceChildren(world);
    applyCam(); paint();
  }

  const applyCam = () => { world.style.transform = `translate(${cam.x}px, ${cam.y}px) scale(${cam.z})`; };
  function fit() {
    const r = stage.getBoundingClientRect();
    const byWidth = (r.width - 24) / view.W, byHeight = (r.height - 24) / view.H;
    cam.z = Math.min(1.15, Math.max(0.2, Math.min(byWidth, Math.max(byHeight, 0.62))));   // stay readable; a tall map is panned
    cam.x = (r.width - view.W * cam.z) / 2; cam.y = view.H * cam.z < r.height ? (r.height - view.H * cam.z) / 2 : 8;
    applyCam();
  }

  // ------------------------------------------------------------ navigation and the side panel
  function syncUrl() {
    const p = new URLSearchParams();
    if (path[0]) p.set('g', path[0]);
    if (path[1]) p.set('f', path[1]);
    if (sel) p.set('sel', sel);
    history.replaceState(null, '', '#/floorplan' + (p.toString() ? '?' + p : ''));
  }
  function go(next, { select = null, dir } = {}) {
    const deeper = next.length > path.length;
    path = next; sel = select; hover = null;
    renderWorld(); fit(); renderCrumbs(); renderSide(); syncUrl();
    if (!reduced()) anim.animate([{ opacity: 0, transform: `scale(${(dir || (deeper ? 'in' : 'out')) === 'in' ? 1.16 : 0.88})` }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'ease-out' });
  }
  function choose(key) {
    sel = sel === key ? null : key;
    paint(); renderSide(); syncUrl();
  }
  function renderCrumbs() {
    const parts = [{ label: t('fp.crumb.root'), path: [] }];
    if (path[0]) parts.push({ label: humanize(last(path[0], 1) === '.' ? 'root' : last(path[0], 1)), path: [path[0]] });
    if (path[1]) parts.push({ label: humanize(path[1].split('/').pop()), path: [path[0], path[1]] });
    crumbs.replaceChildren(...parts.flatMap((p, i) => [i ? el('span', { class: 'mini' }, '›') : '', el('button', { type: 'button', class: 'chip', 'data-testid': 'fp-crumb', 'aria-current': i === parts.length - 1 ? 'page' : null, onclick: () => i < parts.length - 1 && go(p.path) }, p.label)]));
  }
  function linkList(title, list) {
    return el('div', { class: 'cg-rel' }, el('h3', {}, `${title} (${list.length})`),
      list.length ? el('div', { class: 'cg-rel-list' }, ...list.slice(0, 40).map(({ c, w }) => el('button', { type: 'button', class: 'cg-sym', onclick: () => (view.cards.has(c.key) ? choose(c.key) : null) },
        el('span', { class: 'cg-name' }, textOf(c)), el('small', { class: 'mini' }, ` ×${w}`)))) : el('div', { class: 'mini' }, t('cg.none')));
  }
  function renderSide() {
    const c = sel && view.cards.get(sel);
    if (!c) {
      const what = path.length === 0 ? t('fp.summary.root', { parts: groups.size, files: data.stats.files, funcs: data.stats.nodes }) : path.length === 1 ? groups.get(path[0])?.doc || '' : clean(fileInfo.get(path[1])?.doc);
      side.replaceChildren(el('h2', {}, path.length ? textOfPath() : t('fp.title')), el('p', {}, what), el('p', { class: 'mini' }, t('fp.hint')),
        el('p', { class: 'mini' }, t('cg.stats', { nodes: data.stats.nodes, edges: data.stats.edges, files: data.stats.files, shown: view.cards.size, unresolved: data.stats.unresolved })));
      return;
    }
    const usedBy = view.arrows.filter((ar) => ar.b === c.key).map((ar) => ({ c: view.cards.get(ar.a), w: ar.w })).sort((a, b) => b.w - a.w);
    const uses = view.arrows.filter((ar) => ar.a === c.key).map((ar) => ({ c: view.cards.get(ar.b), w: ar.w })).sort((a, b) => b.w - a.w);
    const reqs = (c.reqs || []).filter((id) => store.nodes.has(id));
    const n = c.node;
    side.replaceChildren(
      el('h2', { 'data-testid': 'fp-name' }, textOf(c)), el('div', { class: 'mono mini' }, subOf(c)),
      el('p', {}, c.desc || c.stats), c.desc ? el('div', { class: 'mini' }, c.stats) : '',
      c.open ? el('p', {}, el('button', { type: 'button', class: 'btn', 'data-testid': 'fp-open', onclick: () => go(c.open) }, t('fp.open'))) : '',
      n ? el('div', { class: 'mini' }, t('cg.file') + ': ', el('a', { class: 'mono', href: vscodeUrl(n.file, n.line), title: t('cg.vscode') }, `${n.file}:${n.line}`)) : '',
      c.type === 'file' ? el('div', { class: 'mini' }, el('a', { class: 'mono', href: vscodeUrl(c.key), title: t('cg.vscode') }, c.key)) : '',
      reqs.length ? el('div', { class: 'mini cg-reqs' }, t('cg.reqs') + ': ', ...reqs.map((id) => el('a', { class: 'chip', href: '#/map2d?select=' + encodeURIComponent(id) }, id))) : '',
      linkList(t('fp.usedby.h'), usedBy), linkList(t('fp.uses.h'), uses));
  }
  const textOfPath = () => (path.length === 1 ? humanize(last(path[0], 1) === '.' ? 'root' : last(path[0], 1)) : humanize(path[1].split('/').pop()));

  // ------------------------------------------------------------ search across everything
  function matchesAll(q) {
    q = q.trim().toLowerCase();
    if (!q) return [];
    const hits = [];
    for (const g of groups.values()) if (g.key.toLowerCase().includes(q)) hits.push({ label: g.key, path: [g.key], sel: g.key, kind: 'group' });
    for (const f of data.files) if (f.path.toLowerCase().includes(q)) hits.push({ label: f.path, path: [groupOf(f.path)], sel: f.path, kind: 'file' });
    for (const n of data.nodes) if (n.kind !== 'module' && n.qual.toLowerCase().includes(q)) hits.push({ label: `${n.qual}  ${last(n.file, 1)}`, path: [groupOf(n.file), n.file], sel: n.id, kind: n.kind });
    hits.sort((a, b) => (a.label.toLowerCase().startsWith(q) ? 0 : 1) - (b.label.toLowerCase().startsWith(q) ? 0 : 1));
    return hits.slice(0, 8);
  }
  function renderSugg() {
    const hits = matchesAll(ui.q);
    sugg.replaceChildren(...hits.map((h) => el('button', { type: 'button', class: 'cg-sym', 'data-testid': 'fp-hit', onclick: () => { ui.q = ''; searchBox.value = ''; sugg.replaceChildren(); go(h.path, { select: h.sel, dir: 'in' }); } },
      el('span', { class: 'cg-name mono' }, h.label), el('small', { class: 'mini' }, ' ' + (h.kind === 'group' || h.kind === 'file' ? t('fp.kind.' + h.kind) : t('cg.kind.' + h.kind))))));
  }

  // ------------------------------------------------------------ page
  function bindStage() {
    let pan = null, moved = 0;
    stage.addEventListener('pointerdown', (e) => { if (e.target.closest('.fp-card')) return; pan = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y }; moved = 0; stage.setPointerCapture?.(e.pointerId); });
    stage.addEventListener('pointermove', (e) => { if (!pan) return; moved++; cam.x = pan.cx + e.clientX - pan.x; cam.y = pan.cy + e.clientY - pan.y; applyCam(); });
    const end = () => { if (pan && moved < 3 && sel) { sel = null; paint(); renderSide(); syncUrl(); } pan = null; };
    stage.addEventListener('pointerup', end); stage.addEventListener('pointercancel', () => { pan = null; });
    stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = stage.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top;
      const z = Math.min(2.5, Math.max(0.15, cam.z * Math.exp(-e.deltaY * 0.0016)));
      cam.x = px - (px - cam.x) * (z / cam.z); cam.y = py - (py - cam.y) * (z / cam.z); cam.z = z; applyCam();
    }, { passive: false });
    stage.addEventListener('dblclick', (e) => { if (!e.target.closest('.fp-card')) fit(); });
    stage.addEventListener('keydown', (e) => { if (e.key === 'Escape') { if (sel) { sel = null; paint(); renderSide(); syncUrl(); } else if (path.length) go(path.slice(0, -1)); } });
  }
  function flow(now) {
    if (destroyed) return;
    raf = requestAnimationFrame(flow);
    if (reduced() || document.hidden) return;
    const off = -((now * 0.035) % 14);
    for (const p of hotPaths) p.setAttribute('stroke-dashoffset', String(off));
  }

  function render() {
    stage = el('div', { class: 'fp-stage', 'data-testid': 'fp-stage', tabindex: '-1' });
    anim = el('div', { class: 'fp-anim' });
    stage.append(anim);
    side = el('aside', { class: 'card fp-side', 'data-testid': 'fp-side', 'aria-live': 'polite' });
    crumbs = el('nav', { class: 'row fp-crumbs', 'aria-label': t('fp.crumb.root') });
    sugg = el('div', { class: 'fp-sugg' });
    searchBox = el('input', { type: 'search', 'data-testid': 'fp-search', placeholder: t('fp.search'), 'aria-label': t('fp.search'), value: ui.q,
      oninput: (e) => { ui.q = e.target.value; renderSugg(); paint(); },
      onkeydown: (e) => { if (e.key === 'Enter') { const h = matchesAll(ui.q)[0]; if (h) { ui.q = ''; searchBox.value = ''; sugg.replaceChildren(); go(h.path, { select: h.sel, dir: 'in' }); } } } });
    page.replaceChildren(el('h1', {}, t('fp.title')), el('p', { class: 'sub' }, t('fp.sub')),
      el('div', { class: 'tbar cg-bar' }, crumbs, el('div', { class: 'fp-search' }, searchBox, sugg),
        el('label', { class: 'row mini cg-toggle' }, el('input', { type: 'checkbox', 'data-testid': 'fp-dev', checked: ui.dev || null, onchange: (e) => { ui.dev = e.target.checked; renderWorld(); renderSide(); } }), t('fp.dev')),
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'fp-fit', onclick: fit }, t('cg.fit')),
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'fp-up', onclick: () => path.length && go(path.slice(0, -1)) }, t('fp.up')),
        el('a', { class: 'btn ghost', href: '#/codegraph', 'data-testid': 'open-network' }, t('fp.network'))),
      el('div', { class: 'cg-body' }, stage, side));
    bindStage();
    renderWorld(); fit(); renderCrumbs(); renderSide();
  }

  const state = () => ({ level: path.length, path: [...path], cards: view ? view.cards.size : 0, arrows: view ? view.arrows.length : 0, selected: sel, dev: ui.dev });
  const viewApi = { mode: 'floorplan', getState: state, open: (p, s) => go(p, { select: s }), select: (k) => choose(k) };
  window.eabkView = viewApi;
  const offLang = onLang(() => { if (data) { render(); } });
  load().then((ok) => {
    if (!ok || destroyed) return;
    const p = new URLSearchParams(location.hash.split('?')[1] || '');
    if (p.get('g') && groups.has(p.get('g'))) { path = [p.get('g')]; if (p.get('f') && fileInfo.has(p.get('f'))) path.push(p.get('f')); }
    render();
    if (p.get('sel') && view.cards.has(p.get('sel'))) { sel = p.get('sel'); paint(); renderSide(); }
    raf = requestAnimationFrame(flow);
  });
  return { destroy() { destroyed = true; cancelAnimationFrame(raf); offLang(); if (window.eabkView === viewApi) window.eabkView = undefined; } };
}
