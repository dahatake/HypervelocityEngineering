// FR-1079: Graph display mode — the shared drawing part. Nodes + directed edges in SVG, no external library.
//  - layered layout (directed / hierarchical relations: trace, goals, states): layers → barycentre ordering → left to right.
//  - force layout (Fruchterman–Reingold, fixed iteration count, so the same input always gives the same picture):
//    undirected only in the computation; the arrow still follows the original direction of the relation.
// Nothing is animated, so prefers-reduced-motion needs no special case (AC-428). Icons come from the bundled set (ui.js), never fetched.
import { t } from './i18n.js';
import { store } from './store.js';
import { el, svgEl, icon } from './ui.js';

export const GRAPH_CAP = 150;           // PARAM-056: more nodes than this are narrowed down (AC-429)
export const NODE_W = 208, NODE_H = 48; // 4px grid
const GAP_X = 72, GAP_Y = 24, PAD = 24;

const ICON_OF = { goal: 'goal', req: 'req', nfr: 'req', ac: 'ac', case: 'test', test: 'test', entity: 'entity', table: 'tables', component: 'component', state: 'state',
  system: 'structure', persona: 'person', external: 'integrations', integration: 'integrations', api: 'api', file: 'source' };
const VAR_OF = { goal: '--viz-goal', req: '--viz-req', nfr: '--viz-nfr', ac: '--viz-ac', case: '--viz-case', test: '--viz-test', entity: '--viz-entity', component: '--viz-comp',
  persona: '--viz-persona', external: '--viz-external', integration: '--viz-external', api: '--viz-api', table: '--viz-table', state: '--viz-entity', system: '--viz-file' };
export const typeWord = (type) => t('graph.type.' + type);

// ---------------------------------------------------------------- layouts (pure; exported for tests)
const dedupe = (nodes, edges) => {
  const idx = new Map(nodes.map((n, i) => [n.id, i]));
  const seen = new Set(), list = [];
  for (const e of edges) {
    const a = idx.get(e.from), b = idx.get(e.to);
    if (a == null || b == null || a === b) continue;
    const k = a + '>' + b;
    if (seen.has(k)) continue;
    seen.add(k); list.push([a, b]);
  }
  return { idx, list };
};

export function layeredLayout(nodes, edges) {
  const n = nodes.length;
  const { list } = dedupe(nodes, edges);
  const out = nodes.map(() => []);
  for (const [a, b] of list) out[a].push(b);
  // break cycles: drop the edges that point back to a node still on the DFS stack
  const mark = new Array(n).fill(0), dagOut = nodes.map(() => []), dagIn = nodes.map(() => []);
  const dfs = (u) => {
    mark[u] = 1;
    for (const v of out[u]) {
      if (mark[v] === 1) continue;
      dagOut[u].push(v); dagIn[v].push(u);
      if (mark[v] === 0) dfs(v);
    }
    mark[u] = 2;
  };
  for (let i = 0; i < n; i++) if (mark[i] === 0) dfs(i);
  const layer = new Array(n).fill(-1);
  const depth = (u) => {
    if (layer[u] >= 0) return layer[u];
    layer[u] = 0;
    let d = 0;
    for (const p of dagIn[u]) d = Math.max(d, depth(p) + 1);
    return (layer[u] = d);
  };
  for (let i = 0; i < n; i++) depth(i);
  const cols = [];
  for (let i = 0; i < n; i++) (cols[layer[i]] ||= []).push(i);
  for (let l = 0; l < cols.length; l++) cols[l] ||= [];
  const pos = new Array(n).fill(0);
  const place = () => cols.forEach((c) => c.forEach((v, i) => { pos[v] = i; }));
  place();
  const bary = (v, nb) => (nb[v].length ? nb[v].reduce((s, u) => s + pos[u], 0) / nb[v].length : pos[v]);
  for (let pass = 0; pass < 4; pass++) {
    const down = pass % 2 === 0;
    const order = down ? cols.map((_, i) => i) : cols.map((_, i) => cols.length - 1 - i);
    for (const l of order) {
      const nb = down ? dagIn : dagOut;
      cols[l] = cols[l].map((v) => [v, bary(v, nb)]).sort((a, b) => a[1] - b[1] || a[0] - b[0]).map((x) => x[0]);
      cols[l].forEach((v, i) => { pos[v] = i; });
    }
  }
  const at = new Map();
  let h = 0;
  cols.forEach((c, l) => c.forEach((v, i) => {
    const y = PAD + i * (NODE_H + GAP_Y);
    at.set(nodes[v].id, { x: PAD + l * (NODE_W + GAP_X), y, layer: l });
    h = Math.max(h, y + NODE_H + PAD);
  }));
  return { pos: at, width: PAD * 2 + cols.length * NODE_W + Math.max(0, cols.length - 1) * GAP_X, height: Math.max(h, PAD * 2 + NODE_H), layers: cols.length };
}

