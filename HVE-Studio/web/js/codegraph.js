// FR-1091: code relations — functions, methods and classes as a living map (calls, references, inheritance).
// Data: GET /api/codegraph (code_graph.py, read only). Drawing: Canvas 2D with a small force simulation of our own
// (repulsion on a grid, link springs, a pull towards the file each symbol lives in, collision) — no external library, nothing fetched.
// prefers-reduced-motion: the layout is solved at once and drawn still; no particles, no pulses.
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, token, vscodeUrl, showTip, hideTip, esc } from './ui.js';
import { reduced } from './viz.js';

const KINDS = ['function', 'method', 'class', 'module'];
const KIND_VAR = { function: '--viz-fn', method: '--viz-method', class: '--viz-class', module: '--viz-module' };
const ALPHA_MIN = 0.004, ALPHA_DECAY = 0.016, VELOCITY_KEEP = 0.62, LINK_LEN = 34, CELL = 64;
const LIMITS = [100, 200, 300, 500, 800, 1200, 2000];

const hash = (s) => { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; };
const baseName = (p) => p.split('/').pop();
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const isDark = () => document.documentElement.dataset.theme === 'dark';

// Pure helpers (exported for tests)
export function hopMap(start, out, inn, depth) {
  const down = new Map([[start, 0]]), up = new Map([[start, 0]]);
  const walk = (map, adj) => {
    let front = [start];
    for (let d = 1; d <= depth; d++) {
      const next = [];
      for (const id of front) for (const e of adj.get(id) || []) {
        const other = adj === out ? e.t : e.s;
        if (!map.has(other)) { map.set(other, d); next.push(other); }
      }
      front = next;
    }
  };
  walk(down, out); walk(up, inn);
  return { down, up };
}

