// Semantic zoom for the entity model (FR-1027..FR-1029, NFR-PERF-004, NFR-UX-010).
// One shared view state (scale, centre, selection, filter) drives the 2D renderer (sz2d.js, also used on #/entities) and the
// 3D renderer (sz3d.js), so switching between them keeps the target, the level and the filter.
//   scale 1 = the whole model fits.  scale < PARAM-017 (2): "overview" = clusters;  < PARAM-018 (8): "mid" = entities + relation
//   lines;  otherwise "detail" = column list (name, type, key, reference).
// Data: model.entities (scripts/entities.py through eabk_model.build_entities): entities[].columns, relations, clusters.
// Only the part inside the viewport is drawn (virtualisation); getState() always reports the complete data.
import { t, lang, onLang } from './i18n.js';
import { store, norm } from './store.js';
import { el } from './ui.js';

export const MIN_SCALE = 0.1;
export const MAX_SCALE = 64;
export const L = { CELL_W: 300, BOX_W: 260, HEAD_H: 32, ROW_H: 17, MAX_ROWS: 14, USE_ROW: 16, MAX_USES: 4, GAP_Y: 34, PAD: 40, CL_GAP: 70, TITLE_H: 24 };
export const KINDS = ['外部キー', '参照', '使用'];
const CLICK_DRAG_PX = 6;

// Shared across routes (module singleton): 2D <-> 3D keeps the same target, level and filter (FR-1029 AC-180).
export const view = { scale: 1, cx: null, cy: null, selected: null, column: null, filter: '', tab: null, yaw: 0.6, pitch: 0.95 };
const viewListeners = new Set();
export const onView = (fn) => { viewListeners.add(fn); return () => viewListeners.delete(fn); };
const notify = (why) => { for (const f of [...viewListeners]) { try { f(why); } catch (e) { console.error(e); } } };

export const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
export const levelOf = (scale, th) => (scale >= th.detail ? 'detail' : scale >= th.mid ? 'mid' : 'overview');

function paramNum(m, id, dflt) {
  const p = (m.params || []).find((x) => x.id === id);
  const v = p ? parseFloat(String(p.value).match(/-?\d+(\.\d+)?/)?.[0]) : NaN;
  return Number.isFinite(v) && v > 0 ? v : dflt;
}
export function thresholds(m) {
  const mid = paramNum(m, 'PARAM-017', 2), detail = paramNum(m, 'PARAM-018', 8);
  return detail > mid ? { mid, detail } : { mid: 2, detail: 8 };
}

// Words: Japanese UI shows the data word; English UI shows the English word followed by the data word (data is shown as written).
export const kindLabel = (k) => (lang() === 'ja' ? k : `${t('sz.k.' + k)} (${k})`);
export const keyMark = (k) => (k === '主キー' ? 'PK' : k === '外部キー' ? 'FK' : '');

// ---------------------------------------------------------------------------------------------- data + layout
const cache = new WeakMap();
const archCache = new WeakMap();
// FR-1034: ?view=arch shows the architecture diagram (execution locations as the overview "clusters") on the same renderers.
export const isArch = () => new URLSearchParams((location.hash.split('?')[1]) || '').get('view') === 'arch';
export function dataOf(m, arch = false) {
  const ent = m && m.entities;
  if (!ent || !ent.entities || !ent.entities.length) return null;
  const c = arch ? archCache : cache;
  let d = c.get(ent);
  if (!d) { d = build(m, arch); c.set(ent, d); }
  return d;
}