export function forceLayout(nodes, edges, iterations = 250) {
  const n = nodes.length;
  const { list } = dedupe(nodes, edges);
  const k = 190;
  const side = Math.max(480, k * Math.sqrt(Math.max(n, 1)) * 1.1);
  const x = new Array(n), y = new Array(n);
  for (let i = 0; i < n; i++) {   // deterministic start: a spiral in input order
    const r = 0.45 * side * Math.sqrt((i + 0.5) / n), a = i * 2.399963229728653;
    x[i] = side / 2 + r * Math.cos(a); y[i] = side / 2 + r * Math.sin(a);
  }
  let temp = side / 8;
  const dx = new Array(n), dy = new Array(n);
  for (let it = 0; it < iterations; it++) {
    dx.fill(0); dy.fill(0);
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let ex = x[i] - x[j], ey = y[i] - y[j];
      let d = Math.hypot(ex, ey);
      if (d < 0.01) { ex = 0.01 * ((i + j) % 2 ? 1 : -1); ey = 0.01; d = 0.0142; }
      const f = (k * k) / d / d;
      dx[i] += ex * f; dy[i] += ey * f; dx[j] -= ex * f; dy[j] -= ey * f;
    }
    for (const [a, b] of list) {
      const ex = x[a] - x[b], ey = y[a] - y[b];
      const d = Math.max(Math.hypot(ex, ey), 0.01);
      const f = d / k;
      dx[a] -= ex * f; dy[a] -= ey * f; dx[b] += ex * f; dy[b] += ey * f;
    }
    for (let i = 0; i < n; i++) {
      const d = Math.max(Math.hypot(dx[i], dy[i]), 0.01), m = Math.min(d, temp);
      x[i] += (dx[i] / d) * m; y[i] += (dy[i] / d) * m;
    }
    temp = (side / 8) * (1 - (it + 1) / iterations);
  }
  // a few passes that push overlapping boxes apart (the boxes are wide, points are not)
  for (let pass = 0; pass < 40; pass++) {
    let moved = false;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const ox = NODE_W + 16 - Math.abs(x[i] - x[j]), oy = NODE_H + 16 - Math.abs(y[i] - y[j]);
      if (ox > 0 && oy > 0) {
        moved = true;
        if (oy < ox) { const s = y[i] <= y[j] ? 1 : -1; y[i] -= (s * oy) / 2; y[j] += (s * oy) / 2; }
        else { const s = x[i] <= x[j] ? 1 : -1; x[i] -= (s * ox) / 2; x[j] += (s * ox) / 2; }
      }
    }
    if (!moved) break;
  }
  const minX = Math.min(...x, 0), minY = Math.min(...y, 0);
  const at = new Map();
  let w = 0, h = 0;
  nodes.forEach((nd, i) => {
    const px = Math.round(x[i] - minX - NODE_W / 2 + PAD + NODE_W / 2), py = Math.round(y[i] - minY - NODE_H / 2 + PAD + NODE_H / 2);
    at.set(nd.id, { x: px, y: py });
    w = Math.max(w, px + NODE_W + PAD); h = Math.max(h, py + NODE_H + PAD);
  });
  return { pos: at, width: Math.max(w, 2 * PAD + NODE_W), height: Math.max(h, 2 * PAD + NODE_H), layers: 0 };
}

