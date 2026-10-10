// Requirement-engineering diagrams drawn only from the EABK data layer:
// context diagram, goal tree, state-transition diagrams, entity relation diagram, component diagram.
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, svgEl, colorOf, TYPE_COLOR, STATUS_COLOR, showTip, hideTip, nodeTip, nodeChip, statusText } from './ui.js';

const KINDS = ['ctx', 'goals', 'states', 'entities', 'components'];
let kind = 'ctx';
let entThreshold = 0;
let goalColor = 'impl';
const IMPL_COLOR = { done: '#34e0a1', none: '#3a4a78', unlisted: '#8aa1b5' };

const textW = (s) => [...String(s)].reduce((w, ch) => w + (ch.charCodeAt(0) > 255 ? 13 : 7.2), 0);
const cut = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));

function defs() {
  const d = svgEl('defs');
  const mk = (id, color) => d.append(svgEl('marker', { id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }, svgEl('path', { d: 'M0 0 10 5 0 10z', fill: color })));
  mk('arr', '#8fa6e8'); mk('arrh', '#39d0ff');
  const g = svgEl('filter', { id: 'glow', x: '-30%', y: '-30%', width: '160%', height: '160%' }, svgEl('feGaussianBlur', { stdDeviation: 3, result: 'b' }), svgEl('feMerge', {}, svgEl('feMergeNode', { in: 'b' }), svgEl('feMergeNode', { in: 'SourceGraphic' })));
  d.append(g);
  return d;
}

function bindNode(g, id) {
  g.classList.add('node-g');
  g.dataset.id = id;
  g.addEventListener('click', (e) => { e.stopPropagation(); store.select(id, { fly: true }); });
  g.addEventListener('mouseenter', (e) => { const n = store.node(id); store.setHover(id); if (n) showTip(nodeTip(n), e.clientX, e.clientY); });
  g.addEventListener('mousemove', (e) => { const n = store.node(id); if (n) showTip(nodeTip(n), e.clientX, e.clientY); });
  g.addEventListener('mouseleave', () => { store.setHover(null); hideTip(); });
}

function applyDim(root) {
  const hov = store.hover ? store.related(store.hover, 1) : null;
  const set = hov || store.activeSet();
  root.querySelectorAll('[data-id]').forEach((n) => n.classList.toggle('dim', !!set && !set.has(n.dataset.id) && !(n.dataset.ids && n.dataset.ids.split('|').some((x) => set.has(x)))));
  root.querySelectorAll('[data-a]').forEach((n) => {
    const hi = set && set.has(n.dataset.a) && set.has(n.dataset.b);
    n.classList.toggle('dim', !!set && !hi);
    if (n.tagName === 'path' || n.tagName === 'line') n.setAttribute('marker-end', hi ? 'url(#arrh)' : n.dataset.arrow ? 'url(#arr)' : '');
  });
  root.querySelectorAll('[data-sel]').forEach((n) => n.setAttribute('stroke-width', n.dataset.id === store.selected ? 3.5 : 1.5));
}

