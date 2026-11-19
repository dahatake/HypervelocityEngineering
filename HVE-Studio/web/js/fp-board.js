// FR-1092: the board — cards and pills laid out with ELK (layered, left to right, three partitions: used by | inside | uses),
// lines routed at right angles, wheel zoom and drag pan, and descriptions that drop away as you zoom out.
// Drawing only: what is on the board comes from fp-data.js, and what a click does is decided by the caller.
import { el, svgEl } from './ui.js';
import { reduced } from './viz.js';

const SIZE = { node: [236, 116], file: [236, 108], route: [236, 84], folder: [236, 96], symbol: [236, 76], pill: [176, 38] };
const KIND_VAR = { import: '--viz-call', call: '--viz-call', http: '--viz-method', rpc: '--viz-module', event: '--viz-class', queue: '--viz-class', data: '--viz-table', config: '--color-border-strong' };
export const ICONS = {
  ui: 'M3 5h18v11H3zM8 20h8M12 16v4', service: 'M4 4h16v6H4zM4 14h16v6H4zM8 7h.01M8 17h.01', worker: 'M13 2 4 14h7l-1 8 9-12h-7z', library: 'M12 3 3 8l9 5 9-5zM3 13l9 5 9-5M3 17l9 5 9-5',
  feature: 'M5 4h6v6H5zM13 4h6v6h-6zM5 12h6v6H5zM15 12l4 3-4 3z', data: 'M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zM5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3',
  config: 'M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M6 14v6', test: 'M9 3h6M10 3v6L5 19a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-10V3', script: 'M4 5h16v14H4zM7 10l3 2-3 2M12 15h5',
  infra: 'M7 18a4 4 0 0 1-.5-8A5.5 5.5 0 0 1 17 8.5 3.8 3.8 0 0 1 17 18z', external: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.6 3.5 5.6 3.5 9S14.5 18.4 12 21c-2.5-2.6-3.5-5.6-3.5-9S9.5 5.6 12 3z',
  file: 'M7 3h7l4 4v14H7zM14 3v4h4', route: 'M4 12h14M13 6l6 6-6 6', folder: 'M3 6h6l2 2h10v11H3z', symbol: 'M8 6 3 12l5 6M16 6l5 6-5 6', codebase: 'M12 3 3 8l9 5 9-5zM3 13l9 5 9-5',
};
export const icon = (name, size = 16) => svgEl('svg', { class: 'fp-ic', viewBox: '0 0 24 24', width: size, height: size, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.8', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true' }, svgEl('path', { d: ICONS[name] || ICONS.file }));

let elkPromise = null;
export function loadElk() {
  if (window.ELK) return Promise.resolve(new window.ELK());
  elkPromise ||= new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/vendor/elk.bundled.js';
    s.onload = () => (window.ELK ? resolve(new window.ELK()) : reject(new Error('ELK missing')));
    s.onerror = () => reject(new Error('ELK failed to load'));
    document.head.append(s);
  });
  return elkPromise;
}

const partOf = (kind) => (kind === 'external' ? 2 : kind === 'ui' || kind === 'test' || kind === 'script' || kind === 'infra' ? 0 : 1);

async function layoutBoard(cards, edges, partitions) {
  const children = cards.map((c) => ({ id: c.id, width: c.w, height: c.h, layoutOptions: { 'elk.partitioning.partition': String(partitions.get(c.id) ?? 1) } }));
  const ids = new Set(cards.map((c) => c.id));
  const kedges = edges.filter((e) => ids.has(e.a) && ids.has(e.b) && e.a !== e.b).map((e, i) => ({ id: 'e' + i, sources: [e.a], targets: [e.b] }));
  try {
    const elk = await loadElk();
    const g = await elk.layout({
      id: 'root', children, edges: kedges,
      layoutOptions: { 'elk.algorithm': 'layered', 'elk.direction': 'RIGHT', 'elk.partitioning.activate': 'true', 'elk.edgeRouting': 'ORTHOGONAL',
        'elk.layered.spacing.nodeNodeBetweenLayers': '120', 'elk.spacing.nodeNode': '30', 'elk.spacing.edgeNode': '22', 'elk.spacing.edgeEdge': '10',
        'elk.layered.spacing.edgeNodeBetweenLayers': '24', 'elk.layered.crossingMinimization.strategy': 'LAYER_SWEEP', 'elk.padding': '[top=48,left=24,bottom=24,right=24]' },
    });
    const pos = new Map(g.children.map((c) => [c.id, { x: c.x, y: c.y }]));
    const routes = new Map();
    const keyed = edges.filter((e) => ids.has(e.a) && ids.has(e.b) && e.a !== e.b);
    for (const ke of g.edges || []) {
      const e = keyed[+ke.id.slice(1)], sec = ke.sections?.[0];
      if (e && sec) routes.set(e, [sec.startPoint, ...(sec.bendPoints || []), sec.endPoint]);
    }
    return { pos, routes, width: g.width, height: g.height };
  } catch {
    return fallbackLayout(cards, partitions);
  }
}
function fallbackLayout(cards, partitions) {
  const cols = [[], [], []];
  for (const c of cards) cols[partitions.get(c.id) ?? 1].push(c);
  const pos = new Map();
  let x = 24, height = 0;
  for (const col of cols) {
    if (!col.length) continue;
    let y = 48;
    for (const c of col) { pos.set(c.id, { x, y }); y += c.h + 24; }
    height = Math.max(height, y);
    x += 236 + 120;
  }
  return { pos, routes: new Map(), width: x, height };
}