function build(m, arch = false) {
  const ent = m.entities;
  const ents = ent.entities;
  const byName = new Map(ents.map((e) => [e.name, e]));
  const names = ents.map((e) => e.name);
  const edges = [], colEdges = [], uses = new Map(), nbr = new Map();
  for (const n of names) { uses.set(n, []); nbr.set(n, new Set()); }
  for (const r of ent.relations || []) {
    if (r.scope === 'entity' && byName.has(r.from) && byName.has(r.to)) {
      edges.push({ from: r.from, to: r.to, kind: r.kind, sources: r.sources || [] });
      nbr.get(r.from).add(r.to); nbr.get(r.to).add(r.from);
    } else if (r.scope === 'usage' && r.toType === 'table' && byName.has(r.from)) {
      const e = { from: r.from, to: r.to, kind: '使用', sources: r.sources || [], usage: true };
      edges.push(e); uses.get(r.from).push(e);
    } else if (r.scope === 'column' && byName.has(r.from) && byName.has(r.to)) colEdges.push(r);
  }
  // every entity belongs to exactly one cluster (AC-176); anything the derivation missed becomes a singleton
  const seen = new Set();
  let clusters = [];
  const locations = ((m.placements && m.placements.locations) || []).map((l) => ({ ...l, links: (l.links || []).map((x) => ({ ...x })) }));
  const storage = new Map(names.map((n) => [n, []]));   // entity -> every listed location holding its data (AC-201)
  for (const l of locations) for (const dn of l.data) if (storage.has(dn)) storage.get(dn).push({ kind: l.kind, name: l.name });
  if (arch) {
    // overview content = execution locations; nothing unlisted is invented, unplaced entities go to "なし" (AC-202)
    for (const l of locations) {
      const es = l.data.filter((n) => byName.has(n) && !seen.has(n));
      es.forEach((n) => seen.add(n));
      const lines = [...l.apps.map((a) => `▫ ${a}`), ...l.data.filter((n) => !byName.has(n)).map((n) => `▫ ${n}`), ...es.map((n) => `▪ ${n}`)];
      clusters.push({ id: `${l.kind} · ${l.name}`, count: es.length, entities: es, lines, location: l });
    }
    const rest = names.filter((n) => !seen.has(n));
    if (rest.length || !clusters.length) clusters.push({ id: 'なし', count: rest.length, entities: rest, lines: rest.map((n) => `▪ ${n}`), none: true });
    rest.forEach((n) => seen.add(n));
  } else {
    for (const c of ent.clusters || []) {
      const es = c.entities.filter((n) => byName.has(n) && !seen.has(n));
      es.forEach((n) => seen.add(n));
      if (es.length) clusters.push({ id: c.id, count: es.length, entities: es });
    }
    for (const n of names) if (!seen.has(n)) clusters.push({ id: 'C' + (clusters.length + 1), count: 1, entities: [n] });
  }
  const clusterOf = new Map();
  for (const c of clusters) for (const n of c.entities) clusterOf.set(n, c);

  const midH = (e) => L.HEAD_H + L.USE_ROW * (Math.min(uses.get(e.name).length, L.MAX_USES) + (uses.get(e.name).length > L.MAX_USES ? 1 : 0)) + 10;
  const rowsOf = (e) => (e.columns.length ? Math.min(e.columns.length, L.MAX_ROWS) + (e.columns.length > L.MAX_ROWS ? 1 : 0) : 1);
  const detH = (e) => L.HEAD_H + L.ROW_H * rowsOf(e) + 10;
  let maxH = 0;
  for (const e of ents) maxH = Math.max(maxH, midH(e), detH(e));
  const cellH = maxH + L.GAP_Y;

  const blocks = clusters.map((c) => {
    const cols = Math.max(1, Math.ceil(Math.sqrt(c.count))), rows = Math.max(1, Math.ceil(c.count / cols));
    return { c, cols, w: cols * L.CELL_W - (L.CELL_W - L.BOX_W) + 2 * L.PAD, h: rows * cellH - L.GAP_Y + 2 * L.PAD + L.TITLE_H };
  });
  const area = blocks.reduce((s, b) => s + b.w * b.h, 0);
  const rowW = Math.max(...blocks.map((b) => b.w), Math.sqrt(area * 1.7));
  const pos = new Map(), rects = new Map();
  let x = 0, y = 0, rowH = 0, maxX = 0;
  for (const b of blocks) {
    if (x > 0 && x + b.w > rowW) { x = 0; y += rowH + L.CL_GAP; rowH = 0; }
    rects.set(b.c.id, { x, y, w: b.w, h: b.h });
    b.c.entities.forEach((n, i) => {
      const e = byName.get(n);
      pos.set(n, { x: x + L.PAD + (i % b.cols) * L.CELL_W, y: y + L.PAD + L.TITLE_H + Math.floor(i / b.cols) * cellH, midH: midH(e), detH: detH(e), w: L.BOX_W });
    });
    maxX = Math.max(maxX, x + b.w);
    x += b.w + L.CL_GAP;
    rowH = Math.max(rowH, b.h);
  }
  const world = { x0: 0, y0: 0, x1: maxX, y1: y + rowH };
  const cols = new Map();
  for (const e of ents) cols.set(e.name, new Map(e.columns.map((c, i) => [c.name, i])));
  return { ents, byName, names, edges, colEdges, uses, nbr, clusters, clusterOf, pos, rects, world, cellH, cols, arch, locations, storage,
    totalColumns: ents.reduce((s, e) => s + e.columns.length, 0), supplement: ent.supplement || { files: [], diagnostics: [] } };
}

export const parseRef = (ref) => { const m = /^(.+)\.([^.]+)$/.exec(ref || ''); return m ? { entity: m[1].trim(), column: m[2].trim() } : null; };
export const worldCenter = (d) => ({ x: (d.world.x0 + d.world.x1) / 2, y: (d.world.y0 + d.world.y1) / 2 });
export const boxCenter = (d, n, level) => { const p = d.pos.get(n); return { x: p.x + p.w / 2, y: p.y + (level === 'detail' ? p.detH : p.midH) / 2 }; };
export const matches = (n, d) => { if (!view.filter) return true; const e = d.byName.get(n); return norm(n + ' ' + (e ? e.description : '')).includes(norm(view.filter)); };