// ---------------------------------------------------------------- context diagram
function contextDiagram(m) {
  const P = m.personas, X = m.integrations;
  const rows = Math.max(P.length, X.length, 1), Hh = rows * 120 + 140, Ww = 1180;
  const svg = svgEl('svg', { viewBox: `0 0 ${Ww} ${Hh}`, width: Ww, height: Hh, style: 'max-width:100%' }, defs());
  const cx = Ww / 2, cy = Hh / 2;
  const sysW = 260, sysH = Math.max(150, rows * 60);
  svg.append(svgEl('rect', { x: cx - sysW / 2, y: cy - sysH / 2, width: sysW, height: sysH, rx: 22, fill: 'rgba(57,208,255,.1)', stroke: '#39d0ff', 'stroke-width': 2, filter: 'url(#glow)' }));
  svg.append(svgEl('text', { x: cx, y: cy - 14, 'text-anchor': 'middle', 'font-size': 20, 'font-weight': 700, fill: '#fff' }, cut(m.meta.name, 22)));
  svg.append(svgEl('text', { x: cx, y: cy + 8, 'text-anchor': 'middle', 'font-size': 12, fill: '#9aa9c9' }, t('ctx.system')));
  m.goals.forEach((g, i) => {
    const gx = cx - sysW / 2 + 22 + (i % 3) * 78, gy = cy + 28 + Math.floor(i / 3) * 24;
    const gg = svgEl('g', {}, svgEl('rect', { x: gx, y: gy - 12, width: 68, height: 20, rx: 10, fill: 'rgba(255,176,32,.18)', stroke: TYPE_COLOR.goal }), svgEl('text', { x: gx + 34, y: gy + 3, 'text-anchor': 'middle', 'font-size': 11, fill: '#ffd58a' }, g.id));
    bindNode(gg, g.id); svg.append(gg);
  });
  const place = (list, x, side) => list.map((it, i) => ({ it, x, y: (Hh / (list.length + 1)) * (i + 1), side }));
  const pp = place(P, 140, 'l'), xx = place(X, Ww - 140, 'r');
  const sx = (side) => (side === 'l' ? cx - sysW / 2 : cx + sysW / 2);
  for (const { it, x, y, side } of [...pp, ...xx]) {
    const id = side === 'l' ? `persona:${it.name}` : `ext:${it.name}`;
    const label = it.name;
    const line = svgEl('line', { x1: side === 'l' ? x + 74 : x - 74, y1: y, x2: sx(side) + (side === 'l' ? -4 : 4), y2: cy + Math.max(-sysH / 2 + 20, Math.min(sysH / 2 - 20, (y - cy) * 0.5)), stroke: '#8fa6e8', 'stroke-width': 1.6, 'marker-end': 'url(#arr)', 'data-a': id, 'data-b': id, 'data-arrow': 1 });
    if (side === 'r') line.setAttribute('marker-start', 'url(#arr)');
    svg.append(line);
    const mx = (parseFloat(line.getAttribute('x1')) + parseFloat(line.getAttribute('x2'))) / 2, my = (parseFloat(line.getAttribute('y1')) + parseFloat(line.getAttribute('y2'))) / 2;
    svg.append(svgEl('text', { x: mx, y: my - 6, 'text-anchor': 'middle', 'font-size': 11, fill: '#b4c2e4', style: 'paint-order:stroke;stroke:#070b16;stroke-width:5px;stroke-linejoin:round' }, cut(side === 'l' ? it.work : it.method, 24)));
    const w = Math.max(150, textW(cut(label, 22)) + 30), g = svgEl('g', {});
    if (side === 'l') { g.append(svgEl('circle', { cx: x, cy: y - 28, r: 11, fill: 'none', stroke: TYPE_COLOR.persona, 'stroke-width': 2 }), svgEl('path', { d: `M${x} ${y - 17}v22M${x - 16} ${y - 10}h32M${x} ${y + 5}l-13 18M${x} ${y + 5}l13 18`, stroke: TYPE_COLOR.persona, 'stroke-width': 2, fill: 'none', 'stroke-linecap': 'round' })); g.append(svgEl('text', { x, y: y + 42, 'text-anchor': 'middle', 'font-size': 12.5, fill: '#fff' }, cut(label, 16))); }
    else { g.append(svgEl('rect', { x: x - w / 2, y: y - 26, width: w, height: 52, rx: 10, fill: 'rgba(125,211,252,.1)', stroke: TYPE_COLOR.external, 'stroke-width': 1.6, 'data-sel': 1, 'data-id': id }), svgEl('text', { x, y: y + 4, 'text-anchor': 'middle', 'font-size': 12.5, fill: '#fff' }, cut(label, 22))); g.append(svgEl('title', {}, it.meaning)); }
    bindNode(g, id);
    svg.append(g);
  }
  if (!P.length && !X.length) svg.append(svgEl('text', { x: cx, y: 60, 'text-anchor': 'middle', fill: '#9aa9c9' }, t('none')));
  return svg;
}