// where the line from the centre of `a` to the centre of `b` leaves the box of `a`
const clip = (a, b) => {
  const cx = a.x + NODE_W / 2, cy = a.y + NODE_H / 2, tx = b.x + NODE_W / 2 - cx, ty = b.y + NODE_H / 2 - cy;
  if (!tx && !ty) return [cx, cy];
  const s = Math.min(tx ? NODE_W / 2 / Math.abs(tx) : Infinity, ty ? NODE_H / 2 / Math.abs(ty) : Infinity);
  return [cx + tx * s, cy + ty * s];
};

// ---------------------------------------------------------------- filtering over PARAM-056 (AC-429)
const filterState = new Map();   // per graph name: kept while the page is open (selection lives in the store)
export function narrow(nodes, edges, { selected, mode, type, cap = GRAPH_CAP }) {
  if (nodes.length <= cap) return { nodes, edges, mode: null, type: null };
  const ids = new Set(nodes.map((n) => n.id));
  const types = [...new Set(nodes.map((n) => n.type))];
  const byType = (ty) => nodes.filter((n) => n.type === ty);
  let keep;
  let m = mode || (selected && ids.has(selected) ? 'near' : 'type');
  if (m === 'near' && !(selected && ids.has(selected))) m = 'type';
  let ty = type;
  if (m === 'near') {
    const adj = new Map(nodes.map((n) => [n.id, []]));
    for (const e of edges) if (adj.has(e.from) && adj.has(e.to)) { adj.get(e.from).push(e.to); adj.get(e.to).push(e.from); }
    keep = new Set([selected]);
    let frontier = [selected];
    while (frontier.length && keep.size < cap) {
      const next = [];
      for (const u of frontier) for (const v of adj.get(u)) if (!keep.has(v) && keep.size < cap) { keep.add(v); next.push(v); }
      frontier = next;
    }
  } else {
    if (!ty || !types.includes(ty)) {    // default: the biggest type that fits under the cap, else the smallest
      const fit = types.filter((x) => byType(x).length <= cap).sort((a, b) => byType(b).length - byType(a).length);
      ty = fit[0] || [...types].sort((a, b) => byType(a).length - byType(b).length)[0];
    }
    keep = new Set(byType(ty).slice(0, cap).map((n) => n.id));
    if (selected && ids.has(selected)) keep.add(selected);    // the selected node never disappears
  }
  return { nodes: nodes.filter((n) => keep.has(n.id)), edges: edges.filter((e) => keep.has(e.from) && keep.has(e.to)), mode: m, type: ty };
}

// ---------------------------------------------------------------- view
let uid = 0;
const cutTitle = (s, n) => (String(s).length > n ? String(s).slice(0, n - 1) + '…' : String(s));