export function stateOf(d, th) {
  const level = levelOf(view.scale, th);
  const st = {
    scale: view.scale, level, selected: view.selected, column: view.column, filter: view.filter, thresholds: th,
    clusters: d.clusters.map((c) => ({ id: c.id, count: c.count, entities: [...c.entities] })),
    entities: [...d.names],
    edges: level === 'overview' ? [] : d.edges.map((e) => ({ from: e.from, to: e.to, kind: e.kind })),
    columns: {},
    arch: !!d.arch,
    locations: d.locations.map((l) => ({ kind: l.kind, name: l.name, apps: [...l.apps], data: [...l.data], links: l.links.map((x) => ({ ...x })) })),
    storage: Object.fromEntries(d.names.map((n) => [n, d.storage.get(n).length ? d.storage.get(n).map((s) => `${s.kind} · ${s.name}`) : 'なし'])),
    totals: { entities: d.names.length, columns: d.totalColumns },
  };
  if (view.filter) st.matched = d.names.filter((n) => matches(n, d));
  if (level === 'detail') {
    for (const e of d.ents) if (e.columns.length) st.columns[e.name] = e.columns.map((c) => ({ name: c.name, type: c.type, key: c.key, ref: c.ref, description: c.description, origin: c.origin }));
  }
  return st;
}