const roundedPath = (pts, r = 10) => {
  if (pts.length < 2) return '';
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const p0 = pts[i - 1], p1 = pts[i], p2 = pts[i + 1];
    const l1 = Math.hypot(p1.x - p0.x, p1.y - p0.y), l2 = Math.hypot(p2.x - p1.x, p2.y - p1.y), k = Math.min(r, l1 / 2, l2 / 2);
    if (!k) { d += ` L${p1.x},${p1.y}`; continue; }
    d += ` L${p1.x - ((p1.x - p0.x) / l1) * k},${p1.y - ((p1.y - p0.y) / l1) * k} Q${p1.x},${p1.y} ${p1.x + ((p2.x - p1.x) / l2) * k},${p1.y + ((p2.y - p1.y) / l2) * k}`;
  }
  const e = pts[pts.length - 1];
  return d + ` L${e.x},${e.y}`;
};

export function createBoard(host, hooks) {
  const stage = el('div', { class: 'fp-stage', 'data-testid': 'fp-stage', tabindex: '0', role: 'application' });
  const anim = el('div', { class: 'fp-anim' });
  stage.append(anim);
  host.append(stage);
  const cam = { x: 0, y: 0, z: 1 };
  let world = null, svg = null, current = null, token = 0, signalRaf = 0;
  const cardEls = new Map(), edgeEls = [];

  const apply = () => {
    if (!world) return;
    world.style.transform = `translate(${cam.x}px, ${cam.y}px) scale(${cam.z})`;
    world.dataset.zoom = cam.z < 0.5 ? 'far' : cam.z < 0.85 ? 'mid' : 'near';
    stage.style.setProperty('--tz', String(Math.min(2.4, Math.max(1, 0.8 / cam.z))));
    hooks.onZoom?.(cam.z);
  };
  const fit = (instant) => {
    if (!current) return;
    const r = stage.getBoundingClientRect();
    const z = Math.min(1.05, Math.max(0.12, Math.min((r.width - 48) / current.width, (r.height - 96) / current.height)));
    cam.z = z; cam.x = (r.width - current.width * z) / 2; cam.y = Math.max(24, (r.height - current.height * z) / 2);
    apply();
    if (!instant && !reduced()) anim.animate([{ opacity: 0.4 }, { opacity: 1 }], { duration: 220 });
  };

  async function show(spec) {
    const my = ++token;
    const { cards, edges, partitions, brackets, state } = spec;
    cards.forEach((c) => { const s = SIZE[c.pill ? 'pill' : c.type] || SIZE.file; c.w = s[0]; c.h = s[1]; });
    const lay = await layoutBoard(cards, edges, partitions);
    if (my !== token) return;
    const W = Math.max(lay.width, 360), H = Math.max(lay.height, 240);
    svg = svgEl('svg', { class: 'fp-svg', width: W, height: H, viewBox: `0 0 ${W} ${H}`, 'aria-hidden': 'true' });
    world = el('div', { class: 'fp-world', style: { width: W + 'px', height: H + 'px' } }, svg);
    cardEls.clear(); edgeEls.length = 0;
    const byId = new Map(cards.map((c) => [c.id, c]));
    for (const c of cards) { const p = lay.pos.get(c.id) || { x: 0, y: 0 }; c.x = p.x; c.y = p.y; }
    // lines first (under the cards)
    for (const e of edges) {
      const a = byId.get(e.a), b = byId.get(e.b);
      if (!a || !b) continue;
      const pts = lay.routes.get(e) || [{ x: a.x + a.w, y: a.y + a.h / 2 }, { x: (a.x + a.w + b.x) / 2, y: a.y + a.h / 2 }, { x: (a.x + a.w + b.x) / 2, y: b.y + b.h / 2 }, { x: b.x, y: b.y + b.h / 2 }];
      const d = roundedPath(pts);
      const color = `var(${KIND_VAR[e.kind] || '--viz-call'})`;
      const g = svgEl('g', { class: 'fp-line', 'data-a': e.a, 'data-b': e.b, 'data-testid': 'fp-edge', style: `--lc:${color}` },
        svgEl('path', { class: 'fp-edge', d, fill: 'none', 'stroke-width': (1.3 + Math.min(2.4, Math.log2(e.w + 1) * 0.5)).toFixed(2) }),
        svgEl('path', { class: 'fp-hit', d, fill: 'none', 'stroke-width': 14 }),
        svgEl('circle', { class: 'fp-port', cx: pts[0].x, cy: pts[0].y, r: 3 }), svgEl('circle', { class: 'fp-port', cx: pts[pts.length - 1].x, cy: pts[pts.length - 1].y, r: 3 }));
      g.addEventListener('pointerenter', (ev) => hooks.onEdgeHover?.(e, ev));
      g.addEventListener('pointermove', (ev) => hooks.onEdgeHover?.(e, ev));
      g.addEventListener('pointerleave', () => hooks.onEdgeHover?.(null));
      g.addEventListener('contextmenu', (ev) => { ev.preventDefault(); hooks.onContext?.({ edge: e }, ev); });
      g.addEventListener('click', (ev) => { ev.stopPropagation(); hooks.onEdgeClick?.(e); });
      svg.append(g);
      edgeEls.push({ e, g, d });
    }
    for (const br of brackets || []) {
      const ids = br.ids.filter((id) => lay.pos.has(id));
      if (!ids.length) continue;
      const x0 = Math.min(...ids.map((id) => byId.get(id).x)), x1 = Math.max(...ids.map((id) => byId.get(id).x + byId.get(id).w));
      world.append(el('div', { class: 'fp-bracket mini', style: { left: x0 + 'px', width: x1 - x0 + 'px', top: '14px' } }, el('span', {}, br.label)));
    }
    for (const c of cards) {
      const node = hooks.renderCard(c, state);
      node.style.cssText += `;left:${c.x}px;top:${c.y}px;width:${c.w}px;height:${c.h}px`;
      node.dataset.id = c.id;
      node.addEventListener('click', (ev) => { ev.stopPropagation(); hooks.onSelect?.(c.id); });
      node.addEventListener('dblclick', (ev) => { ev.stopPropagation(); hooks.onOpen?.(c.id); });
      node.addEventListener('contextmenu', (ev) => { ev.preventDefault(); ev.stopPropagation(); hooks.onContext?.({ id: c.id }, ev); });
      node.addEventListener('pointerenter', (ev) => hooks.onHover?.(c.id, ev));
      node.addEventListener('pointerleave', () => hooks.onHover?.(null));
      node.addEventListener('keydown', (ev) => { if (ev.key === 'Enter') { ev.preventDefault(); hooks.onOpen?.(c.id); } else if (ev.key === ' ') { ev.preventDefault(); hooks.onSelect?.(c.id); } });
      world.append(node);
      cardEls.set(c.id, node);
    }
    current = { width: W, height: H, cards: byId, edges };
    anim.replaceChildren(world);
    if (spec.keepCamera) apply(); else fit(true);
    if (!reduced() && spec.transition) anim.animate([{ opacity: 0, transform: `scale(${spec.transition === 'in' ? 1.14 : 0.88})` }, { opacity: 1, transform: 'none' }], { duration: 300, easing: 'ease-out' });
    paint(spec.paint || {});
    hooks.onShown?.();
  }

  /** Dim what is not connected to `focus`, ring `marks`, tag recent work. */
  function paint({ focus = null, marks = null, dim = null } = {}) {
    if (!current) return;
    const near = new Set();
    if (focus) { near.add(focus); for (const e of current.edges) { if (e.a === focus) near.add(e.b); if (e.b === focus) near.add(e.a); } }
    for (const [id, node] of cardEls) {
      node.classList.toggle('sel', id === focus && !!hooks.isSelected?.(id));
      node.classList.toggle('dim', (!!focus && !near.has(id)) || (!!dim && !dim.has(id)));
      node.classList.toggle('mark', !!marks && marks.has(id));
    }
    const hot = [];
    for (const { e, g } of edgeEls) {
      const on = !!focus && (e.a === focus || e.b === focus);
      g.classList.toggle('hot', on);
      g.classList.toggle('faint', (!!focus && !on) || (!!dim && !(dim.has(e.a) && dim.has(e.b))));
      if (on) hot.push(g.querySelector('.fp-edge'));
    }
    cancelAnimationFrame(signalRaf);
    if (hot.length && !reduced()) {
      const tick = (now) => { const off = -((now * 0.03) % 16); for (const p of hot) p.setAttribute('stroke-dashoffset', String(off)); signalRaf = requestAnimationFrame(tick); };
      signalRaf = requestAnimationFrame(tick);
    }
  }

  function signal(a, b, ms = 1100) {
    const hit = edgeEls.find(({ e }) => (e.a === a && e.b === b) || (e.a === b && e.b === a));
    if (!hit || reduced()) return;
    const path = hit.g.querySelector('.fp-edge'), len = path.getTotalLength();
    const dot = svgEl('circle', { class: 'fp-signal', r: 5 });
    svg.append(dot);
    const t0 = performance.now();
    const step = (now) => {
      const u = Math.min(1, (now - t0) / ms), pt = path.getPointAtLength(len * (hit.e.a === a ? u : 1 - u));
      dot.setAttribute('cx', pt.x); dot.setAttribute('cy', pt.y);
      if (u < 1) requestAnimationFrame(step); else dot.remove();
    };
    requestAnimationFrame(step);
  }
  function centerOn(ids) {
    if (!current) return;
    const rs = ids.map((id) => current.cards.get(id)).filter(Boolean);
    if (!rs.length) return;
    const x0 = Math.min(...rs.map((c) => c.x)), y0 = Math.min(...rs.map((c) => c.y)), x1 = Math.max(...rs.map((c) => c.x + c.w)), y1 = Math.max(...rs.map((c) => c.y + c.h));
    const r = stage.getBoundingClientRect();
    const z = Math.min(1.1, Math.max(0.2, Math.min((r.width - 120) / (x1 - x0), (r.height - 160) / (y1 - y0))));
    cam.z = z; cam.x = r.width / 2 - ((x0 + x1) / 2) * z; cam.y = r.height / 2 - ((y0 + y1) / 2) * z;
    if (!reduced()) world.animate([{ opacity: 0.7 }, { opacity: 1 }], { duration: 200 });
    apply();
  }
  const zoomBy = (f) => {
    const r = stage.getBoundingClientRect(), px = r.width / 2, py = r.height / 2, z = Math.min(2.5, Math.max(0.12, cam.z * f));
    cam.x = px - (px - cam.x) * (z / cam.z); cam.y = py - (py - cam.y) * (z / cam.z); cam.z = z; apply();
  };

  // pointer: drag the background to pan, wheel to zoom
  let pan = null, moved = 0;
  stage.addEventListener('pointerdown', (e) => { if (e.target.closest('.fp-card,.fp-line')) return; pan = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y }; moved = 0; stage.setPointerCapture?.(e.pointerId); });
  stage.addEventListener('pointermove', (e) => { if (!pan) return; moved++; cam.x = pan.cx + e.clientX - pan.x; cam.y = pan.cy + e.clientY - pan.y; apply(); });
  const end = () => { if (pan && moved < 3) hooks.onBackground?.(); pan = null; };
  stage.addEventListener('pointerup', end); stage.addEventListener('pointercancel', () => { pan = null; });
  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = stage.getBoundingClientRect(), px = e.clientX - r.left, py = e.clientY - r.top, z = Math.min(2.5, Math.max(0.12, cam.z * Math.exp(-e.deltaY * 0.0016)));
    cam.x = px - (px - cam.x) * (z / cam.z); cam.y = py - (py - cam.y) * (z / cam.z); cam.z = z; apply();
  }, { passive: false });
  stage.addEventListener('dblclick', (e) => { if (!e.target.closest('.fp-card')) fit(); });
  stage.addEventListener('contextmenu', (e) => { if (!e.target.closest('.fp-card,.fp-line')) { e.preventDefault(); hooks.onContext?.({}, e); } });
  new ResizeObserver(() => { if (current && !pan) { /* keep the camera; only an initial fit needs the size */ } }).observe(stage);
  return { show, paint, fit, zoomBy, signal, centerOn, stage, partOf, get zoom() { return cam.z; }, get cards() { return current?.cards; }, destroy() { cancelAnimationFrame(signalRaf); token++; } };
}