export function mount(host) {
  const page = el('div', { class: 'page cg-page' });
  host.append(page);
  const ui = { q: '', kinds: new Set(KINDS), tests: false, guess: false, ref: true, labels: false, flow: true, limit: 500, color: 'kind', paused: false, depth: 2 };
  let data = null, byId = new Map(), out = new Map(), inn = new Map(), loadError = false;
  let sims = [], simById = new Map(), links = [], pos = new Map();
  let sel = null, hover = null, hops = null, waveAt = 0;
  let alpha = 1, destroyed = false, dirty = true, raf = 0, follow = false;
  const cam = { x: 0, y: 0, z: 1, tx: 0, ty: 0, tz: 1, fit: true };
  let canvas, ctx, stage, W = 0, H = 0, dpr = 1, ro = null;
  let statsEl, detailEl, listEl, limitVal, pauseBtn;

  // ------------------------------------------------------------ data
  async function load() {
    page.replaceChildren(el('h1', {}, t('cg.title')), el('div', { class: 'mini', role: 'status' }, t('cg.loading')));
    try {
      const r = await fetch('/api/codegraph', { cache: 'no-store' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      data = await r.json();
    } catch (e) { loadError = true; if (!destroyed) page.replaceChildren(el('h1', {}, t('cg.title')), el('div', { class: 'warnbox' }, t('cg.error') + ' ' + String(e.message || e))); return; }
    if (destroyed) return;
    byId = new Map(data.nodes.map((n) => [n.id, n]));
    out = new Map(); inn = new Map();
    for (const e of data.edges) {
      if (!byId.has(e.s) || !byId.has(e.t)) continue;
      (out.get(e.s) || out.set(e.s, []).get(e.s)).push(e);
      (inn.get(e.t) || inn.set(e.t, []).get(e.t)).push(e);
    }
    const p = new URLSearchParams(location.hash.split('?')[1] || '');
    if (p.get('find')) ui.q = p.get('find');
    if (p.get('sym') && byId.has(p.get('sym'))) sel = p.get('sym');
  }

  const edgeAllowed = (e) => (e.kind !== 'ref' || ui.ref) && (e.conf !== 'name' || ui.guess);
  const nodeAllowed = (n) => ui.kinds.has(n.kind) && (ui.tests || !n.test);
  const matches = (n, q) => n.name.toLowerCase().includes(q) || n.qual.toLowerCase().includes(q) || n.file.toLowerCase().includes(q);

  function visibleSet() {
    const ok = new Set(data.nodes.filter(nodeAllowed).map((n) => n.id));
    const deg = new Map();
    for (const e of data.edges) {
      if (!ok.has(e.s) || !ok.has(e.t) || !edgeAllowed(e)) continue;
      deg.set(e.s, (deg.get(e.s) || 0) + 1); deg.set(e.t, (deg.get(e.t) || 0) + 1);
    }
    const ranked = [...deg.entries()].sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1)).slice(0, ui.limit).map((x) => x[0]);
    const vis = new Set(ranked);
    const q = ui.q.trim().toLowerCase();
    if (q) { let n = 0; for (const node of data.nodes) if (ok.has(node.id) && matches(node, q)) { vis.add(node.id); if (++n >= 80) break; } }
    if (sel && byId.has(sel)) {
      vis.add(sel);
      for (const e of [...(out.get(sel) || []), ...(inn.get(sel) || [])]) if (edgeAllowed(e)) { vis.add(e.s); vis.add(e.t); }
    }
    return { vis, deg, total: ok.size };
  }

  function build() {
    const { vis, deg } = visibleSet();
    const files = new Map();
    for (const id of vis) {
      const n = byId.get(id);
      (files.get(n.file) || files.set(n.file, []).get(n.file)).push(n);
    }
    const prev = pos;
    pos = new Map();
    const ordered = [...vis].map((id) => byId.get(id)).sort((a, b) => (deg.get(b.id) || 0) - (deg.get(a.id) || 0));
    const spread = Math.sqrt(ordered.length) * 26 + 40;
    sims = ordered.map((n) => {
      let p = prev.get(n.id);
      if (!p) {
        let anchor = null;
        for (const e of [...(out.get(n.id) || []), ...(inn.get(n.id) || [])]) { const o = prev.get(e.s === n.id ? e.t : e.s); if (o) { anchor = o; break; } }
        const h = hash(n.id), a = (h % 3600) / 3600 * Math.PI * 2, rr = ((h >>> 12) % 1000) / 1000;
        p = anchor ? { x: anchor.x + Math.cos(a) * 24, y: anchor.y + Math.sin(a) * 24 } : { x: Math.cos(a) * spread * (0.2 + rr), y: Math.sin(a) * spread * (0.2 + rr) };
      }
      const r = clamp(3 + Math.sqrt(n.loc) * 0.75 + Math.sqrt(deg.get(n.id) || 0) * 0.7, 3, 15) * (n.kind === 'class' ? 1.25 : 1);
      const s = { n, id: n.id, x: p.x, y: p.y, vx: 0, vy: 0, r, deg: deg.get(n.id) || 0, fx: null, fy: null };
      pos.set(n.id, s);
      return s;
    });
    simById = new Map(sims.map((s) => [s.id, s]));
    links = [];
    for (const e of data.edges) {
      const a = simById.get(e.s), b = simById.get(e.t);
      if (a && b && edgeAllowed(e)) links.push({ e, a, b, phase: (hash(e.s + e.t) % 1000) / 1000 });
    }
    clusterIndex = new Map();
    for (const s of sims) (clusterIndex.get(s.n.file) || clusterIndex.set(s.n.file, []).get(s.n.file)).push(s);
    stats = { shown: sims.length, links: links.length };
    computeHops();
    alpha = 1; cam.fit = true; dirty = true;
    if (reduced()) { settle(); fit(true); }
    else { for (let i = 0; i < 40; i++) tick(); }
    renderChrome();
  }
  let clusterIndex = new Map(), stats = { shown: 0, links: 0 };

  function computeHops() {
    const focus = sel;
    hops = focus && simById.has(focus) ? hopMap(focus, out, inn, ui.depth) : null;
    waveAt = performance.now();
  }

  // ------------------------------------------------------------ force simulation
  function tick() {
    const n = sims.length;
    if (!n) return;
    const grid = new Map();
    for (const s of sims) {
      const k = Math.floor(s.x / CELL) + ',' + Math.floor(s.y / CELL);
      (grid.get(k) || grid.set(k, []).get(k)).push(s);
    }
    const charge = 46 * alpha;
    for (const s of sims) {
      const cx = Math.floor(s.x / CELL), cy = Math.floor(s.y / CELL);
      for (let gx = cx - 1; gx <= cx + 1; gx++) for (let gy = cy - 1; gy <= cy + 1; gy++) {
        const cell = grid.get(gx + ',' + gy);
        if (!cell) continue;
        for (const o of cell) {
          if (o === s) continue;
          let dx = s.x - o.x, dy = s.y - o.y, d2 = dx * dx + dy * dy;
          if (d2 === 0) { dx = (hash(s.id) % 7) - 3 || 1; dy = (hash(o.id) % 7) - 3 || 1; d2 = dx * dx + dy * dy; }
          const d = Math.sqrt(d2), min = s.r + o.r + 3;
          if (d < CELL * 1.5) { const f = charge / d2; s.vx += dx * f; s.vy += dy * f; }
          if (d < min) { const push = (min - d) / d * 0.5; s.vx += dx * push; s.vy += dy * push; }
        }
      }
    }
    for (const l of links) {
      const { a, b } = l;
      let dx = b.x + b.vx - a.x - a.vx, dy = b.y + b.vy - a.y - a.vy;
      const d = Math.sqrt(dx * dx + dy * dy) || 1;
      const k = (d - LINK_LEN - a.r - b.r) / d * alpha * 0.34 / Math.min(Math.max(a.deg, 1), Math.max(b.deg, 1));
      dx *= k; dy *= k;
      const wb = a.deg / (a.deg + b.deg || 1);
      b.vx -= dx * (1 - wb); b.vy -= dy * (1 - wb); a.vx += dx * wb; a.vy += dy * wb;
    }
    // each file is a "room": members are drawn towards the file's centre and the rooms keep apart
    const rooms = [];
    for (const members of clusterIndex.values()) {
      let cx = 0, cy = 0;
      for (const s of members) { cx += s.x; cy += s.y; }
      cx /= members.length; cy /= members.length;
      const rad = 14 + Math.sqrt(members.length) * 16;
      rooms.push({ members, cx, cy, rad });
      if (members.length > 1) for (const s of members) { s.vx += (cx - s.x) * 0.1 * alpha; s.vy += (cy - s.y) * 0.1 * alpha; }
    }
    if (rooms.length <= 260) {
      for (let i = 0; i < rooms.length; i++) for (let j = i + 1; j < rooms.length; j++) {
        const A = rooms[i], B = rooms[j];
        const dx = B.cx - A.cx, dy = B.cy - A.cy, d = Math.sqrt(dx * dx + dy * dy) || 1, min = A.rad + B.rad + 18;
        if (d >= min) continue;
        const push = (min - d) / d * 0.12 * alpha;
        for (const s of A.members) { s.vx -= dx * push; s.vy -= dy * push; }
        for (const s of B.members) { s.vx += dx * push; s.vy += dy * push; }
      }
    }
    for (const s of sims) {
      s.vx -= s.x * 0.0035 * alpha; s.vy -= s.y * 0.0035 * alpha;
      if (s.fx != null) { s.x = s.fx; s.y = s.fy; s.vx = s.vy = 0; continue; }
      s.vx *= VELOCITY_KEEP; s.vy *= VELOCITY_KEEP;
      s.x += s.vx; s.y += s.vy;
    }
    alpha += (0 - alpha) * ALPHA_DECAY;
    dirty = true;
  }
  function settle() { for (let i = 0; i < 320 && alpha > ALPHA_MIN; i++) tick(); alpha = 0; }
  const reheat = (a = 0.35) => { if (reduced()) { settle(); } else alpha = Math.max(alpha, a); dirty = true; };

  // ------------------------------------------------------------ camera
  function fit(now) {
    if (!sims.length || !W) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const s of sims) { x0 = Math.min(x0, s.x - s.r); y0 = Math.min(y0, s.y - s.r); x1 = Math.max(x1, s.x + s.r); y1 = Math.max(y1, s.y + s.r); }
    const bw = Math.max(40, x1 - x0), bh = Math.max(40, y1 - y0);
    cam.tz = clamp(Math.min(W / bw, H / bh) * 0.88, 0.03, 3);
    cam.tx = (x0 + x1) / 2; cam.ty = (y0 + y1) / 2;
    if (now || reduced()) { cam.x = cam.tx; cam.y = cam.ty; cam.z = cam.tz; }
    dirty = true;
  }
  const toWorld = (px, py) => ({ x: (px - W / 2) / cam.z + cam.x, y: (py - H / 2) / cam.z + cam.y });
  function nodeAt(px, py) {
    const w = toWorld(px, py);
    let best = null, bd = Infinity;
    for (const s of sims) {
      const d = Math.hypot(s.x - w.x, s.y - w.y), reach = Math.max(s.r, 6 / cam.z);
      if (d <= reach && d < bd) { best = s; bd = d; }
    }
    return best;
  }

  // ------------------------------------------------------------ drawing
  function colorOfSim(s) {
    if (ui.color === 'folder') {
      const parts = s.n.file.split('/'), key = parts.slice(0, Math.min(2, parts.length - 1)).join('/');
      return `hsl(${hash(key) % 360} 72% ${isDark() ? 66 : 38}%)`;
    }
    return token(KIND_VAR[s.n.kind] || '--viz-file');
  }
  function curve(l) {
    const { a, b } = l;
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy) || 1;
    const k = 0.14 * len;
    return { ax: a.x, ay: a.y, bx: b.x, by: b.y, cx: (a.x + b.x) / 2 - dy / len * k, cy: (a.y + b.y) / 2 + dx / len * k, len };
  }
  const at = (c, u) => { const v = 1 - u; return { x: v * v * c.ax + 2 * v * u * c.cx + u * u * c.bx, y: v * v * c.ay + 2 * v * u * c.cy + u * u * c.by }; };

  function draw(now) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.setTransform(dpr * cam.z, 0, 0, dpr * cam.z, dpr * (W / 2 - cam.x * cam.z), dpr * (H / 2 - cam.y * cam.z));
    const dark = isDark();
    const fg = token('--color-fg-default'), bg = token('--color-bg-canvas'), accent = token('--viz-call'), guess = token('--viz-guess');
    const focus = sel ? hops : hover ? hopMap(hover, out, inn, 1) : null;
    const inFocus = (id) => !focus || focus.down.has(id) || focus.up.has(id);
    const q = ui.q.trim().toLowerCase();
    const flowOn = ui.flow && !reduced() && !ui.paused;

    // file rooms
    for (const [file, members] of clusterIndex) {
      if (members.length < 2) continue;
      let cx = 0, cy = 0;
      for (const s of members) { cx += s.x; cy += s.y; }
      cx /= members.length; cy /= members.length;
      let rad = 0;
      for (const s of members) rad = Math.max(rad, Math.hypot(s.x - cx, s.y - cy) + s.r);
      rad += 10;
      const lit = !focus || members.some((s) => inFocus(s.id));
      ctx.globalAlpha = lit ? 0.07 : 0.025;
      ctx.fillStyle = fg;
      ctx.beginPath(); ctx.arc(cx, cy, rad, 0, 6.2832); ctx.fill();
      ctx.globalAlpha = lit ? 0.28 : 0.1;
      ctx.strokeStyle = fg; ctx.lineWidth = 1 / cam.z;
      ctx.stroke();
      if (cam.z * rad > 26) {
        ctx.globalAlpha = lit ? 0.7 : 0.25;
        ctx.fillStyle = fg;
        const size = clamp(11 / cam.z, 5, 60);
        ctx.font = `700 ${size}px ui-monospace, Consolas, monospace`;
        ctx.textAlign = 'center';
        ctx.fillText(baseName(file), cx, cy - rad - 4 / cam.z);
      }
    }

    // an edge is "hot" when it lies on a call path leading away from the centre (callees) or towards it (callers)
    const isHot = (f, l) => {
      const a = l.a.id, b = l.b.id;
      return (f.down.has(a) && f.down.has(b) && f.down.get(b) === f.down.get(a) + 1) || (f.up.has(a) && f.up.has(b) && f.up.get(a) === f.up.get(b) + 1);
    };

    // edges
    ctx.lineCap = 'round';
    for (const l of links) {
      const hot = !!focus && isHot(focus, l);
      const c = curve(l);
      const guessy = l.e.conf === 'name';
      ctx.globalAlpha = hot ? 0.9 : focus ? 0.04 : clamp(0.16 + 0.5 / Math.sqrt(links.length / 60 + 1), 0.1, 0.34);
      ctx.strokeStyle = guessy ? guess : accent;
      ctx.lineWidth = (hot ? 1.8 : 0.8) / Math.min(cam.z, 1.5);
      ctx.setLineDash(l.e.kind === 'ref' ? [4 / cam.z, 3 / cam.z] : guessy ? [2 / cam.z, 3 / cam.z] : l.e.kind === 'inherit' ? [10 / cam.z, 2 / cam.z] : []);
      ctx.beginPath(); ctx.moveTo(c.ax, c.ay); ctx.quadraticCurveTo(c.cx, c.cy, c.bx, c.by); ctx.stroke();
      if (hot || cam.z > 1.6) {
        const p = at(c, 0.86), q2 = at(c, 0.9), ang = Math.atan2(q2.y - p.y, q2.x - p.x), ar = 4 / Math.min(cam.z, 1.6) + 1;
        const tx = c.bx - Math.cos(ang) * l.b.r, ty = c.by - Math.sin(ang) * l.b.r;
        ctx.setLineDash([]); ctx.fillStyle = guessy ? guess : accent;
        ctx.beginPath(); ctx.moveTo(tx, ty); ctx.lineTo(tx - Math.cos(ang - 0.45) * ar * 1.6, ty - Math.sin(ang - 0.45) * ar * 1.6);
        ctx.lineTo(tx - Math.cos(ang + 0.45) * ar * 1.6, ty - Math.sin(ang + 0.45) * ar * 1.6); ctx.closePath(); ctx.fill();
      }
      if (flowOn && (hot || links.length <= 500) && l.e.kind !== 'inherit') {
        const u = (now * 0.00009 * (hot ? 1.6 : 1) + l.phase) % 1, pt = at(c, u);
        ctx.setLineDash([]);
        ctx.globalAlpha = hot ? 1 : focus ? 0 : 0.7;
        ctx.fillStyle = dark ? '#ffffff' : accent;
        ctx.beginPath(); ctx.arc(pt.x, pt.y, (hot ? 2.4 : 1.5) / Math.min(cam.z, 2), 0, 6.2832); ctx.fill();
      }
    }
    ctx.setLineDash([]);

    // nodes
    const waveAge = now - waveAt;
    for (const s of sims) {
      const lit = inFocus(s.id);
      const hit = q && matches(s.n, q);
      const base = colorOfSim(s);
      const dim = focus ? !lit : (q ? !hit : false);
      ctx.globalAlpha = dim ? 0.14 : 1;
      if (dark && !dim) {
        const g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, s.r * 3.2);
        g.addColorStop(0, base); g.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = 0.28 + Math.min(0.3, s.deg / 60);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(s.x, s.y, s.r * 3.2, 0, 6.2832); ctx.fill();
        ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;
      }
      ctx.fillStyle = base;
      ctx.beginPath();
      if (s.n.kind === 'class') { const r = s.r; ctx.rect(s.x - r, s.y - r, r * 2, r * 2); }
      else if (s.n.kind === 'module') { ctx.moveTo(s.x, s.y - s.r * 1.2); ctx.lineTo(s.x + s.r * 1.1, s.y + s.r * 0.8); ctx.lineTo(s.x - s.r * 1.1, s.y + s.r * 0.8); ctx.closePath(); }
      else ctx.arc(s.x, s.y, s.r, 0, 6.2832);
      ctx.fill();
      ctx.lineWidth = 1 / cam.z; ctx.strokeStyle = bg; ctx.globalAlpha = dim ? 0.1 : 0.9; ctx.stroke();
      if (s.n.test) { ctx.globalAlpha = dim ? 0.1 : 0.8; ctx.strokeStyle = fg; ctx.setLineDash([2 / cam.z, 2 / cam.z]); ctx.beginPath(); ctx.arc(s.x, s.y, s.r + 2 / cam.z, 0, 6.2832); ctx.stroke(); ctx.setLineDash([]); }
      if (hops && !reduced()) {
        const h = Math.min(hops.down.has(s.id) ? hops.down.get(s.id) : 99, hops.up.has(s.id) ? hops.up.get(s.id) : 99);
        if (h < 99) {
          const x = waveAge - h * 240, power = Math.exp(-(x * x) / (2 * 150 * 150));
          if (power > 0.03) { ctx.globalAlpha = power; ctx.strokeStyle = fg; ctx.lineWidth = 2 / cam.z; ctx.beginPath(); ctx.arc(s.x, s.y, s.r + (4 + power * 10) / cam.z, 0, 6.2832); ctx.stroke(); }
        }
      }
      if (s.id === sel) { ctx.globalAlpha = 1; ctx.strokeStyle = fg; ctx.lineWidth = 2.5 / cam.z; ctx.beginPath(); ctx.arc(s.x, s.y, s.r + 5 / cam.z, 0, 6.2832); ctx.stroke(); }
    }
    if (hops && waveAge < (ui.depth + 2) * 240 + 800) dirty = true;

    // labels: the busiest first, at most one per screen cell
    ctx.globalAlpha = 1; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    const size = clamp(11 / Math.max(cam.z, 0.6), 8, 16);
    ctx.font = `600 ${size}px ui-monospace, Consolas, monospace`;
    ctx.lineJoin = 'round'; ctx.lineWidth = 3 / Math.max(cam.z, 0.6);
    const need = cam.z > 2.2 ? 0 : cam.z > 1.2 ? 3 : cam.z > 0.7 ? 8 : 18;
    const taken = new Set();
    let labelled = 0;
    for (const s of sims) {
      const must = s.id === sel || s.id === hover || (hops && inFocus(s.id) && labelled < 40) || (q && matches(s.n, q));
      if (!must && !ui.labels && s.deg < need) continue;
      if (!must && focus && !inFocus(s.id)) continue;
      const sx = (s.x - cam.x) * cam.z + W / 2, sy = (s.y - cam.y) * cam.z + H / 2;
      if (sx < -40 || sy < -20 || sx > W + 40 || sy > H + 20) continue;
      const key = Math.floor(sx / 90) + ',' + Math.floor(sy / 16);
      if (!must && taken.has(key)) continue;
      taken.add(key); labelled++;
      ctx.globalAlpha = must ? 1 : 0.85;
      ctx.strokeStyle = bg; ctx.strokeText(s.n.name, s.x + s.r + 3 / cam.z, s.y);
      ctx.fillStyle = fg; ctx.fillText(s.n.name, s.x + s.r + 3 / cam.z, s.y);
    }
    ctx.globalAlpha = 1;
  }

  function frame(now) {
    if (destroyed) return;
    raf = requestAnimationFrame(frame);
    if (document.hidden || !ctx) return;
    if (!ui.paused && alpha > ALPHA_MIN) tick();
    else if (alpha <= ALPHA_MIN && alpha !== 0) { alpha = 0; dirty = true; }
    if (cam.fit && alpha > ALPHA_MIN && !reduced()) fit(false);
    else if (follow && sel && alpha > ALPHA_MIN) { const s = simById.get(sel); if (s) { cam.tx = s.x; cam.ty = s.y; } }
    const ease = reduced() ? 1 : 0.16;
    const moving = Math.abs(cam.tx - cam.x) + Math.abs(cam.ty - cam.y) > 0.05 / cam.z || Math.abs(cam.tz - cam.z) > 0.0005;
    if (moving) {
      cam.x += (cam.tx - cam.x) * ease; cam.y += (cam.ty - cam.y) * ease; cam.z += (cam.tz - cam.z) * ease;
      dirty = true;
    }
    const flowing = ui.flow && !reduced() && !ui.paused && sims.length && links.length <= 500;
    if (dirty || flowing || hover || sel) { draw(now); dirty = false; }
    canvas.dataset.settled = String(alpha <= ALPHA_MIN);
    canvas.dataset.nodeCount = String(sims.length);
    canvas.dataset.linkCount = String(links.length);
    canvas.dataset.selected = sel || '';
  }

  // ------------------------------------------------------------ interaction
  function resize() {
    if (!stage) return;
    const r = stage.getBoundingClientRect();
    W = Math.max(200, Math.floor(r.width)); H = Math.max(200, Math.floor(r.height));
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.floor(W * dpr); canvas.height = Math.floor(H * dpr);
    if (cam.fit) fit(true);
    dirty = true;
  }
  function select(id, { fly = true } = {}) {
    sel = id && byId.has(id) ? id : null;
    const missing = (id) => [...(out.get(id) || []), ...(inn.get(id) || [])].some((e) => edgeAllowed(e) && (!simById.has(e.s) || !simById.has(e.t)));
    const needBuild = sel && (!simById.has(sel) || missing(sel));
    if (needBuild) build(); else computeHops();
    cam.fit = false; follow = !!fly;
    const s = sel && simById.get(sel);
    if (s && fly) { cam.tx = s.x; cam.ty = s.y; cam.tz = clamp(Math.max(cam.z, 1.1), 0.1, 3); if (reduced()) { cam.x = cam.tx; cam.y = cam.ty; cam.z = cam.tz; } }
    if (!sel && fly) { cam.fit = true; fit(false); }
    renderDetail(); renderList(); dirty = true;
  }
  function bindCanvas() {
    let drag = null, pan = null, moved = 0;
    const local = (e) => { const r = canvas.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    canvas.addEventListener('pointerdown', (e) => {
      canvas.setPointerCapture?.(e.pointerId);
      const p = local(e), hit = nodeAt(p.x, p.y); moved = 0; cam.fit = false; follow = false; hideTip();
      if (hit) { drag = hit; hit.fx = hit.x; hit.fy = hit.y; reheat(0.25); }
      else pan = { x: p.x, y: p.y, cx: cam.x, cy: cam.y };
    });
    canvas.addEventListener('pointermove', (e) => {
      const p = local(e);
      if (drag) { const w = toWorld(p.x, p.y); moved += 1; drag.fx = w.x; drag.fy = w.y; dirty = true; return; }
      if (pan) { moved += 1; cam.x = cam.tx = pan.cx - (p.x - pan.x) / cam.z; cam.y = cam.ty = pan.cy - (p.y - pan.y) / cam.z; dirty = true; return; }
      const hit = nodeAt(p.x, p.y);
      const id = hit ? hit.id : null;
      if (id !== hover) { hover = id; dirty = true; canvas.style.cursor = id ? 'pointer' : ''; }
      if (hit) {
        const n = hit.n;
        showTip(`<b>${esc(n.qual)}</b><div class="mini">${esc(t('cg.kind.' + n.kind))} · ${esc(n.file)}:${n.line}</div>${n.doc ? `<div>${esc(n.doc)}</div>` : ''}`, e.clientX, e.clientY);
      } else hideTip();
    });
    const up = () => {
      if (drag) { const hit = drag; drag.fx = drag.fy = null; drag = null; if (moved < 3) select(sel === hit.id ? null : hit.id, { fly: false }); }
      else if (pan) { pan = null; if (moved < 3) select(null, { fly: false }); }
      dirty = true;
    };
    canvas.addEventListener('pointerup', up);
    canvas.addEventListener('pointercancel', up);
    canvas.addEventListener('pointerleave', () => { if (hover) { hover = null; dirty = true; } hideTip(); });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const p = local(e), before = toWorld(p.x, p.y);
      const z = clamp(cam.z * Math.exp(-e.deltaY * 0.0016), 0.03, 6);
      cam.fit = false; follow = false; cam.z = cam.tz = z;
      cam.x = cam.tx = before.x - (p.x - W / 2) / z; cam.y = cam.ty = before.y - (p.y - H / 2) / z;
      dirty = true;
    }, { passive: false });
    canvas.addEventListener('dblclick', () => { cam.fit = true; fit(false); });
    canvas.addEventListener('keydown', (e) => {
      const step = 40 / cam.z;
      if (e.key === 'Escape') select(null);
      else if (e.key === '+' || e.key === '=') { cam.tz = clamp(cam.z * 1.2, 0.03, 6); }
      else if (e.key === '-') { cam.tz = clamp(cam.z / 1.2, 0.03, 6); }
      else if (e.key === '0') { cam.fit = true; fit(false); }
      else if (e.key === 'ArrowLeft') cam.tx -= step; else if (e.key === 'ArrowRight') cam.tx += step;
      else if (e.key === 'ArrowUp') cam.ty -= step; else if (e.key === 'ArrowDown') cam.ty += step;
      else return;
      cam.fit = cam.fit && e.key === '0'; e.preventDefault(); dirty = true;
    });
  }

  // ------------------------------------------------------------ DOM
  const chip = (cls, text) => el('span', { class: cls }, text);
  function symButton(n, extra) {
    return el('button', { type: 'button', class: 'cg-sym' + (n.id === sel ? ' on' : ''), 'data-testid': 'cg-item', 'data-id': n.id, onclick: () => select(n.id) },
      el('i', { class: 'dot', style: { background: token(KIND_VAR[n.kind] || '--viz-file') } }), el('span', { class: 'mono cg-name' }, n.qual),
      el('small', { class: 'mini' }, ` ${baseName(n.file)}:${n.line}`), extra || '');
  }
  function relList(title, edges, pick) {
    const items = edges.filter(edgeAllowed).map((e) => ({ e, n: byId.get(pick(e)) })).filter((x) => x.n);
    items.sort((a, b) => (b.n.deg || 0) - (a.n.deg || 0));
    return el('div', { class: 'cg-rel' }, el('h3', {}, `${title} (${items.length})`),
      items.length ? el('div', { class: 'cg-rel-list' }, ...items.slice(0, 60).map(({ e, n }) => symButton(n, [e.conf === 'name' ? el('span', { class: 'badge' }, t('cg.guess')) : '', e.kind === 'ref' ? el('span', { class: 'badge' }, t('cg.legend.ref')) : '']))) : el('div', { class: 'mini' }, t('cg.none')));
  }
  function renderDetail() {
    if (!detailEl) return;
    const n = sel && byId.get(sel);
    if (!n) { detailEl.replaceChildren(el('p', { class: 'mini' }, t('cg.detail.none'))); return; }
    const file = data.files.find((f) => f.path === n.file);
    const reqs = (file?.reqs || []).filter((id) => store.nodes.has(id));
    const inh = (out.get(n.id) || []).filter((e) => e.kind === 'inherit');
    detailEl.replaceChildren(
      el('h2', { class: 'mono', 'data-testid': 'cg-name' }, n.qual),
      el('div', { class: 'row' }, el('span', { class: 'badge' }, t('cg.kind.' + n.kind)), el('span', { class: 'badge' }, t('cg.lines', { n: n.loc })), el('span', { class: 'badge' }, t('cg.deg', { n: n.deg }))),
      n.doc ? el('p', {}, n.doc) : '',
      el('div', { class: 'mini' }, t('cg.file') + ': ', el('a', { class: 'mono', href: vscodeUrl(n.file, n.line), title: t('cg.vscode') }, `${n.file}:${n.line}`)),
      reqs.length ? el('div', { class: 'mini cg-reqs' }, t('cg.reqs') + ': ', ...reqs.map((id) => el('a', { class: 'chip', href: '#/map2d?select=' + encodeURIComponent(id) }, id))) : '',
      relList(t('cg.callers'), (inn.get(n.id) || []).filter((e) => e.kind !== 'inherit'), (e) => e.s),
      relList(t('cg.callees'), (out.get(n.id) || []).filter((e) => e.kind !== 'inherit'), (e) => e.t),
      inh.length ? relList(t('cg.inherits'), inh, (e) => e.t) : '');
  }
  function renderList() {
    if (!listEl) return;
    const q = ui.q.trim().toLowerCase();
    let items = sims.map((s) => s.n);
    if (q) items = items.filter((n) => matches(n, q));
    items.sort((a, b) => b.deg - a.deg);
    listEl.replaceChildren(...(items.length ? items.slice(0, 200).map((n) => el('li', {}, symButton(n))) : [el('li', { class: 'mini' }, t('cg.nohit'))]));
  }
  function renderStats() {
    if (!statsEl || !data) return;
    const s = data.stats;
    statsEl.replaceChildren(t('cg.stats', { nodes: s.nodes, edges: s.edges, files: s.files, shown: stats.shown, unresolved: s.unresolved }),
      s.truncated ? ' ' + t('cg.trunc') : '', s.skipped ? ' ' + t('cg.skipped', { n: s.skipped }) : '');
  }
  function toggle(label, key, testid, after) {
    return el('label', { class: 'row mini cg-toggle' }, el('input', { type: 'checkbox', 'data-testid': testid, checked: ui[key] || null, onchange: (e) => { ui[key] = e.target.checked; (after || rebuild)(); } }), label);
  }
  const rebuild = () => { build(); renderDetail(); renderList(); };
  function renderChrome() { renderStats(); renderList(); renderDetail(); if (limitVal) limitVal.textContent = t('cg.limit.val', { n: ui.limit }); }

  function render() {
    if (!data) return;
    hideTip();
    canvas = el('canvas', { 'data-testid': 'cg-canvas', tabindex: '0', role: 'img', 'aria-label': t('cg.canvas.aria') });
    ctx = canvas.getContext('2d');
    stage = el('div', { class: 'cg-stage' }, canvas,
      el('div', { class: 'cg-legend mini', 'aria-hidden': 'true' },
        ...KINDS.map((k) => el('span', {}, el('i', { class: 'dot', style: { background: token(KIND_VAR[k]) } }), t('cg.kind.' + k))),
        el('span', {}, '—— ' + t('cg.legend.call')), el('span', {}, '- - ' + t('cg.legend.ref')), el('span', {}, '·· ' + t('cg.legend.guess'))),
      el('div', { class: 'cg-hint mini' }, t('cg.hint')));
    statsEl = el('div', { class: 'mini', role: 'status', 'data-testid': 'cg-stats' });
    detailEl = el('div', { class: 'cg-detail', 'data-testid': 'cg-detail', 'aria-live': 'polite' });
    listEl = el('ul', { class: 'cg-list', 'data-testid': 'cg-list' });
    limitVal = el('span', { class: 'mini' });
    pauseBtn = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'cg-pause', onclick: () => { ui.paused = !ui.paused; pauseBtn.textContent = t(ui.paused ? 'cg.resume' : 'cg.pause'); dirty = true; } }, t(ui.paused ? 'cg.resume' : 'cg.pause'));
    const search = el('input', { type: 'search', 'data-testid': 'cg-search', value: ui.q, placeholder: t('cg.search'), 'aria-label': t('cg.search.aria'),
      oninput: (e) => { ui.q = e.target.value; clearTimeout(search._t); search._t = setTimeout(rebuild, 160); },
      onkeydown: (e) => { if (e.key === 'Enter') { const q = ui.q.trim().toLowerCase(); const hit = q && data.nodes.filter(nodeAllowed).find((n) => matches(n, q)); if (hit) select(hit.id); } } });
    const limit = el('input', { type: 'range', min: '0', max: String(LIMITS.length - 1), step: '1', value: String(Math.max(0, LIMITS.indexOf(ui.limit))), 'data-testid': 'cg-limit', 'aria-label': t('cg.limit'),
      oninput: (e) => { ui.limit = LIMITS[+e.target.value]; limitVal.textContent = t('cg.limit.val', { n: ui.limit }); clearTimeout(limit._t); limit._t = setTimeout(rebuild, 120); } });
    const depth = el('input', { type: 'range', min: '1', max: '4', step: '1', value: String(ui.depth), 'data-testid': 'cg-depth', 'aria-label': t('cg.depth', { n: ui.depth }),
      oninput: (e) => { ui.depth = +e.target.value; depthLbl.textContent = t('cg.depth', { n: ui.depth }); computeHops(); dirty = true; } });
    const depthLbl = el('span', { class: 'mini' }, t('cg.depth', { n: ui.depth }));
    const color = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'cg-color', onclick: () => { ui.color = ui.color === 'kind' ? 'folder' : 'kind'; color.textContent = t('cg.color.' + ui.color); dirty = true; } }, t('cg.color.' + ui.color));
    const kindChips = KINDS.map((k) => el('label', { class: 'row mini cg-toggle' }, el('input', { type: 'checkbox', 'data-testid': 'cg-kind-' + k, checked: ui.kinds.has(k) || null,
      onchange: (e) => { if (e.target.checked) ui.kinds.add(k); else ui.kinds.delete(k); rebuild(); } }), el('i', { class: 'dot', style: { background: token(KIND_VAR[k]) } }), t('cg.kind.' + k)));
    page.replaceChildren(el('h1', {}, t('cg.title')), el('p', { class: 'sub' }, t('cg.sub')), el('p', {}, el('a', { class: 'btn ghost', href: '#/floorplan', 'data-testid': 'open-floorplan' }, t('fp.floorplan'))),
      el('div', { class: 'tbar cg-bar' }, search, ...kindChips,
        toggle(t('cg.show.tests'), 'tests', 'cg-tests'), toggle(t('cg.show.ref'), 'ref', 'cg-ref'), toggle(t('cg.show.guess'), 'guess', 'cg-guess'),
        toggle(t('cg.show.labels'), 'labels', 'cg-labels', () => { dirty = true; }), toggle(t('cg.show.flow'), 'flow', 'cg-flow', () => { dirty = true; })),
      el('div', { class: 'tbar cg-bar' }, el('label', { class: 'row mini' }, t('cg.limit'), limit, limitVal), el('label', { class: 'row mini' }, depth, depthLbl), color, pauseBtn,
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'cg-fit', onclick: () => { cam.fit = true; fit(false); } }, t('cg.fit')),
        el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'cg-relayout', onclick: () => { pos = new Map(); build(); } }, t('cg.relayout'))),
      statsEl,
      el('div', { class: 'cg-body' }, stage, el('aside', { class: 'card cg-side' }, detailEl, el('h3', {}, t('cg.list')), listEl)));
    bindCanvas();
    ro?.disconnect();
    ro = new ResizeObserver(resize); ro.observe(stage);
    resize();
    if (!data.nodes.length) { stage.replaceChildren(el('div', { class: 'empty' }, t('cg.empty'))); return; }
    renderChrome();
    if (!raf) raf = requestAnimationFrame(frame);
  }

  const view = { mode: 'codegraph', select: (id) => select(id), getState: () => ({ dim: 'codegraph', nodes: sims.length, links: links.length, selected: sel, settled: alpha <= ALPHA_MIN,
    zoom: cam.z, shown: stats.shown, guess: ui.guess }) };
  window.eabkView = view;
  const offLang = onLang(() => { if (data) { render(); build(); } });
  load().then(() => { if (data && !destroyed) { render(); build(); if (sel) select(sel); } });
  return {
    destroy() {
      destroyed = true; cancelAnimationFrame(raf); ro?.disconnect(); offLang(); hideTip();
      if (window.eabkView === view) window.eabkView = undefined;
    },
  };
}