// ---------------------------------------------------------------- goal tree
function goalTree(m) {
  const goals = m.goals;
  const colW = 300, chip = 17, gap = 4, perRow = 12;
  const ungrouped = m.reqs.filter((r) => !goals.find((g) => g.id === r.goal));
  const cols = [...goals.map((g) => ({ g, rs: m.reqs.filter((r) => r.goal === g.id) }))];
  if (ungrouped.length) cols.push({ g: { id: '', title: t('goals.none') }, rs: ungrouped });
  const Ww = Math.max(900, cols.length * colW + 60);
  const maxRows = Math.max(1, ...cols.map((c) => Math.ceil(c.rs.length / perRow)));
  const Hh = 220 + maxRows * (chip + gap) + 40;
  const svg = svgEl('svg', { viewBox: `0 0 ${Ww} ${Hh}`, width: Ww, height: Hh }, defs());
  const rx = Ww / 2;
  svg.append(svgEl('rect', { x: rx - 110, y: 14, width: 220, height: 40, rx: 12, fill: 'rgba(57,208,255,.12)', stroke: '#39d0ff' }), svgEl('text', { x: rx, y: 40, 'text-anchor': 'middle', 'font-size': 15, 'font-weight': 700, fill: '#fff' }, cut(m.meta.name, 24)));
  cols.forEach(({ g, rs }, i) => {
    const x = 30 + i * colW, gw = colW - 24;
    svg.append(svgEl('path', { d: `M${rx} 54 C${rx} 90 ${x + gw / 2} 70 ${x + gw / 2} 100`, stroke: '#5a70b5', fill: 'none', 'stroke-width': 1.5, 'data-a': g.id || 'x', 'data-b': g.id || 'x' }));
    const gg = svgEl('g', {}, svgEl('rect', { x, y: 100, width: gw, height: 84, rx: 12, fill: 'rgba(255,176,32,.1)', stroke: TYPE_COLOR.goal, 'stroke-width': 1.5, 'data-sel': 1, 'data-id': g.id }),
      svgEl('text', { x: x + 12, y: 124, 'font-size': 14, 'font-weight': 700, fill: '#ffd58a' }, g.id || '—'));
    const words = String(g.title || '');
    [0, 1, 2].forEach((ln) => gg.append(svgEl('text', { x: x + 12, y: 144 + ln * 15, 'font-size': 11.5, fill: '#c9d6f5' }, words.slice(ln * 21, ln * 21 + 21) + (ln === 2 && words.length > 63 ? '…' : ''))));
    gg.append(svgEl('title', {}, words));
    if (g.id) bindNode(gg, g.id);
    svg.append(gg);
    rs.forEach((r, j) => {
      const n = store.node(r.id);
      const cxp = x + (j % perRow) * (chip + gap), cyp = 204 + Math.floor(j / perRow) * (chip + gap);
      const col = goalColor === 'status' ? STATUS_COLOR[r.statusKind] : IMPL_COLOR[n?.impl] || '#8aa1b5';
      const c = svgEl('g', {}, svgEl('rect', { x: cxp, y: cyp, width: chip, height: chip, rx: 4, fill: col, opacity: 0.9, stroke: r.kind === 'NFR' ? '#2fd3c9' : 'none', 'stroke-width': 2 }));
      bindNode(c, r.id); svg.append(c);
    });
    svg.append(svgEl('text', { x, y: 204 + maxRows * (chip + gap) + 16, 'font-size': 11, fill: '#9aa9c9' }, `${rs.length} ${t('type.req')}`));
  });
  return svg;
}

