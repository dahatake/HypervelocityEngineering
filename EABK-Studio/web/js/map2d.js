// 2D traceability map: goals -> requirements -> parts/data -> source -> tests, on a pannable, zoomable canvas.
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, colorOf, TYPE_COLOR, STATUS_COLOR, showTip, hideTip, nodeTip } from './ui.js';

const COL = { goal: 0, req: 1, ac: 2, entity: 3, part: 3, api: 3, table: 3, param: 3, question: 3, file: 4, component: 4, case: 5, persona: 6, external: 6 };
const LAYER_TYPES = ['goal', 'req', 'ac', 'entity', 'part', 'api', 'table', 'param', 'question', 'file', 'case'];
const DEFAULT_ON = new Set(['goal', 'req', 'entity', 'part', 'api', 'table', 'file', 'case']);
const rowH = 22, groupGap = 30, TOP = 70;
const prefs = { layers: new Set(DEFAULT_ON), color: 'type' };
const IMPL_COLOR = { done: '#34e0a1', none: '#ff5c7a', unlisted: '#8aa1b5' };

export function mount(host) {
  host.append(el('h1', { class: 'sr-only' }, '2D マップ'));
  const canvas = el('canvas', { class: 'fill' });
  const mini = el('canvas', { class: 'minimap', width: 380, height: 240 });
  const toolbar = el('div', { class: 'toolbar' });
  const statusBox = el('div', { class: 'status' });
  const hint = el('div', { class: 'hint' });
  host.append(canvas, toolbar, mini, statusBox, hint);
  const ctx = canvas.getContext('2d');
  const mctx = mini.getContext('2d');

  let W = 0, H = 0, dpr = 1;
  let cam = { x: 0, y: 0, k: 0.2 };
  let pos = new Map(), groups = [], order = [], bounds = { x0: 0, y0: 0, x1: 1, y1: 1 };
  let dirty = true, raf = 0, anim = null, tour = null, dead = false;
  let drag = null, moved = false;

  // ---------- layout
  function visibleNodes() {
    const on = prefs.layers;
    const out = [];
    for (const n of store.nodes.values()) {
      if (n.type === 'component') continue;
      if (n.type === 'persona' || n.type === 'external') continue;
      if (!on.has(n.type)) continue;
      if (n.deg === 0 && !['goal', 'req', 'file', 'case'].includes(n.type)) continue;
      out.push(n);
    }
    return out;
  }

  const subW = 400, layerGap = 170, targetH = 2200;
  function layout() {
    pos = new Map(); groups = [];
    const nodes = visibleNodes();
    const cols = [...new Set(nodes.map((n) => COL[n.type]))].sort((a, b) => a - b);
    const byCol = new Map(cols.map((c) => [c, nodes.filter((n) => COL[n.type] === c)]));
    const subsOf = new Map();
    const bary = (n) => {
      let s = 0, c = 0;
      for (const a of store.adj.get(n.id) || []) { const p = pos.get(a.id); if (p) { s += p.gy; c++; } }
      return c ? s / c : null;
    };
    // Lays a column out top-to-bottom in groups and wraps it into sub-columns once it exceeds targetH.
    const place = (list, gkey, spread, colIdx, label) => {
      const gs = [];
      for (const n of list) { const g = gkey(n); if (!gs.length || gs[gs.length - 1].key !== g) gs.push({ key: g, nodes: [] }); gs[gs.length - 1].nodes.push(n); }
      let total = 0;
      gs.forEach((g, i) => { total += (g.nodes.length - 1) * rowH + (i ? groupGap : 0); });
      const single = total <= targetH;
      const sc = single && spread && total > 0 && total < spread ? Math.min(spread / total, 6) : 1;
      let sub = 0, yl = 0;
      gs.forEach((g, i) => {
        const gh = (g.nodes.length - 1) * rowH * sc;
        if (i) { if (yl > 0 && yl + groupGap * sc + gh > targetH) { sub++; yl = 0; } else yl += groupGap * sc; }
        let y0 = yl, cnt = 0;
        const close = () => groups.push({ col: colIdx, sub, key: g.key, label: label(g.key, g.nodes), y0, y1: yl, n: cnt });
        g.nodes.forEach((n, j) => {
          if (j) { yl += rowH * sc; if (yl > targetH) { close(); sub++; yl = 0; y0 = 0; cnt = 0; } }
          pos.set(n.id, { col: colIdx, sub, y: yl, gy: sub * targetH + yl, n });
          cnt++;
        });
        close();
      });
      subsOf.set(colIdx, sub + 1);
      return single ? Math.max(total, spread || 0) : targetH;
    };

    const reqCol = byCol.get(1) || [];
    const gOrder = new Map();
    reqCol.forEach((n) => { if (!gOrder.has(n.group)) gOrder.set(n.group, gOrder.size); });
    reqCol.sort((a, b) => gOrder.get(a.group) - gOrder.get(b.group) || a.id.localeCompare(b.id));
    const Href = reqCol.length ? place(reqCol, (n) => n.group, 0, 1, (k) => k.replace(/\.md$/, '')) : 600;

    for (const c of cols) {
      if (c === 1) continue;
      const list = byCol.get(c);
      if (c === 0) {
        const per = subsOf.get(1) || 1;
        const want = new Map(list.map((n) => [n.id, (bary(n) ?? 0) / per]));
        list.sort((a, b) => want.get(a.id) - want.get(b.id));
        let last = -1e9;
        for (const n of list) { const y = Math.max(want.get(n.id), last + 46); pos.set(n.id, { col: 0, sub: 0, y, gy: y, n }); last = y; }
        subsOf.set(0, 1);
        continue;
      }
      if (c === 2) {
        list.sort((a, b) => (pos.get(a.req)?.gy ?? 0) - (pos.get(b.req)?.gy ?? 0) || a.id.localeCompare(b.id));
        place(list, () => '', Href, 2, () => 'AC');
        continue;
      }
      if (c === 4) {
        const comps = new Map();
        for (const n of list) { if (!comps.has(n.comp)) comps.set(n.comp, []); comps.get(n.comp).push(n); }
        const rank = (arr) => { let s = 0, k = 0; for (const n of arr) { const b = bary(n); if (b != null) { s += b; k++; } } return k ? s / k : 1e9; };
        const flat = [];
        for (const [, arr] of [...comps.entries()].sort((a, b) => rank(a[1]) - rank(b[1]))) {
          arr.sort((a, b) => (a.module || '').localeCompare(b.module || '') || (bary(a) ?? 1e9) - (bary(b) ?? 1e9) || a.label.localeCompare(b.label));
          flat.push(...arr);
        }
        place(flat, (n) => n.comp, Href, 4, (k) => k);
        continue;
      }
      const typeRank = { entity: 0, part: 1, api: 2, table: 3, param: 4, question: 5, case: 0 };
      list.sort((a, b) => typeRank[a.type] - typeRank[b.type] || (bary(a) ?? 1e9) - (bary(b) ?? 1e9) || a.label.localeCompare(b.label));
      place(list, (n) => n.type, Href, c, (k) => t('type.' + k));
    }

    const start = new Map();
    let x = 0;
    for (const c of cols) { start.set(c, x); x += (subsOf.get(c) || 1) * subW + layerGap; }
    for (const p of pos.values()) p.x = start.get(p.col) + p.sub * subW;
    for (const g of groups) g.x = start.get(g.col) + g.sub * subW;

    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for (const p of pos.values()) { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + 280); y1 = Math.max(y1, p.y); }
    if (!pos.size) { x0 = y0 = 0; x1 = y1 = 100; }
    bounds = { x0: x0 - 60, y0: y0 - 60, x1: x1 + 40, y1: y1 + 60 };
    order = [...pos.values()];
  }

  // ---------- camera
  const ease = (p) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);
  function fly(to, ms = 1100) {
    if (!isFinite(to.x + to.y + to.k)) return;
    const from = { ...cam };
    const dist = Math.hypot((to.x - from.x) * from.k, (to.y - from.y) * from.k);
    const dip = Math.min(0.7, dist / 3000);
    anim = { from, to, t0: performance.now(), ms, dip };
    schedule();
  }
  function stepAnim(now) {
    if (!anim) return;
    const p = Math.min(1, (now - anim.t0) / anim.ms), e = ease(p);
    const lk = Math.log(anim.from.k) + (Math.log(anim.to.k) - Math.log(anim.from.k)) * e - anim.dip * Math.sin(Math.PI * p);
    cam.k = Math.exp(lk);
    cam.x = anim.from.x + (anim.to.x - anim.from.x) * e;
    cam.y = anim.from.y + (anim.to.y - anim.from.y) * e;
    if (p >= 1) { cam = { ...anim.to }; anim = null; }
    dirty = true;
  }
  function camFor(ids, pad = 120) {
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9, c = 0;
    for (const id of ids) { const p = pos.get(id); if (!p) continue; c++; x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x + 240); y1 = Math.max(y1, p.y); }
    if (!c) return null;
    const bw = x1 - x0 + pad * 2, bh = y1 - y0 + pad * 2;
    const dw = store.selected ? Math.min(440, W * 0.4) : 0;
    const k = Math.min(2.2, Math.max(0.05, Math.min((W - dw) / bw, (H - TOP) / bh)));
    return { x: (x0 + x1) / 2 + dw / 2 / k, y: (y0 + y1) / 2 - TOP / 2 / k, k };
  }
  function camFit() {
    const bw = bounds.x1 - bounds.x0, bh = bounds.y1 - bounds.y0;
    const k = Math.min(W / bw, (H - TOP) / bh) * 0.94;
    return { x: (bounds.x0 + bounds.x1) / 2, y: (bounds.y0 + bounds.y1) / 2 - TOP / 2 / k, k };
  }
  const toWorld = (sx, sy) => ({ x: (sx - W / 2) / cam.k + cam.x, y: (sy - H / 2) / cam.k + cam.y });

  function flyToActive() {
    const set = store.activeSet();
    if (!set) return;
    const c = camFor(set, 140);
    if (c) fly(c);
  }

  // ---------- drawing
  function nodeColor(n) {
    if (n.type === 'req') {
      if (prefs.color === 'status') return STATUS_COLOR[n.statusKind] || STATUS_COLOR.unknown;
      if (prefs.color === 'impl') return IMPL_COLOR[n.impl];
    }
    if (n.type === 'ac' && prefs.color === 'status') return STATUS_COLOR.approved;
    return colorOf(n);
  }

  function draw(now) {
    dirty = false;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.translate(W / 2, H / 2); ctx.scale(cam.k, cam.k); ctx.translate(-cam.x, -cam.y);
    const k = cam.k;
    const hov = store.hover && pos.has(store.hover) ? new Set([...store.related(store.hover, 1)]) : null;
    const set = hov || store.activeSet();
    const focusing = !!set;
    const vx0 = cam.x - W / 2 / k - 300, vx1 = cam.x + W / 2 / k + 300, vy0 = cam.y - H / 2 / k - 20, vy1 = cam.y + H / 2 / k + 20;

    // group bands
    for (const g of groups) {
      if (g.y1 + 20 < vy0 || g.y0 - 20 > vy1) continue;
      if (k < 0.5 && g.n < 3 && groups.length > 14) continue;
      ctx.fillStyle = 'rgba(120,150,255,0.045)';
      round(ctx, g.x - 14, g.y0 - 16, 330, g.y1 - g.y0 + 32, 12); ctx.fill();
      const gl = g.label + (k < 0.5 ? ` (${g.n})` : '');
      ctx.font = '600 1px "Segoe UI","Yu Gothic UI",sans-serif';
      const fs = Math.max(8, Math.min(Math.min(80, Math.max(11, 15 / k)), (subW - 40) / Math.max(1, ctx.measureText(gl).width)));
      ctx.font = `600 ${fs}px "Segoe UI","Yu Gothic UI",sans-serif`;
      ctx.fillStyle = k < 0.5 ? 'rgba(200,215,255,0.8)' : 'rgba(160,180,230,0.55)';
      ctx.textBaseline = 'alphabetic';
      ctx.fillText(gl, g.x - 6, g.y0 - 20 + (k < 0.5 ? -2 : 0));
    }

    // edges
    ctx.lineCap = 'round';
    const act = (id) => !focusing || set.has(id);
    const lw = 1 / k;
    for (let pass = 0; pass < 2; pass++) {
      for (const e of store.edges) {
        if (e.rel === 'member') continue;
        const a = pos.get(e.s), b = pos.get(e.t);
        if (!a || !b) continue;
        const hi = focusing && set.has(e.s) && set.has(e.t);
        if (e.rel === 'ref' && !hi) continue;
        if ((pass === 1) !== hi) continue;
        if ((a.x < vx0 && b.x < vx0) || (a.x > vx1 && b.x > vx1) || (a.y < vy0 && b.y < vy0) || (a.y > vy1 && b.y > vy1)) continue;
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        if (a.x === b.x) ctx.bezierCurveTo(a.x + 120, a.y, b.x + 120, b.y, b.x, b.y);
        else { const m = (a.x + b.x) / 2; ctx.bezierCurveTo(m, a.y, m, b.y, b.x, b.y); }
        if (hi) {
          const base = nodeColor(a.n);
          ctx.strokeStyle = base; ctx.globalAlpha = 0.85; ctx.lineWidth = 1.8 / k;
        } else { ctx.strokeStyle = focusing ? '#6f86c8' : '#7f9bff'; ctx.globalAlpha = focusing ? 0.035 : Math.min(0.18, 0.05 + 0.05 * k); ctx.lineWidth = lw; }
        ctx.stroke();
      }
    }
    ctx.globalAlpha = 1;

    // nodes
    const labelOn = k >= 0.85;
    for (const p of order) {
      const n = p.n;
      if (p.x < vx0 || p.x > vx1 || p.y < vy0 || p.y > vy1) continue;
      const on = act(n.id);
      const r = (n.type === 'goal' ? 9 : n.type === 'req' ? 5.5 : 4.5) * Math.max(1, 0.9 / Math.sqrt(k) * 0.9);
      ctx.globalAlpha = on ? 1 : 0.14;
      const col = nodeColor(n);
      if (on && focusing) { ctx.shadowColor = col; ctx.shadowBlur = 12; }
      ctx.fillStyle = col;
      ctx.beginPath();
      if (n.type === 'file' || n.type === 'part') round(ctx, p.x - r, p.y - r, r * 2, r * 2, r * 0.4);
      else if (n.type === 'case' || n.type === 'ac') { ctx.moveTo(p.x, p.y - r * 1.2); ctx.lineTo(p.x + r * 1.2, p.y); ctx.lineTo(p.x, p.y + r * 1.2); ctx.lineTo(p.x - r * 1.2, p.y); ctx.closePath(); }
      else ctx.arc(p.x, p.y, r, 0, 7);
      ctx.fill();
      ctx.shadowBlur = 0;
      if (n.id === store.selected || n.id === store.hover) {
        const pulse = 1 + 0.25 * Math.sin(now / 220);
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 2 / k; ctx.beginPath(); ctx.arc(p.x, p.y, r * 1.9 * pulse, 0, 7); ctx.stroke();
        dirty = true;
      }
      if ((labelOn && on) || (focusing && on && k > 0.22 && (set.size < 90 || n.id === store.selected))) {
        const fs = 12;
        ctx.font = `${fs}px "Segoe UI","Yu Gothic UI",sans-serif`;
        ctx.fillStyle = on && focusing ? '#fff' : 'rgba(215,226,250,0.9)';
        ctx.textBaseline = 'middle';
        const lab = n.type === 'file' ? n.label : (n.type === 'req' || n.type === 'ac' || n.type === 'goal' || n.type === 'case') ? n.label + (labelOn || focusing ? '  ' + (n.title || '').slice(0, 28) : '') : n.label;
        ctx.fillText(lab.slice(0, 44), p.x + r + 6, p.y);
      }
    }
    ctx.globalAlpha = 1;
    ctx.restore();
    drawMini(set);
    if (cam.k < 0.07) hint.textContent = '';
  }

  function round(c, x, y, w, h, r) {
    c.beginPath(); c.moveTo(x + r, y); c.arcTo(x + w, y, x + w, y + h, r); c.arcTo(x + w, y + h, x, y + h, r); c.arcTo(x, y + h, x, y, r); c.arcTo(x, y, x + w, y, r); c.closePath();
  }

  function drawMini(set) {
    const mw = mini.width, mh = mini.height;
    mctx.clearRect(0, 0, mw, mh);
    const bw = bounds.x1 - bounds.x0, bh = bounds.y1 - bounds.y0;
    const s = Math.min(mw / bw, mh / bh) * 0.92;
    const ox = (mw - bw * s) / 2 - bounds.x0 * s, oy = (mh - bh * s) / 2 - bounds.y0 * s;
    for (const p of order) {
      const on = !set || set.has(p.n.id);
      mctx.fillStyle = on ? nodeColor(p.n) : 'rgba(150,170,220,.25)';
      mctx.globalAlpha = on ? 1 : 0.5;
      mctx.fillRect(p.x * s + ox, p.y * s + oy, on && set ? 5 : 2.5, on && set ? 5 : 2.5);
    }
    mctx.globalAlpha = 1;
    mctx.strokeStyle = '#39d0ff'; mctx.lineWidth = 2;
    const vw = W / cam.k, vh = H / cam.k;
    mctx.strokeRect((cam.x - vw / 2) * s + ox, (cam.y - vh / 2) * s + oy, vw * s, vh * s);
    mini._s = { s, ox, oy };
  }

  function schedule() { if (!raf && !dead) raf = requestAnimationFrame(frame); }
  function frame(now) {
    raf = 0;
    if (dead) return;
    stepAnim(now);
    if (dirty || anim) draw(now);
    if (dirty || anim) schedule();
  }
  const redraw = () => { dirty = true; schedule(); };

  // ---------- interaction
  function pick(sx, sy) {
    const w = toWorld(sx, sy);
    let best = null, bd = Infinity;
    const tol = Math.max(7, 10 / cam.k);
    for (const p of order) {
      const dx = p.x - w.x, dy = p.y - w.y;
      if (Math.abs(dx) > tol + 6 || Math.abs(dy) > tol) continue;
      const d = dx * dx + dy * dy;
      if (d < bd) { bd = d; best = p; }
    }
    return best;
  }
  canvas.addEventListener('pointerdown', (e) => { drag = { x: e.clientX, y: e.clientY, cx: cam.x, cy: cam.y }; moved = false; canvas.setPointerCapture(e.pointerId); stopTour(); anim = null; });
  canvas.addEventListener('pointermove', (e) => {
    const r = canvas.getBoundingClientRect();
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      cam.x = drag.cx - dx / cam.k; cam.y = drag.cy - dy / cam.k; redraw(); hideTip();
      return;
    }
    const p = pick(e.clientX - r.left, e.clientY - r.top);
    canvas.style.cursor = p ? 'pointer' : 'grab';
    store.setHover(p ? p.n.id : null);
    if (p) showTip(nodeTip(p.n), e.clientX, e.clientY); else hideTip();
  });
  canvas.addEventListener('pointerup', (e) => {
    const was = moved; drag = null;
    if (was) return;
    const r = canvas.getBoundingClientRect();
    const p = pick(e.clientX - r.left, e.clientY - r.top);
    if (p) store.select(p.n.id, { fly: true });
    else if (store.selected || store.focus) store.clear();
  });
  canvas.addEventListener('pointerleave', () => { store.setHover(null); hideTip(); });
  canvas.addEventListener('dblclick', () => { store.clear(); fly(camFit()); });
  canvas.addEventListener('wheel', (e) => {
    e.preventDefault(); stopTour(); anim = null;
    const r = canvas.getBoundingClientRect();
    const sx = e.clientX - r.left, sy = e.clientY - r.top;
    const before = toWorld(sx, sy);
    cam.k = Math.min(4, Math.max(0.03, cam.k * Math.exp(-e.deltaY * 0.0015)));
    cam.x = before.x - (sx - W / 2) / cam.k; cam.y = before.y - (sy - H / 2) / cam.k;
    redraw();
  }, { passive: false });
  mini.addEventListener('pointerdown', (e) => {
    const r = mini.getBoundingClientRect(), s = mini._s; if (!s) return;
    const mx = (e.clientX - r.left) * (mini.width / r.width), my = (e.clientY - r.top) * (mini.height / r.height);
    stopTour(); fly({ x: (mx - s.ox) / s.s, y: (my - s.oy) / s.s, k: Math.max(cam.k, 0.5) }, 800);
  });

  // ---------- tour
  function stopTour() { if (tour) { clearTimeout(tour.timer); tour = null; renderToolbar(); } }
  function startTour() {
    if (tour) return stopTour();
    const goals = [...store.nodes.values()].filter((n) => n.type === 'goal' && pos.has(n.id));
    const seq = goals.length ? goals.map((g) => g.id) : order.filter((p) => p.n.type === 'req').slice(0, 8).map((p) => p.n.id);
    let i = 0;
    tour = { timer: 0 };
    const next = () => {
      if (!tour) return;
      if (i >= seq.length) { store.clear(); fly(camFit(), 1600); tour.timer = setTimeout(stopTour, 2200); return; }
      store.select(seq[i++], { fly: true, tour: true });
      tour.timer = setTimeout(next, 3800);
    };
    store.clear(); fly(camFit(), 900);
    tour.timer = setTimeout(next, 1400);
    renderToolbar();
  }

  // ---------- chrome
  function renderToolbar() {
    toolbar.replaceChildren(
      el('div', { class: 'grp' },
        el('button', { onclick: () => { store.clear(); fly(camFit(), 1200); } }, '🛰 ' + t('map.bird')),
        el('button', { onclick: () => flyToActive() }, '🎯 ' + t('map.zoomsel')),
        el('button', { class: tour ? 'on' : '', onclick: startTour }, (tour ? '■ ' : '▶ ') + t('map.tour'))),
      el('details', { class: 'grp pop' }, el('summary', {}, '◧ ' + t('map.layers')), el('div', {}, LAYER_TYPES.map((ty) => el('label', { title: t('type.' + ty) },
        el('input', { type: 'checkbox', checked: prefs.layers.has(ty) || null, onchange: (e) => { e.target.checked ? prefs.layers.add(ty) : prefs.layers.delete(ty); relayout(true); } }),
        el('i', { class: 'dot', style: { background: TYPE_COLOR[ty] } }), t('type.' + ty))))),
      el('div', { class: 'grp' }, ['type', 'status', 'impl'].map((m) => el('button', { class: prefs.color === m ? 'on' : '', onclick: () => { prefs.color = m; renderToolbar(); redraw(); } }, t('map.color.' + m)))));
    hint.textContent = t('map.hint');
  }
  function renderStatus() {
    const set = store.activeSet();
    statusBox.hidden = !set;
    if (!set) return;
    const n = store.selected ? store.node(store.selected) : null;
    statusBox.replaceChildren(
      el('div', {}, n ? el('b', {}, n.label) : el('b', {}, store.focusLabel || t('focus.set')), ' · ', t('focus.count', { n: [...set].filter((id) => pos.has(id)).length })),
      el('div', { class: 'row', style: { marginTop: '6px' } }, el('button', { class: 'btn ghost', onclick: () => store.clear() }, t('focus.clear'))));
  }
  function relayout(keepCam) {
    layout();
    if (!keepCam) cam = camFit();
    renderToolbar(); renderStatus(); redraw();
  }
  function resize() {
    const r = host.getBoundingClientRect();
    dpr = Math.min(2, devicePixelRatio || 1);
    W = r.width; H = r.height;
    canvas.width = W * dpr; canvas.height = H * dpr;
    redraw();
  }
  const ro = new ResizeObserver(resize); ro.observe(host);
  resize();
  relayout(false);
  cam = camFit();

  const offs = [
    store.on('select', (o) => {
      const id = o.id;
      if (id && store.node(id) && !pos.has(id)) {
        const n = store.node(id);
        if (!prefs.layers.has(n.type) && LAYER_TYPES.includes(n.type)) { prefs.layers.add(n.type); relayout(true); }
      }
      renderStatus(); redraw();
      if (o.cleared) return;
      if (o.fly || o.focus) {
        const set = store.activeSet();
        const c = set && camFor(set, 160);
        if (c) fly(c, o.tour ? 1600 : 1100);
      }
    }),
    store.on('hover', redraw),
    store.on('model', () => relayout(false)),
    onLang(() => { renderToolbar(); renderStatus(); layout(); redraw(); }),
  ];
  if (store.activeSet()) setTimeout(() => { const c = camFor(store.activeSet(), 160); if (c) fly(c, 900); renderStatus(); }, 50);

  return { destroy() { dead = true; cancelAnimationFrame(raf); stopTour(); ro.disconnect(); offs.forEach((f) => f()); hideTip(); } };
}