// nodes: [{id, label, title?, type, word?}], edges: [{from, to, label?}], layout: 'layered' | 'force'
export function graphView({ name = 'graph', nodes, edges, layout = 'layered', cap = GRAPH_CAP, note }) {
  const root = el('section', { class: 'gv', 'data-testid': 'graph-view', 'data-current': 'graph', 'data-layout': layout, 'data-graph': name, 'data-total': String(nodes.length) });
  const ids = new Set(nodes.map((n) => n.id));
  const fs = filterState.get(name) || {};
  filterState.set(name, fs);
  let sel = ids.has(store.selected) ? store.selected : null;
  const arrow = 'gv-arrow-' + ++uid;
  let focusId = null;

  const draw = () => {
    const view = narrow(nodes, edges, { selected: sel, mode: fs.mode, type: fs.type, cap });
    const lay = layout === 'force' ? forceLayout(view.nodes, view.edges) : layeredLayout(view.nodes, view.edges);
    // reading order (= Tab order): left to right by layer / row for the layered layout, top to bottom then left to right for the force layout
    const ordered = [...view.nodes].sort((a, b) => {
      const pa = lay.pos.get(a.id), pb = lay.pos.get(b.id);
      return layout === 'force' ? Math.round(pa.y / NODE_H) - Math.round(pb.y / NODE_H) || pa.x - pb.x : pa.x - pb.x || pa.y - pb.y;
    });
    const svg = svgEl('svg', { class: 'gv-svg', width: lay.width, height: lay.height, viewBox: `0 0 ${lay.width} ${lay.height}`, role: 'group',
      'aria-label': t('graph.aria', { n: view.nodes.length, r: view.edges.length }) });
    svg.append(svgEl('defs', {}, svgEl('marker', { id: arrow, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: 'auto' },
      svgEl('path', { d: 'M0 0L10 5L0 10z', class: 'gv-arrowhead' }))));
    const eg = svgEl('g', { class: 'gv-edges' });
    for (const e of view.edges) {
      const a = lay.pos.get(e.from), b = lay.pos.get(e.to);
      if (!a || !b || e.from === e.to) continue;
      let d;
      if (layout !== 'force' && b.x > a.x + NODE_W) {
        const sx = a.x + NODE_W, sy = a.y + NODE_H / 2, tx = b.x, ty = b.y + NODE_H / 2, c = Math.max(24, (tx - sx) / 2);
        d = `M${sx} ${sy}C${sx + c} ${sy} ${tx - c} ${ty} ${tx} ${ty}`;
      } else {
        const [sx, sy] = clip(a, b), [tx, ty] = clip(b, a);
        d = `M${Math.round(sx)} ${Math.round(sy)}L${Math.round(tx)} ${Math.round(ty)}`;
      }
      const p = svgEl('path', { d, class: 'gv-edge', 'data-testid': 'graph-edge', 'data-from': e.from, 'data-to': e.to, 'marker-end': `url(#${arrow})`, fill: 'none' });
      if (e.label) p.append(svgEl('title', {}, `${e.from} → ${e.to}: ${e.label}`));
      else p.append(svgEl('title', {}, `${e.from} → ${e.to}`));
      eg.append(p);
    }
    const ng = svgEl('g', { class: 'gv-nodes' });
    for (const n of ordered) {
      const p = lay.pos.get(n.id);
      const word = n.word || typeWord(n.type);
      const title = n.title && n.title !== n.id ? n.title : (n.label && n.label !== n.id ? n.label : '');
      const g = svgEl('g', { class: 'gv-node' + (n.id === sel ? ' sel' : ''), transform: `translate(${p.x} ${p.y})`, tabindex: '0', role: 'button', 'data-testid': 'graph-node', 'data-node-id': n.id,
        'data-type': n.type, 'aria-pressed': n.id === sel ? 'true' : 'false', 'aria-label': `${word} ${n.id}${title ? ' ' + title : ''}`,
        style: `color:var(${VAR_OF[n.type] || '--viz-file'})` });
      g.append(svgEl('title', {}, `${word} · ${n.id}${title ? ' · ' + title : ''}`),
        svgEl('rect', { class: 'gv-box', width: NODE_W, height: NODE_H, rx: 8 }),
        svgEl('rect', { class: 'gv-bar', x: 0, y: 8, width: 4, height: NODE_H - 16, rx: 2 }));
      const ic = icon(ICON_OF[n.type] || 'info', { size: 20 });
      ic.setAttribute('x', 12); ic.setAttribute('y', 14); ic.setAttribute('class', 'icon gv-ico');
      g.append(ic,
        svgEl('text', { class: 'gv-id', x: 40, y: 20 }, cutTitle(n.id, 22)),
        svgEl('text', { class: 'gv-title', x: 40, y: 37 }, cutTitle(title || word, 20)));
      const pick = () => { focusId = n.id; sel = n.id; if (store.nodes.has(n.id)) store.select(n.id); paintSel(); };
      g.addEventListener('click', (ev) => { ev.stopPropagation(); pick(); });
      g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); pick(); } });
      g.addEventListener('focus', () => { focusId = n.id; });
      ng.append(g);
    }
    svg.append(eg, ng);

    const parts = [];
    if (view.mode) {   // AC-429: say why and how many there are in all; the chips change the narrowing, the selection stays
      const why = view.mode === 'near' ? t('graph.filter.near') : t('graph.filter.type', { type: typeWord(view.type) });
      parts.push(el('div', { class: 'gv-filter', 'data-testid': 'graph-filter', 'data-mode': view.mode, role: 'status' },
        el('p', {}, t('graph.filter.note', { total: nodes.length, cap, n: view.nodes.length, why })),
        el('div', { class: 'gv-chips', role: 'group', 'aria-label': t('graph.filter.by') },
          el('button', { type: 'button', class: 'btn ghost' + (view.mode === 'near' ? ' on' : ''), 'aria-pressed': view.mode === 'near' ? 'true' : 'false', disabled: sel ? null : true,
            onclick: () => { fs.mode = 'near'; redraw(); } }, t('graph.filter.near')),
          [...new Set(nodes.map((x) => x.type))].map((ty) => el('button', { type: 'button', class: 'btn ghost' + (view.mode === 'type' && view.type === ty ? ' on' : ''), 'data-filter-type': ty,
            'aria-pressed': view.mode === 'type' && view.type === ty ? 'true' : 'false', onclick: () => { fs.mode = 'type'; fs.type = ty; redraw(); } },
          `${typeWord(ty)} (${nodes.filter((x) => x.type === ty).length})`)))));
    }
    root.setAttribute('data-shown', String(view.nodes.length));
    root.setAttribute('data-filtered', view.mode ? 'true' : 'false');
    const legend = el('ul', { class: 'gv-legend', 'aria-label': t('graph.legend') },
      [...new Set(view.nodes.map((x) => x.type))].map((ty) => el('li', {}, el('span', { class: 'gv-key', style: `color:var(${VAR_OF[ty] || '--viz-file'})` }, icon(ICON_OF[ty] || 'info', { size: 16 })), typeWord(ty))));
    const body = el('div', { class: 'gv-scroll', tabindex: '-1' }, svg);
    root.replaceChildren(...(note ? [el('p', { class: 'mini gv-note' }, note)] : []), ...parts, legend, body,
      view.nodes.length ? '' : el('p', { class: 'empty' }, t('graph.empty')));
    if (focusId) root.querySelector(`[data-node-id="${CSS.escape(focusId)}"]`)?.focus({ preventScroll: true });
  };
  const redraw = () => draw();
  const paintSel = () => {
    for (const g of root.querySelectorAll('.gv-node')) { const on = g.dataset.nodeId === sel; g.classList.toggle('sel', on); g.setAttribute('aria-pressed', on ? 'true' : 'false'); }
    for (const p of root.querySelectorAll('.gv-edge')) p.classList.toggle('hi', !!sel && (p.dataset.from === sel || p.dataset.to === sel));
  };
  draw(); paintSel();
  const off = store.on('select', ({ id }) => {
    const next = id && ids.has(id) ? id : null;
    if (next === sel) return;
    sel = next;
    if (root.dataset.filtered === 'true') redraw();    // the neighbourhood moves with the selection; the narrowing itself is kept
    paintSel();
  });
  return { el: root, destroy: () => off() };
}