// ---------------------------------------------------------------- state diagrams
function stateDiagram(sm) {
  const inc = new Map(sm.states.map((s) => [s, 0])), out = new Map(sm.states.map((s) => [s, 0]));
  for (const tr of sm.transitions) { inc.set(tr.to, (inc.get(tr.to) || 0) + 1); out.set(tr.from, (out.get(tr.from) || 0) + 1); }
  const starts = sm.states.filter((s) => !inc.get(s));
  if (!starts.length && sm.states.length) starts.push(sm.states[0]);
  const depth = new Map(), q = [...starts];
  starts.forEach((s) => depth.set(s, 0));
  while (q.length) { const s = q.shift(); for (const tr of sm.transitions) if (tr.from === s && !depth.has(tr.to)) { depth.set(tr.to, depth.get(s) + 1); q.push(tr.to); } }
  sm.states.forEach((s) => { if (!depth.has(s)) depth.set(s, 0); });
  const cols = [];
  sm.states.forEach((s) => (cols[depth.get(s)] ||= []).push(s));
  const widths = new Map(sm.states.map((s) => [s, Math.max(76, textW(s) + 28)]));
  const colWs = cols.map((c) => Math.max(...(c || [0]).map((s) => widths.get(s) || 0)));
  const pos = new Map(); let x = 60;
  const maxRows = Math.max(...cols.map((c) => (c || []).length), 1);
  cols.forEach((c, i) => { (c || []).forEach((s, j) => pos.set(s, { x, y: 60 + j * 62 + ((maxRows - c.length) * 62) / 2, w: colWs[i] })); x += colWs[i] + 90; });
  const Ww = x + 10, Hh = 60 + maxRows * 62 + 50;
  const svg = svgEl('svg', { viewBox: `0 0 ${Ww} ${Hh}`, width: Ww, height: Hh, style: 'max-width:100%' }, defs());
  for (const s of starts) { const p = pos.get(s); svg.append(svgEl('circle', { cx: p.x - 30, cy: p.y + 20, r: 6, fill: '#8fa6e8' }), svgEl('line', { x1: p.x - 24, y1: p.y + 20, x2: p.x - 2, y2: p.y + 20, stroke: '#8fa6e8', 'stroke-width': 1.5, 'marker-end': 'url(#arr)' })); }
  const eid = `ent:${sm.entity}`;
  for (const tr of sm.transitions) {
    const a = pos.get(tr.from), b = pos.get(tr.to); if (!a || !b) continue;
    let d, lx, ly;
    if (b.x > a.x) { const x1 = a.x + a.w, y1 = a.y + 20, x2 = b.x, y2 = b.y + 20; d = `M${x1} ${y1} C${x1 + 45} ${y1} ${x2 - 45} ${y2} ${x2 - 2} ${y2}`; lx = (x1 + x2) / 2; ly = (y1 + y2) / 2 - 6; }
    else { const x1 = a.x + a.w / 2, y1 = a.y + 40, x2 = b.x + b.w / 2, y2 = b.y + 40, dy = 44 + Math.abs(a.x - b.x) / 8; d = `M${x1} ${y1} C${x1} ${y1 + dy} ${x2} ${y2 + dy} ${x2} ${y2 + 2}`; lx = (x1 + x2) / 2; ly = Math.max(y1, y2) + dy * 0.72; }
    svg.append(svgEl('path', { d, fill: 'none', stroke: '#8fa6e8', 'stroke-width': 1.6, 'marker-end': 'url(#arr)', 'data-a': eid, 'data-b': eid, 'data-arrow': 1 }, tr.label ? svgEl('title', {}, tr.label) : null));
  }
  for (const s of sm.states) {
    const p = pos.get(s), fin = !out.get(s);
    const g = svgEl('g', {}, svgEl('rect', { x: p.x, y: p.y, width: p.w, height: 40, rx: 14, fill: 'rgba(179,107,255,.16)', stroke: fin ? '#ff8a5c' : '#b36bff', 'stroke-width': fin ? 2.4 : 1.5 }),
      svgEl('text', { x: p.x + p.w / 2, y: p.y + 25, 'text-anchor': 'middle', 'font-size': 12.5, fill: '#fff' }, s));
    if (fin) g.append(svgEl('rect', { x: p.x + 4, y: p.y + 4, width: p.w - 8, height: 32, rx: 10, fill: 'none', stroke: '#ff8a5c', 'stroke-opacity': 0.5 }));
    svg.append(g);
  }
  return svg;
}