// ---------------------------------------------------------------------------------------------- shell
// opts: { mode: 'entities'|'map2d'|'map3d', createRenderer(ctx) -> renderer, height?: px, links?: [{label, href}] }
// renderer: { el, draw(), fit(), toWorld(px,py), toScreen(wx,wy), kind: '2d'|'3d', pick?(px,py) }
export function mountShell(host, opts) {
  const m = store.model;
  const d = dataOf(m, isArch());
  if (!d) return { destroy() {} };
  const th = thresholds(m);
  let W = 0, H = 0, raf = 0, dead = false, moved = false, ready = false, altOpen = false;
  const ptrs = new Map();
  let pinch = null, dragStart = null;

  const root = el('section', { class: `sz sz-${opts.mode}`, 'data-testid': 'semantic-zoom', 'data-mode': opts.mode, 'data-scale': String(view.scale),
    'data-level': levelOf(view.scale, th), 'data-ready': 'false', role: 'region', style: opts.height ? { height: opts.height + 'px' } : null });
  const live = el('div', { class: 'sr-only', role: 'status', 'aria-live': 'polite', 'data-testid': 'sz-live' });
  const levelBadge = el('span', { class: 'sz-level badge', 'data-testid': 'sz-level' });
  const scaleText = el('span', { class: 'mini sz-scale' });
  const btn = (label, text, fn, extra = {}) => el('button', { type: 'button', class: 'btn ghost sz-btn', 'aria-label': label, title: label, onclick: fn, ...extra }, text);
  const levelBtns = ['overview', 'mid', 'detail'].map((lv) => btn(`${t('sz.level')}: ${t('sz.level.' + lv)}`, t('sz.level.' + lv), () => setLevel(lv), { 'data-level-btn': lv }));
  const filterIn = el('input', { type: 'search', class: 'sz-filter', value: view.filter, 'aria-label': t('sz.filter'), placeholder: t('sz.filter'),
    oninput: (e) => { view.filter = e.target.value; sync(); draw(); notify('filter'); } });
  const bar = el('div', { class: 'sz-bar', role: 'toolbar', 'aria-label': t('sz.title') });
  const viewport = el('div', { class: 'sz-view', tabindex: '0', role: 'group', 'aria-roledescription': 'semantic zoom', 'data-testid': 'sz-viewport' });
  const side = el('aside', { class: 'sz-side', 'data-testid': 'sz-side', hidden: true });
  const note = el('div', { class: 'sz-note mini', 'data-testid': 'sz-note' });
  const altBox = el('details', { class: 'sz-alt', 'data-testid': 'sz-alt', ontoggle: (e) => { altOpen = e.target.open; if (altOpen) renderAlt(); } },
    el('summary', {}, t('sz.alt')), el('div', { class: 'sz-alt-body' }));
  const hint = el('div', { class: 'mini sz-hint', id: 'sz-hint-' + opts.mode }, t('sz.hint'));
  viewport.setAttribute('aria-describedby', hint.id);

  const api = {
    dragged: () => moved,
    select, selectColumn, gotoRef, zoomToCluster, tip, hideTip: () => tipEl.hidden = true,
    matches: (n) => matches(n, d),
  };
  const tipEl = el('div', { class: 'sz-tip', hidden: true });
  const ctx = { d, th, view, api, size: () => ({ W, H }), level: () => levelOf(view.scale, th), k: () => renderer.fit() * view.scale, center: () => ({ x: view.cx, y: view.cy }) };
  const renderer = opts.createRenderer(ctx);
  viewport.append(renderer.el, tipEl);

  bar.append(
    el('h2', { class: 'sz-title' }, t('sz.title')), levelBadge, scaleText,
    btn(t('sz.zoomout'), '−', () => zoomBy(1 / 1.25), { 'data-testid': 'sz-zoom-out' }),
    btn(t('sz.zoomin'), '+', () => zoomBy(1.25), { 'data-testid': 'sz-zoom-in' }),
    btn(t('sz.fit'), '⤢', () => setScale(1), { 'data-testid': 'sz-fit' }),
    ...levelBtns,
    btn('◀', '◀', () => step(-1)), btn('▶', '▶', () => step(1)),
    btn(t('sz.clear'), '✕', () => select(null)),
    filterIn);
  if (renderer.kind === '3d') {
    bar.append(btn(t('sz.rot') + ' ⟲', '⟲', () => rotate(-0.26, 0)), btn(t('sz.rot') + ' ⟳', '⟳', () => rotate(0.26, 0)),
      btn(t('sz.rot') + ' ↑', '⤒', () => rotate(0, 0.1)), btn(t('sz.rot') + ' ↓', '⤓', () => rotate(0, -0.1)));
  }
  for (const lk of opts.links || []) bar.append(el('a', { class: 'btn ghost sz-btn', href: lk.href, 'data-testid': lk.id || null }, lk.label()));
  if (opts.onSwitch) bar.append(btn(t('sz.graph'), t('sz.graph'), opts.onSwitch));
  const main = el('div', { class: 'sz-main' }, viewport, side);
  root.append(bar, main, note, hint, altBox, live);
  host.append(root);

  // ------------------------------------------------------------ state
  function levelNow() { return levelOf(view.scale, th); }
  function label() {
    const lv = levelNow();
    const sel = view.selected ? `${t('sz.sel')}: ${view.selected}${view.column ? '.' + view.column : ''}` : t('sz.none');
    return `${t('sz.title')} — ${t('sz.level')}: ${t('sz.level.' + lv)}（${t('sz.lv.' + lv)}） / ${t('sz.scale')}: ${fmt(view.scale)} / ${sel}`;
  }
  const fmt = (n) => (Math.abs(n - Math.round(n)) < 1e-9 ? String(Math.round(n)) : n.toFixed(2));
  function sync() {
    const lv = levelNow();
    root.dataset.scale = String(view.scale);
    root.dataset.level = lv;
    root.dataset.selected = view.selected || '';
    root.setAttribute('aria-label', label());
    viewport.setAttribute('aria-label', label());
    levelBadge.textContent = `${t('sz.level')}: ${t('sz.level.' + lv)}`;
    levelBadge.dataset.level = lv;
    scaleText.textContent = `${t('sz.scale')} ×${fmt(view.scale)} · ${t('sz.lv.' + lv)}`;
    for (const b of levelBtns) b.setAttribute('aria-pressed', String(b.dataset.levelBtn === lv));
    live.textContent = label();
    renderSide();
    if (altOpen) renderAlt();
  }

  function renderSide() {
    const n = view.selected, e = n && d.byName.get(n);
    if (!e) { side.hidden = true; side.replaceChildren(); return; }
    side.hidden = false;
    const rels = d.edges.filter((x) => !x.usage && (x.from === n || x.to === n));
    const tb = (head, rows) => el('table', { class: 'eu-sub sz-tbl' }, el('thead', {}, el('tr', {}, head.map((h) => el('th', { scope: 'col' }, h)))), el('tbody', {}, rows));
    const colRows = e.columns.map((c) => {
      const r = parseRef(c.ref);
      return el('tr', { 'data-col-row': c.name, 'aria-selected': String(view.column === c.name), class: view.column === c.name ? 'sel' : '' },
        el('td', {}, el('button', { type: 'button', class: 'eu-h', onclick: () => selectColumn(n, c.name) }, c.name)),
        el('td', {}, c.type || '—'),
        el('td', {}, c.key ? `${keyMark(c.key) ? keyMark(c.key) + ' ' : ''}${kindLabel(c.key)}` : '—'),
        el('td', {}, c.ref ? (r && d.byName.has(r.entity) ? el('button', { type: 'button', class: 'eu-h', 'aria-label': `${t('sz.goto')}: ${c.ref}`, onclick: () => gotoRef(c.ref) }, '→ ' + c.ref) : c.ref) : '—'),
        el('td', {}, (c.description || '') + (c.origin === '補完' ? ` (${t('sz.supp')})` : '') + (c.mismatch && c.mismatch.length ? ` ≠ ${t('sz.mismatch')}: ` + c.mismatch.map((x) => `${x.field}=${x.supplement}`).join(', ') : '')));
    });
    side.replaceChildren(
      el('h3', {}, e.name, ' ', el('span', { class: 'badge' }, `${t('sz.badge.selected')}`)),
      e.description ? el('p', { class: 'mini' }, e.description) : null,
      el('p', { class: 'mini' }, d.clusterOf.get(n) ? t('sz.cluster', { id: d.clusterOf.get(n).id, n: d.clusterOf.get(n).count }) : ''),
      el('p', { class: 'mini', 'data-testid': 'sz-storage' }, `${t('arch.storage')}: ${d.storage.get(n).length ? d.storage.get(n).map((s) => `${s.kind} · ${s.name}`).join(' / ') : 'なし'}`),
      rels.length ? el('ul', { class: 'sz-rels' }, rels.map((x) => { const o = x.from === n ? x.to : x.from; return el('li', {}, `${x.from} → ${x.to} · ${kindLabel(x.kind)} `, el('button', { type: 'button', class: 'eu-h', onclick: () => select(o) }, o)); })) : null,
      e.columns.length ? tb([t('sz.c.name'), t('sz.c.type'), t('sz.c.key'), t('sz.c.ref'), t('sz.c.desc')], colRows) : el('p', { class: 'sz-nocols' }, '⚠ ' + t('sz.nocols')));
  }

  function renderAlt() {
    const body = altBox.querySelector('.sz-alt-body');
    const caption = (s) => el('h4', {}, s);
    const tbl = (head, rows) => el('table', { class: 'eu-sub sz-tbl' }, el('thead', {}, el('tr', {}, head.map((h) => el('th', { scope: 'col' }, h)))), el('tbody', {}, rows));
    const LIM = 400;
    const clusterRows = d.clusters.map((c) => el('tr', { 'data-alt-cluster': c.id }, el('td', {}, c.id), el('td', {}, String(c.count)), el('td', {}, c.entities.join('、'))));
    const edgeRows = d.edges.slice(0, LIM).map((e) => el('tr', { 'data-alt-edge': '' }, el('td', {}, e.from), el('td', {}, e.to), el('td', {}, kindLabel(e.kind)),
      el('td', {}, e.sources.map((s) => `${s.file}${s.line ? ':' + s.line : ''}`).join(' / ') || '—')));
    const list = view.selected ? d.ents.filter((e) => e.name === view.selected) : d.ents;
    const colRows = [];
    for (const e of list) {
      if (!e.columns.length) { colRows.push(el('tr', { 'data-alt-col': '' }, el('td', {}, e.name), el('td', { colspan: 4 }, t('sz.nocols')))); continue; }
      for (const c of e.columns) colRows.push(el('tr', { 'data-alt-col': '' }, el('td', {}, e.name), el('td', {}, c.name), el('td', {}, c.type || '—'), el('td', {}, c.key ? kindLabel(c.key) : '—'), el('td', {}, c.ref || '—')));
      if (colRows.length > LIM) break;
    }
    body.replaceChildren(
      d.arch ? caption(`${t('arch.locations')}（${d.locations.length}）`) : null,
      d.arch ? tbl([t('arch.kind'), t('arch.place'), t('arch.apps'), t('arch.data'), t('arch.links')], d.locations.map((l) => el('tr', { 'data-alt-location': `${l.kind}|${l.name}` },
        el('td', {}, l.kind), el('td', {}, l.name), el('td', {}, l.apps.join('、') || 'なし'), el('td', {}, l.data.join('、') || 'なし'),
        el('td', {}, l.links.map((x) => `→ ${x.to}（${x.direction}）`).join(' / ') || 'なし')))) : null,
      d.arch ? caption(t('arch.storage')) : null,
      d.arch ? tbl([t('eu.entity'), t('arch.storage')], d.names.map((n) => el('tr', { 'data-alt-storage': n }, el('td', {}, n), el('td', {}, d.storage.get(n).map((s) => `${s.kind} · ${s.name}`).join(' / ') || 'なし')))) : null,
      caption(`${t('sz.alt.clusters')}（${t('sz.entities', { n: d.names.length })}）`), tbl(['ID', '#', t('eu.entity')], clusterRows),
      caption(`${t('sz.alt.edges')}（${d.edges.length}）`), tbl([t('sz.from'), t('sz.to'), t('sz.kind'), t('sz.src')], edgeRows),
      d.edges.length > LIM ? el('p', { class: 'mini' }, t('sz.moreuses', { n: d.edges.length - LIM })) : null,
      caption(`${t('sz.alt.cols')}（${d.totalColumns}）`), tbl([t('eu.entity'), t('sz.c.name'), t('sz.c.type'), t('sz.c.key'), t('sz.c.ref')], colRows.slice(0, LIM)),
      colRows.length > LIM ? el('p', { class: 'mini' }, t('sz.more', { n: colRows.length - LIM })) : null);
  }

  // ------------------------------------------------------------ view operations
  function ensureCenter() { if (view.cx == null) { const c = worldCenter(d); view.cx = c.x; view.cy = c.y; } }
  function recentre(p) { view.cx = p.x; view.cy = p.y; }
  function visibleRectWorld(pad = 0) {
    const k = ctx.k(), a = renderer.toWorld(0, 0), b = renderer.toWorld(W, H);
    return { x0: Math.min(a.x, b.x) - pad / k, y0: Math.min(a.y, b.y) - pad / k, x1: Math.max(a.x, b.x) + pad / k, y1: Math.max(a.y, b.y) + pad / k };
  }
  function selCenter() { return view.selected && d.pos.has(view.selected) ? boxCenter(d, view.selected, levelNow()) : null; }

  // Zoom keeps `wpt` (world point) at the screen position `spt`.
  function zoomAround(n, wpt, spt) {
    view.scale = clamp(n, MIN_SCALE, MAX_SCALE);
    const w1 = renderer.toWorld(spt.x, spt.y);
    view.cx += wpt.x - w1.x; view.cy += wpt.y - w1.y;
  }
  function setScale(n, anchor) {
    ensureCenter();
    n = clamp(Number(n) || 1, MIN_SCALE, MAX_SCALE);
    const prev = view.scale;
    if (anchor) zoomAround(n, renderer.toWorld(anchor.x, anchor.y), anchor);
    else {
      const sc = selCenter();
      if (sc) {   // the target of the zoom never leaves the screen
        const s0 = renderer.toScreen(sc.x, sc.y);
        const inside = s0.x > 24 && s0.x < W - 24 && s0.y > 24 && s0.y < H - 24;
        zoomAround(n, sc, inside ? s0 : { x: W / 2, y: H / 2 });
      } else if (prev <= 1.0001 && n > 1) {
        const c = d.clusters[0], r = d.rects.get(c.id);
        view.scale = n; recentre({ x: r.x + r.w / 2, y: r.y + r.h / 2 });
      } else view.scale = n;
    }
    if (view.scale <= 1.0001) recentre(worldCenter(d));
    afterChange('zoom');
  }
  function zoomBy(f, anchor) { setScale(view.scale * f, anchor); }
  function setLevel(lv) { setScale(lv === 'detail' ? th.detail : lv === 'mid' ? Math.max(th.mid, view.scale < th.detail ? view.scale : th.mid) : 1); }
  function rotate(dy, dp) { view.yaw += dy; view.pitch = clamp(view.pitch + dp, 0.35, 1.5); afterChange('rotate'); }
  function panBy(dx, dy) {
    ensureCenter();
    const a = renderer.toWorld(W / 2, H / 2), b = renderer.toWorld(W / 2 + dx, H / 2 + dy);
    view.cx += a.x - b.x; view.cy += a.y - b.y;
    afterChange('pan');
  }
  function afterChange(why) { sync(); draw(); notify(why); }

  function ensureVisible(name) {
    if (!d.pos.has(name)) return;
    const c = boxCenter(d, name, levelNow() === 'overview' ? 'mid' : levelNow());
    const s = renderer.toScreen(c.x, c.y);
    if (s.x < 30 || s.x > W - 30 || s.y < 30 || s.y > H - 30) recentre(c);
  }
  function select(name, o = {}) {
    ensureCenter();
    view.selected = name && d.byName.has(name) ? name : null;
    view.column = view.selected ? (o.column || null) : null;
    if (view.selected && o.centre !== false) { if (o.force) recentre(boxCenter(d, view.selected, levelNow() === 'overview' ? 'mid' : levelNow())); else ensureVisible(view.selected); }
    afterChange('select');
  }
  function selectColumn(entity, col) { view.selected = entity; view.column = col; afterChange('select'); }
  function gotoRef(ref) {
    const r = parseRef(ref);
    if (!r || !d.byName.has(r.entity)) return;
    select(r.entity, { column: r.column, force: true });
  }
  function zoomToCluster(id) {
    ensureCenter();
    const r = d.rects.get(id); if (!r) return;
    const need = 0.9 * Math.min(W / r.w, H / r.h) / (renderer.fit() || 1);
    view.scale = clamp(Math.max(th.mid, need >= th.detail ? th.detail - 0.01 : need), MIN_SCALE, MAX_SCALE);
    recentre({ x: r.x + r.w / 2, y: r.y + r.h / 2 });
    afterChange('zoom');
  }
  function step(dir) {
    const order = d.clusters.flatMap((c) => c.entities).filter((n) => matches(n, d));
    if (!order.length) return;
    const i = order.indexOf(view.selected);
    select(order[(i < 0 ? (dir > 0 ? 0 : order.length - 1) : (i + dir + order.length) % order.length)], { force: true });
  }
  function stepColumn(dir) {
    const e = view.selected && d.byName.get(view.selected);
    if (!e || !e.columns.length) return;
    const i = e.columns.findIndex((c) => c.name === view.column);
    selectColumn(e.name, e.columns[(i < 0 ? (dir > 0 ? 0 : e.columns.length - 1) : (i + dir + e.columns.length) % e.columns.length)].name);
  }
  function tip(html, x, y) {
    if (!html) { tipEl.hidden = true; return; }
    const r = viewport.getBoundingClientRect();
    tipEl.innerHTML = html; tipEl.hidden = false;
    tipEl.style.left = Math.min(x - r.left + 14, Math.max(0, r.width - 280)) + 'px';
    tipEl.style.top = Math.min(y - r.top + 14, Math.max(0, r.height - 90)) + 'px';
  }

  // ------------------------------------------------------------ drawing
  function draw() {
    if (dead) return;
    if (W < 2 || H < 2) return;
    ensureCenter();
    const t0 = performance.now();
    renderer.draw();
    const lv = levelNow();
    // virtualisation notice (NFR-PERF-004 AC-184): what was left out of the drawing, never of the data
    const drawn = renderer.drawnEntities ? renderer.drawnEntities() : null;
    if (lv === 'overview') note.textContent = t('sz.entities', { n: d.names.length }) + ` · ${d.clusters.length} ${t('sz.alt.clusters')}`;
    else if (drawn != null && drawn < d.names.length) note.textContent = t('sz.omitted', { n: d.names.length - drawn }) + ` · ${t('sz.entities', { n: d.names.length })} / ${d.totalColumns} ${t('sz.alt.cols')}`;
    else note.textContent = `${t('sz.entities', { n: d.names.length })} / ${d.totalColumns} ${t('sz.alt.cols')}`;
    if (view.filter && !d.names.some((n) => matches(n, d))) note.textContent = t('sz.nothing');
    root.dataset.drawMs = String(Math.round(performance.now() - t0));
    if (!ready) { ready = true; root.dataset.ready = 'true'; }
  }
  function schedule() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; draw(); }); }

  const ro = new ResizeObserver(() => {
    const r = viewport.getBoundingClientRect();
    W = Math.round(r.width); H = Math.round(r.height);
    if (renderer.resize) renderer.resize(W, H);
    draw();
  });
  ro.observe(viewport);

  // ------------------------------------------------------------ pointer / wheel / keyboard
  const pt = (e) => { const r = viewport.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  viewport.addEventListener('wheel', (e) => {
    e.preventDefault();
    zoomBy(Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0015)), pt(e));
  }, { passive: false });
  viewport.addEventListener('pointerdown', (e) => {
    if (e.target.closest('input,button,a')) return;
    ptrs.set(e.pointerId, pt(e));
    moved = false;
    if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, scale: view.scale }; }
    else dragStart = { ...pt(e), rotate: renderer.kind === '3d' && (e.shiftKey || e.button === 2), moved: false };
    viewport.focus({ preventScroll: true });
  });
  window.addEventListener('pointermove', onMove);
  window.addEventListener('pointerup', onUp);
  window.addEventListener('pointercancel', onUp);
  function onMove(e) {
    if (!ptrs.has(e.pointerId)) { hoverAt(e); return; }
    const p = pt(e), prev = ptrs.get(e.pointerId);
    ptrs.set(e.pointerId, p);
    if (pinch && ptrs.size >= 2) {
      const [a, b] = [...ptrs.values()];
      const dist = Math.hypot(a.x - b.x, a.y - b.y) || 1;
      moved = true;
      zoomAround(pinch.scale * dist / pinch.dist, renderer.toWorld((a.x + b.x) / 2, (a.y + b.y) / 2), { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
      if (view.scale <= 1.0001) recentre(worldCenter(d));
      sync(); schedule(); return;
    }
    if (!dragStart) return;
    if (!dragStart.moved && Math.hypot(p.x - dragStart.x, p.y - dragStart.y) < CLICK_DRAG_PX) return;
    dragStart.moved = true; moved = true;
    const dx = p.x - prev.x, dy = p.y - prev.y;
    if (dragStart.rotate) { view.yaw += dx * 0.01; view.pitch = clamp(view.pitch - dy * 0.005, 0.35, 1.5); }
    else if (view.scale > 1.0001) {
      const a = renderer.toWorld(p.x - dx, p.y - dy), b = renderer.toWorld(p.x, p.y);
      view.cx += a.x - b.x; view.cy += a.y - b.y;
    }
    schedule();
  }
  function onUp(e) {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.delete(e.pointerId);
    if (ptrs.size < 2) pinch = null;
    if (!ptrs.size) {
      const was = dragStart; dragStart = null;
      if (was && !was.moved && renderer.pick && e.target === renderer.el) pickClick(pt(e));
      setTimeout(() => { moved = false; }, 0);
      if (was && was.moved) notify('pan');
    }
  }
  function pickClick(p) {
    const h = renderer.pick(p.x, p.y);
    if (!h) { return; }
    if (h.type === 'cluster') zoomToCluster(h.id);
    else if (h.type === 'column') selectColumn(h.entity, h.name);
    else if (h.type === 'entity') select(h.name);
  }
  function hoverAt(e) {
    if (!renderer.pick || e.target !== renderer.el) return;
    const h = renderer.pick(pt(e).x, pt(e).y);
    tip(h ? hoverHtml(h) : '', e.clientX, e.clientY);
  }
  viewport.addEventListener('keydown', (e) => {
    if (e.target.closest('input')) return;
    const k = e.key, big = e.shiftKey ? 3 : 1, stepPx = 60 * big;
    let used = true;
    if (k === '+' || k === '=' || k === 'PageUp') zoomBy(1.25);
    else if (k === '-' || k === '_' || k === 'PageDown') zoomBy(1 / 1.25);
    else if (k === '0') setScale(1);
    else if (k === '1') setLevel('overview');
    else if (k === '2') setLevel('mid');
    else if (k === '3') setLevel('detail');
    else if (k === 'ArrowLeft') panBy(-stepPx, 0);
    else if (k === 'ArrowRight') panBy(stepPx, 0);
    else if (k === 'ArrowUp') panBy(0, -stepPx);
    else if (k === 'ArrowDown') panBy(0, stepPx);
    else if (k === 'n' || k === ']') step(1);
    else if (k === 'p' || k === '[') step(-1);
    else if (k === '.') stepColumn(1);
    else if (k === ',') stepColumn(-1);
    else if (k === 'Enter' || k === 'g') {
      const e2 = view.selected && d.byName.get(view.selected), c = e2 && e2.columns.find((x) => x.name === view.column);
      if (c && c.ref) gotoRef(c.ref);
      else if (!view.selected) step(1);
      else used = k === 'Enter';
    } else if (k === 'Escape') { if (view.selected) select(null); else used = false; }
    else if (renderer.kind === '3d' && (k === 'q' || k === 'e')) rotate(k === 'q' ? -0.26 : 0.26, 0);
    else if (renderer.kind === '3d' && (k === 'r' || k === 'f')) rotate(0, k === 'r' ? 0.1 : -0.1);
    else used = false;
    if (used) { e.preventDefault(); e.stopPropagation(); }
  });
  function hoverHtml(h) {
    if (h.type === 'cluster') { const c = d.clusters.find((x) => x.id === h.id); return c ? `<b>${t('sz.cluster', { id: c.id, n: c.count })}</b>` : ''; }
    const e = d.byName.get(h.name || h.entity);
    if (!e) return '';
    return `<b>${esc(e.name)}</b><div class="mini">${esc(e.description || '')}</div><div class="mini">${e.columns.length ? e.columns.length + ' ' + t('sz.alt.cols') : esc(t('sz.nocols'))}</div>`;
  }

  // ------------------------------------------------------------ language, store, api
  const offLang = onLang(() => {
    bar.querySelectorAll('[data-level-btn]').forEach((b) => { const lv = b.dataset.levelBtn; b.textContent = t('sz.level.' + lv); b.setAttribute('aria-label', `${t('sz.level')}: ${t('sz.level.' + lv)}`); });
    altBox.querySelector('summary').textContent = t('sz.alt');
    hint.textContent = t('sz.hint');
    filterIn.setAttribute('aria-label', t('sz.filter')); filterIn.placeholder = t('sz.filter');
    sync(); draw();
  });
  const offStore = store.on('select', (ev) => {   // search / drawer selection of an entity node moves the view too
    if (ev && ev.id && String(ev.id).startsWith('ent:')) { const n = String(ev.id).slice(4); if (d.byName.has(n) && n !== view.selected) select(n, { force: true }); }
  });
  const offView = onView((why) => { if (why === 'external') { sync(); draw(); } });

  const eabkView = {
    setScale: (n) => setScale(n),
    getState: () => stateOf(d, th),
    select: (n, col) => select(n, { column: col || null, force: true }),
    zoomIn: () => zoomBy(1.25), zoomOut: () => zoomBy(1 / 1.25), fit: () => setScale(1),
    setLevel, setFilter: (s) => { view.filter = String(s || ''); filterIn.value = view.filter; sync(); draw(); },
    mode: opts.mode, renderer: renderer.kind,
  };
  window.eabkView = eabkView;
  sync();

  return {
    destroy() {
      dead = true;
      ro.disconnect(); offLang(); offStore(); offView();
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      cancelAnimationFrame(raf);
      if (window.eabkView === eabkView) delete window.eabkView;
      renderer.destroy?.();
    },
  };
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// Whether the map routes show the entity view first: the model has relations or columns to show (FR-1027).
export function hasEntityStructure(m) {
  const e = m && m.entities;
  if (!e || !e.entities || !e.entities.length) return false;
  return e.entities.some((x) => x.columns && x.columns.length) || (e.relations || []).some((r) => r.scope === 'entity');
}
export const wantsEntityView = (m) => (view.tab === 'entities' ? true : view.tab === 'graph' ? false : hasEntityStructure(m));
export function setTab(tab) { view.tab = tab; }