function statesView(m) {
  const wrap = el('div', { style: { display: 'grid', gap: '16px' } });
  if (!m.stateMachines.length) return el('div', { class: 'empty' }, t('states.none'));
  for (const sm of m.stateMachines) {
    const eid = `ent:${sm.entity}`;
    const reqs = store.neighbors(eid, ['req']).map((x) => x.id);
    const card = el('div', { class: 'card', 'data-id': eid },
      el('div', { class: 'row', style: { justifyContent: 'space-between', marginBottom: '8px' } },
        el('b', { style: { cursor: 'pointer', color: TYPE_COLOR.entity }, onclick: () => store.select(eid, { fly: true }) }, sm.entity),
        el('span', { class: 'mini' }, `${sm.states.length} ${t('states.states')} · ${sm.transitions.length} ${t('states.trans')}`)),
      el('div', { style: { overflow: 'auto' } }, stateDiagram(sm)),
      reqs.length ? el('div', { class: 'row', style: { marginTop: '8px' } }, el('span', { class: 'mini' }, t('states.reqs')), reqs.slice(0, 24).map((id) => nodeChip(id)), reqs.length > 24 ? el('span', { class: 'mini' }, '+' + (reqs.length - 24)) : '') : '');
    wrap.append(card);
  }
  return wrap;
}

// ---------------------------------------------------------------- entity relation
function entityDiagram(m, host) {
  const ents = [...store.nodes.values()].filter((n) => n.type === 'entity' && n.deg > 0);
  if (!ents.length) return el('div', { class: 'empty' }, t('none'));
  const co = new Map();
  for (const r of m.reqs) {
    const ids = [...new Set(store.neighbors(r.id, ['entity']).map((x) => x.id))];
    for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) { const k = ids[i] < ids[j] ? ids[i] + '\u0001' + ids[j] : ids[j] + '\u0001' + ids[i]; co.set(k, (co.get(k) || 0) + 1); }
  }
  const all = [...co.entries()].map(([k, w]) => { const [a, b] = k.split('\u0001'); return { a, b, w }; }).sort((x, y) => y.w - x.w);
  const maxW = all[0]?.w || 1;
  if (!entThreshold) entThreshold = Math.max(1, all.length > 140 ? all[139].w : 1);
  const edges = all.filter((e) => e.w >= entThreshold);
  const Ww = 1100, Hh = 760;
  const pos = new Map(ents.map((n, i) => [n.id, { x: Ww / 2 + Math.cos(i / ents.length * 6.283) * 300, y: Hh / 2 + Math.sin(i / ents.length * 6.283) * 260, vx: 0, vy: 0 }]));
  for (let it = 0; it < 260; it++) {
    const cool = 1 - it / 260;
    for (const a of ents) for (const b of ents) {
      if (a === b) continue; const pa = pos.get(a.id), pb = pos.get(b.id);
      let dx = pa.x - pb.x, dy = pa.y - pb.y, d2 = dx * dx + dy * dy + 0.1; const d = Math.sqrt(d2);
      const f = 5200 / d2; pa.vx += (dx / d) * f; pa.vy += (dy / d) * f;
    }
    for (const e of edges) {
      const pa = pos.get(e.a), pb = pos.get(e.b); if (!pa || !pb) continue;
      const dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.hypot(dx, dy) || 1, f = (d - 130) * 0.012 * Math.min(3, 1 + e.w / 4);
      pa.vx += (dx / d) * f; pa.vy += (dy / d) * f; pb.vx -= (dx / d) * f; pb.vy -= (dy / d) * f;
    }
    for (const p of pos.values()) { p.vx += (Ww / 2 - p.x) * 0.004; p.vy += (Hh / 2 - p.y) * 0.004; p.x += Math.max(-14, Math.min(14, p.vx)) * cool; p.y += Math.max(-14, Math.min(14, p.vy)) * cool; p.vx *= 0.6; p.vy *= 0.6; p.x = Math.max(70, Math.min(Ww - 70, p.x)); p.y = Math.max(30, Math.min(Hh - 30, p.y)); }
  }
  const wOf = (n) => Math.max(60, textW(n.label) + 22);
  for (let it = 0; it < 60; it++) for (let i = 0; i < ents.length; i++) for (let j = i + 1; j < ents.length; j++) {
    const a = pos.get(ents[i].id), b = pos.get(ents[j].id), dx = b.x - a.x, dy = b.y - a.y, ox = (wOf(ents[i]) + wOf(ents[j])) / 2 + 12 - Math.abs(dx), oy = 40 - Math.abs(dy);
    if (ox > 0 && oy > 0) { if (oy < ox) { const m = (dy >= 0 ? 1 : -1) * oy / 2; a.y -= m; b.y += m; } else { const m = (dx >= 0 ? 1 : -1) * ox / 2; a.x -= m; b.x += m; } }
  }
  const svg = svgEl('svg', { viewBox: `0 0 ${Ww} ${Hh}`, width: Ww, height: Hh, style: 'max-width:100%' }, defs());
  for (const e of edges) { const a = pos.get(e.a), b = pos.get(e.b); if (!a || !b) continue; svg.append(svgEl('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, stroke: '#7f9bff', 'stroke-opacity': 0.25 + 0.5 * (e.w / maxW), 'stroke-width': 1 + 4 * (e.w / maxW), 'data-a': e.a, 'data-b': e.b }, svgEl('title', {}, `${store.node(e.a).label} — ${store.node(e.b).label}: ${e.w}`))); }
  for (const n of ents) {
    const p = pos.get(n.id), w = Math.max(60, textW(n.label) + 22);
    const g = svgEl('g', {}, svgEl('rect', { x: p.x - w / 2, y: p.y - 15, width: w, height: 30, rx: 8, fill: 'rgba(255,138,92,.15)', stroke: TYPE_COLOR.entity, 'stroke-width': 1.5, 'data-id': n.id, 'data-sel': 1 }), svgEl('text', { x: p.x, y: p.y + 4.5, 'text-anchor': 'middle', 'font-size': 12, fill: '#fff' }, n.label));
    if (n.states) g.append(svgEl('circle', { cx: p.x + w / 2, cy: p.y - 15, r: 8, fill: '#b36bff' }), svgEl('text', { x: p.x + w / 2, y: p.y - 12, 'text-anchor': 'middle', 'font-size': 9.5, fill: '#fff' }, n.states));
    bindNode(g, n.id); svg.append(g);
  }
  const ctrl = el('div', { class: 'row', style: { marginBottom: '10px' } }, el('span', { class: 'mini' }, t('ent.threshold')),
    el('input', { type: 'range', min: 1, max: Math.max(2, maxW), value: entThreshold, oninput: (e) => { entThreshold = +e.target.value; host.replaceChildren(entityDiagram(m, host)); applyDim(host); } }), el('b', {}, '≥ ' + entThreshold), el('span', { class: 'mini' }, `(${edges.length}/${all.length} ${t('ent.links')})`));
  return el('div', {}, ctrl, el('div', { style: { overflow: 'auto' } }, svg));
}

// ---------------------------------------------------------------- component diagram
function componentDiagram(m) {
  const comps = [...store.nodes.values()].filter((n) => n.type === 'component');
  if (!comps.length) return el('div', { class: 'empty' }, t('none'));
  const files = [...store.nodes.values()].filter((n) => n.type === 'file');
  const byComp = new Map(comps.map((c) => [c.path, { c, mods: new Map(), reqs: new Set(), parts: [], data: [] }]));
  for (const f of files) { const e = byComp.get(f.comp); if (!e) continue; const mm = e.mods.get(f.module) || { files: 0, test: 0 }; mm.files++; if (f.role === 'test') mm.test++; e.mods.set(f.module, mm); for (const a of store.adj.get(f.id) || []) if (store.node(a.id)?.type === 'req') e.reqs.add(a.id); }
  for (const n of store.nodes.values()) if (['part', 'api', 'table'].includes(n.type)) for (const a of store.adj.get(n.id) || []) { const f = store.node(a.id); if (f?.type === 'file') { const e = byComp.get(f.comp); if (e && !e.parts.includes(n)) e.parts.push(n); } }
  const list = [...byComp.values()].filter((e) => e.reqs.size || e.mods.size).sort((a, b) => (a.c.kind === 'test') - (b.c.kind === 'test') || b.reqs.size - a.reqs.size);
  const bw = 300, perRow = Math.min(4, Math.max(2, Math.ceil(Math.sqrt(list.length))));
  const heights = list.map((e) => 70 + e.mods.size * 22 + (e.parts.length ? 26 + Math.ceil(e.parts.length / 2) * 20 : 0));
  const rowsH = []; list.forEach((_, i) => { const r = Math.floor(i / perRow); rowsH[r] = Math.max(rowsH[r] || 0, heights[i]); });
  const rowY = []; let y = 30; rowsH.forEach((h, r) => { rowY[r] = y; y += h + 60; });
  const Ww = perRow * (bw + 80) + 20, Hh = y + 10;
  const svg = svgEl('svg', { viewBox: `0 0 ${Ww} ${Hh}`, width: Ww, height: Hh }, defs());
  const place = new Map(list.map((e, i) => [e.c.id, { x: 30 + (i % perRow) * (bw + 80), y: rowY[Math.floor(i / perRow)], h: heights[i] }]));
  const links = [];
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) { let w = 0; for (const r of list[i].reqs) if (list[j].reqs.has(r)) w++; if (w) links.push({ a: list[i].c.id, b: list[j].c.id, w }); }
  const maxW = Math.max(1, ...links.map((l) => l.w));
  for (const l of links.sort((p, q) => p.w - q.w)) {
    const a = place.get(l.a), b = place.get(l.b);
    const x1 = a.x + bw / 2, y1 = a.y + a.h / 2, x2 = b.x + bw / 2, y2 = b.y + b.h / 2;
    svg.append(svgEl('path', { d: `M${x1} ${y1} Q${(x1 + x2) / 2} ${(y1 + y2) / 2 - 50} ${x2} ${y2}`, fill: 'none', stroke: '#7f9bff', 'stroke-opacity': 0.18 + 0.5 * l.w / maxW, 'stroke-width': 1 + 6 * l.w / maxW, 'data-a': l.a, 'data-b': l.b }, svgEl('title', {}, `${l.w} ${t('comp.shared')}`)));
  }
  for (const e of list) {
    const p = place.get(e.c.id), test = e.c.kind === 'test';
    const g = svgEl('g', {}, svgEl('rect', { x: p.x, y: p.y, width: bw, height: p.h, rx: 16, fill: test ? 'rgba(126,231,168,.07)' : 'rgba(57,208,255,.08)', stroke: test ? TYPE_COLOR.test : '#39d0ff', 'stroke-width': 1.5, 'data-id': e.c.id, 'data-sel': 1 }));
    g.append(svgEl('text', { x: p.x + 16, y: p.y + 28, 'font-size': 14.5, 'font-weight': 700, fill: '#fff' }, '⬢ ' + cut(e.c.label, 30)), svgEl('text', { x: p.x + 16, y: p.y + 46, 'font-size': 11, fill: '#9aa9c9' }, `${e.reqs.size} ${t('type.req')} · ${[...e.mods.values()].reduce((s, v) => s + v.files, 0)} ${t('type.file')}`));
    let yy = p.y + 66;
    for (const [mod, v] of e.mods) { g.append(svgEl('rect', { x: p.x + 14, y: yy - 12, width: bw - 28, height: 18, rx: 6, fill: 'rgba(120,150,255,.1)' }), svgEl('text', { x: p.x + 22, y: yy + 1, 'font-size': 11.5, fill: '#c9d6f5' }, cut(mod.replace(e.c.path, '') || '/', 30)), svgEl('text', { x: p.x + bw - 22, y: yy + 1, 'text-anchor': 'end', 'font-size': 11, fill: '#9aa9c9' }, v.files)); yy += 22; }
    if (e.parts.length) {
      yy += 10;
      e.parts.slice(0, 8).forEach((n, i) => { const px = p.x + 16 + (i % 2) * 140, py = yy + Math.floor(i / 2) * 20; const c = svgEl('g', {}, svgEl('rect', { x: px, y: py - 11, width: 128, height: 17, rx: 8, fill: 'none', stroke: colorOf(n), 'stroke-opacity': 0.7 }), svgEl('text', { x: px + 8, y: py + 1, 'font-size': 10.5, fill: colorOf(n) }, cut(n.label, 16))); bindNode(c, n.id); g.append(c); });
    }
    bindNode(g, e.c.id); svg.append(g);
  }
  return el('div', {}, el('div', { class: 'mini', style: { marginBottom: '8px' } }, t('comp.note')), el('div', { style: { overflow: 'auto' } }, svg));
}

// ---------------------------------------------------------------- shell
export function mount(host) {
  const hk = new URLSearchParams(location.hash.split('?')[1] || '').get('kind');
  if (KINDS.includes(hk)) kind = hk;
  const tabs = el('div', { class: 'dgmtabs' });
  const body = el('div', { class: 'dgm' });
  host.append(tabs, body);
  let current = null;
  const render = () => {
    const m = store.model;
    tabs.replaceChildren(...KINDS.map((k) => el('button', { class: 'tabbtn' + (k === kind ? ' on' : ''), onclick: () => { kind = k; render(); } }, t('dgm.' + k))));
    const note = el('div', { class: 'mini', style: { marginBottom: '10px', maxWidth: '900px' } }, t('dgm.' + kind + '.note'));
    let content;
    if (kind === 'ctx') content = el('div', { style: { overflow: 'auto' } }, contextDiagram(m));
    else if (kind === 'goals') content = el('div', {}, el('div', { class: 'row', style: { marginBottom: '8px' } }, ['impl', 'status'].map((c) => el('button', { class: 'tabbtn' + (goalColor === c ? ' on' : ''), onclick: () => { goalColor = c; render(); } }, t('map.color.' + c))),
      el('span', { class: 'legend' }, goalColor === 'impl' ? [['#34e0a1', t('impl.done')], ['#3a4a78', t('impl.none')]].map(([c, l]) => el('span', {}, el('i', { class: 'dot', style: { background: c } }), l)) : Object.entries(STATUS_COLOR).slice(0, 4).map(([k, c]) => el('span', {}, el('i', { class: 'dot', style: { background: c } }), statusText(k, ''))))), el('div', { style: { overflow: 'auto' } }, goalTree(m)));
    else if (kind === 'states') content = statesView(m);
    else if (kind === 'entities') { const hostEl = el('div'); hostEl.append(entityDiagram(m, hostEl)); content = hostEl; }
    else content = componentDiagram(m);
    current = el('div', {}, note, content);
    body.replaceChildren(current);
    applyDim(body);
  };
  render();
  const refresh = () => applyDim(body);
  const offs = [store.on('select', refresh), store.on('hover', refresh), store.on('model', render), onLang(render)];
  body.addEventListener('click', (e) => { if (e.target === body || e.target.tagName === 'svg') store.clear(); });
  return { destroy() { offs.forEach((f) => f()); hideTip(); } };
}
