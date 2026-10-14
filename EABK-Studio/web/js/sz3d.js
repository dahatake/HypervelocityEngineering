// 3D renderer of the semantic zoom: an orthographic, rotatable and tiltable projection of the same layout (Canvas 2D, no WebGL
// needed, so it also works where WebGL is blocked).  Boxes are extruded by their number of columns; the level of detail follows
// the shared scale exactly as in 2D.  FR-1029 / NFR-PERF-004.
import { el } from './ui.js';
import { t } from './i18n.js';
import { L, kindLabel, keyMark } from './semzoom.js';

const COLORS = { 外部キー: '#ff8a5c', 参照: '#4f9dff', 使用: '#8aa1b5' };
const DASH = { 外部キー: [], 参照: [8, 5], 使用: [2, 4] };
const MARK = { 外部キー: '◆', 参照: '◇', 使用: '▫' };
const clampN = (n, a, b) => Math.min(b, Math.max(a, n));

export function create3d(ctx) {
  const { d, view, api } = ctx;
  const canvas = el('canvas', { class: 'sz-canvas', role: 'img', 'aria-label': t('sz.title') });
  const g = canvas.getContext('2d');
  let hits = [], drawn = 0, dpr = 1;
  const size = () => ctx.size();
  const ZMAX = 150;

  const trig = () => ({ c: Math.cos(view.yaw), s: Math.sin(view.yaw), sp: Math.sin(view.pitch), cp: Math.cos(view.pitch) });
  function fit() {
    const { W, H } = size(), w = d.world, { c, s, sp, cp } = trig();
    const ww = w.x1 - w.x0, wh = w.y1 - w.y0;
    const ex = Math.abs(c) * ww + Math.abs(s) * wh, ey = (Math.abs(s) * ww + Math.abs(c) * wh) * sp + ZMAX * cp;
    return Math.max(1e-4, 0.9 * Math.min((W || 1) / ex, (H || 1) / ey));
  }
  function proj(x, y, z = 0) {
    const { W, H } = size(), k = ctx.k(), { c, s, sp, cp } = trig();
    const dx = x - view.cx, dy = y - view.cy, rx = dx * c - dy * s, ry = dx * s + dy * c;
    return { x: W / 2 + k * rx, y: H / 2 + k * (ry * sp - z * cp), depth: ry };
  }
  function toWorld(px, py) {
    const { W, H } = size(), k = ctx.k(), { c, s, sp } = trig();
    const rx = (px - W / 2) / k, ry = (py - H / 2) / (k * sp);
    return { x: view.cx + rx * c + ry * s, y: view.cy - rx * s + ry * c };
  }
  const toScreen = (wx, wy) => proj(wx, wy, 0);

  function poly(pts, fill, stroke, lw = 1, dash = []) {
    g.beginPath(); pts.forEach((p, i) => (i ? g.lineTo(p.x, p.y) : g.moveTo(p.x, p.y))); g.closePath();
    if (fill) { g.fillStyle = fill; g.fill(); }
    if (stroke) { g.strokeStyle = stroke; g.lineWidth = lw; g.setLineDash(dash); g.stroke(); g.setLineDash([]); }
  }
  // extruded box; returns the projected top face
  function box(x, y, w, h, z, top, side, stroke, lw, dash) {
    const A = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
    const { c, s } = trig();
    const normals = [[0, -1], [1, 0], [0, 1], [-1, 0]];
    for (let i = 0; i < 4; i++) {
      const a = A[i], b = A[(i + 1) % 4], n = normals[i];
      if (n[0] * s + n[1] * c <= 0) continue;   // facing away from the viewer
      poly([proj(a[0], a[1], 0), proj(b[0], b[1], 0), proj(b[0], b[1], z), proj(a[0], a[1], z)], side, 'rgba(0,0,0,.35)', 1);
    }
    const tp = A.map((p) => proj(p[0], p[1], z));
    poly(tp, top, stroke, lw, dash);
    return tp;
  }
  const bbox = (pts) => ({ x0: Math.min(...pts.map((p) => p.x)), y0: Math.min(...pts.map((p) => p.y)), x1: Math.max(...pts.map((p) => p.x)), y1: Math.max(...pts.map((p) => p.y)) });
  function text(s, x, y, px, color = '#e8eefc', align = 'center', weight = '600') {
    g.font = `${weight} ${px}px "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif`;
    g.fillStyle = color; g.textAlign = align; g.textBaseline = 'middle';
    g.fillText(s, x, y);
  }
  function label(s, x, y, px, color = '#e8eefc') {
    g.font = `600 ${px}px sans-serif`;
    const w = g.measureText(s).width + 8;
    g.fillStyle = 'rgba(10,15,32,.86)'; g.fillRect(x - w / 2, y - px * 0.8, w, px * 1.6);
    text(s, x, y, px, color);
  }

  function draw() {
    const { W, H } = size(), k = ctx.k(), level = ctx.level();
    if (canvas.width !== Math.round(W * dpr) || canvas.height !== Math.round(H * dpr) || dpr !== (window.devicePixelRatio || 1)) {
      dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    }
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    hits = []; drawn = 0;
    const onScreen = (b) => b.x1 >= -20 && b.x0 <= W + 20 && b.y1 >= -20 && b.y0 <= H + 20;
    const host = canvas.closest('[aria-label]');
    if (host) canvas.setAttribute('aria-label', host.getAttribute('aria-label'));
    const items = [];
    if (level === 'overview') {
      for (const c of d.clusters) {
        const r = d.rects.get(c.id);
        items.push({ depth: proj(r.x + r.w / 2, r.y + r.h / 2).depth, fn: () => drawCluster(c, r, onScreen) });
      }
    } else {
      for (const c of d.clusters) {
        const r = d.rects.get(c.id);
        items.push({ depth: proj(r.x + r.w / 2, r.y + r.h / 2).depth - 1e9, fn: () => plate(r) });
      }
      for (const n of d.names) {
        const p = d.pos.get(n);
        items.push({ depth: proj(p.x + p.w / 2, p.y + (level === 'detail' ? p.detH : p.midH) / 2).depth, fn: () => drawEntity(n, level, k, onScreen) });
      }
    }
    items.sort((a, b) => a.depth - b.depth);
    const post = [];
    for (const it of items) { const r = it.fn(); if (r) post.push(r); }
    if (level !== 'overview') {
      for (const e of d.edges) if (!e.usage && e.from !== e.to) drawEdge(e, level, onScreen);
      for (const f of post) f();   // billboards (column lists) stand in front of the lines
    }
  }

  function plate(r) {
    const tp = [proj(r.x, r.y), proj(r.x + r.w, r.y), proj(r.x + r.w, r.y + r.h), proj(r.x, r.y + r.h)];
    const { W, H } = size(), b = bbox(tp);
    if (b.x1 < 0 || b.x0 > W || b.y1 < 0 || b.y0 > H) return null;
    poly(tp, 'rgba(120,150,255,.06)', 'rgba(140,170,255,.28)', 1);
    return null;
  }

  function drawCluster(c, r, onScreen) {
    const sel = view.selected && d.clusterOf.get(view.selected) === c;
    const z = 25 + Math.min(120, c.count * 9), pad = 6;
    const corners = [proj(r.x + pad, r.y + pad, z), proj(r.x + r.w - pad, r.y + pad, z), proj(r.x + r.w - pad, r.y + r.h - pad, z), proj(r.x + pad, r.y + r.h - pad, z)];
    if (!onScreen(bbox(corners))) return null;
    const top = box(r.x + pad, r.y + pad, r.w - 2 * pad, r.h - 2 * pad, z, sel ? 'rgba(57,208,255,.34)' : 'rgba(79,157,255,.22)', 'rgba(40,60,120,.55)',
      sel ? '#39d0ff' : 'rgba(160,190,255,.6)', sel ? 3 : 1.5, sel ? [] : [6, 3]);
    const b = bbox(top), cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2;
    hits.push({ type: 'cluster', id: c.id, ...b });
    drawn += c.count;
    const px = clampN((b.x1 - b.x0) / 9, 11, 20);
    text(`${sel ? '◉ ' : ''}${c.id} · ${t('sz.entities', { n: c.count })}`, cx, cy - px * 0.9, px);
    const lines = Math.max(0, Math.min(6, Math.floor((b.y1 - b.y0) / (px * 1.4)) - 2));
    c.entities.slice(0, lines).forEach((n, i) => text(`▪ ${n}`, cx, cy + px * 0.5 + i * px * 1.25, px * 0.8, '#c8d4f0', 'center', '400'));
    return null;
  }

  function drawEntity(n, level, k, onScreen) {
    const p = d.pos.get(n), e = d.byName.get(n);
    const selected = view.selected === n, related = !!view.selected && d.nbr.get(view.selected).has(n);
    const dim = (!!view.selected && !selected && !related) || !api.matches(n);
    const nc = e.columns.length;
    const h = level === 'detail' ? p.detH : p.midH;
    const z = level === 'detail' ? 8 : 18 + Math.min(70, nc * 5);
    const quick = bbox([proj(p.x, p.y, z), proj(p.x + p.w, p.y, z), proj(p.x + p.w, p.y + h, z), proj(p.x, p.y + h, 0)]);
    if (level === 'mid' && !onScreen(quick)) return null;
    if (level === 'detail' && !onScreen({ x0: quick.x0 - p.w * k, x1: quick.x1 + p.w * k, y0: quick.y0 - h * k - 20, y1: quick.y1 })) return null;
    const top = box(p.x, p.y, p.w, h, z, dim ? 'rgba(40,52,86,.55)' : selected ? '#24507a' : '#1f3358', dim ? 'rgba(20,28,52,.55)' : '#16233f',
      selected ? '#39d0ff' : related ? '#ffb020' : 'rgba(160,190,255,.7)', selected ? 3 : related ? 2.5 : 1.2, related && !selected ? [5, 3] : []);
    const b = bbox(top);
    if (level === 'mid') {
      drawn++;
      hits.push({ type: 'entity', name: n, ...b });
      const w = b.x1 - b.x0, px = clampN(w / 11, 9, 17);
      const cx = (b.x0 + b.x1) / 2, cy = (b.y0 + b.y1) / 2, mark = selected || related;
      text(n, cx, cy - (mark ? px * 0.6 : 0), px, dim ? '#7f8db0' : '#ffffff');
      if (mark) text(selected ? `◉ ${t('sz.badge.selected')}` : `↔ ${t('sz.badge.related')}`, cx, cy + px * 0.8, px * 0.8, '#ffd166');
      if (!nc && w > 60) text(`⚠ ${t('sz.nocols')}`, cx, cy + px * (mark ? 2 : 1), px * 0.75, '#9aa9c9', 'center', '400');
      return null;
    }
    // detail: a billboard that stands on the box and lists the columns
    const bw = p.w * k, bh = h * k;
    const anchor = proj(p.x + p.w / 2, p.y + h / 2, z);
    const bx = anchor.x - bw / 2, by = anchor.y - bh - 6;
    drawn++;
    hits.push({ type: 'entity', name: n, x0: bx, y0: by, x1: bx + bw, y1: by + L.HEAD_H * k });
    return () => billboard(n, e, bx, by, bw, bh, k, selected, related, dim);
  }

  function billboard(n, e, bx, by, bw, bh, k, selected, related, dim) {
    g.save();
    g.globalAlpha = dim ? 0.5 : 1;
    g.fillStyle = 'rgba(14,22,44,.95)';
    g.strokeStyle = selected ? '#39d0ff' : related ? '#ffb020' : 'rgba(160,190,255,.7)';
    g.lineWidth = selected ? 3 : 1.5; g.setLineDash(related && !selected ? [5, 3] : []);
    g.beginPath(); g.rect(bx, by, bw, bh); g.fill(); g.stroke(); g.setLineDash([]);
    g.beginPath(); g.rect(bx, by, bw, bh); g.clip();
    const fs = clampN(14 * k, 8, 26);
    text(n, bx + 10 * k, by + L.HEAD_H * k / 2, fs, '#ffffff', 'left', '700');
    const badge = selected ? `◉ ${t('sz.badge.selected')}` : related ? `↔ ${t('sz.badge.related')}` : '';
    if (badge) text(badge, bx + bw - 8 * k, by + L.HEAD_H * k / 2, fs * 0.8, '#ffd166', 'right');
    g.strokeStyle = 'rgba(140,170,255,.3)'; g.lineWidth = 1; g.beginPath(); g.moveTo(bx, by + L.HEAD_H * k); g.lineTo(bx + bw, by + L.HEAD_H * k); g.stroke();
    const rowPx = L.ROW_H * k, f2 = clampN(12 * k, 7, 22);
    if (!e.columns.length) text(`⚠ ${t('sz.nocols')}`, bx + 10 * k, by + L.HEAD_H * k + rowPx / 2, f2, '#9aa9c9', 'left', '400');
    e.columns.slice(0, L.MAX_ROWS).forEach((c, i) => {
      const y0 = by + L.HEAD_H * k + i * rowPx;
      if (selected && view.column === c.name) { g.fillStyle = 'rgba(57,208,255,.25)'; g.fillRect(bx + 2, y0, bw - 4, rowPx); }
      const mk = keyMark(c.key);
      const line = `${mk ? mk + ' ' : '   '}${c.name}${c.type ? ': ' + c.type : ''}${c.ref ? ' → ' + c.ref : ''}${c.origin === '補完' ? ' ＋' : ''}${c.mismatch && c.mismatch.length ? ' ≠' : ''}`;
      text(line, bx + 8 * k, y0 + rowPx / 2, f2, c.ref ? '#ffd166' : '#dfe7fb', 'left', mk ? '700' : '400');
      hits.push({ type: 'column', entity: n, name: c.name, x0: bx, y0, x1: bx + bw, y1: y0 + rowPx });
    });
    if (e.columns.length > L.MAX_ROWS) text(`… ${t('sz.more', { n: e.columns.length - L.MAX_ROWS })}`, bx + 8 * k, by + L.HEAD_H * k + L.MAX_ROWS * rowPx + rowPx / 2, f2, '#9aa9c9', 'left', '400');
    g.restore();
  }

  function drawEdge(e, level, onScreen) {
    const a = d.pos.get(e.from), b = d.pos.get(e.to), lift = level === 'mid' ? 73 : 8;
    const pa = proj(a.x + a.w / 2, a.y + (level === 'detail' ? a.detH : a.midH) / 2, lift);
    const pb = proj(b.x + b.w / 2, b.y + (level === 'detail' ? b.detH : b.midH) / 2, lift);
    if (!onScreen(bbox([pa, pb]))) return;
    const hl = view.selected && (e.from === view.selected || e.to === view.selected);
    g.save(); g.globalAlpha = view.selected && !hl ? 0.25 : 1;
    g.strokeStyle = COLORS[e.kind]; g.lineWidth = hl ? 3.5 : e.kind === '外部キー' ? 2.5 : 1.6; g.setLineDash(DASH[e.kind]);
    g.beginPath(); g.moveTo(pa.x, pa.y); g.lineTo(pb.x, pb.y); g.stroke(); g.setLineDash([]);
    const ang = Math.atan2(pb.y - pa.y, pb.x - pa.x);
    g.fillStyle = COLORS[e.kind]; g.beginPath(); g.moveTo(pb.x, pb.y);
    g.lineTo(pb.x - 11 * Math.cos(ang - 0.4), pb.y - 11 * Math.sin(ang - 0.4)); g.lineTo(pb.x - 11 * Math.cos(ang + 0.4), pb.y - 11 * Math.sin(ang + 0.4)); g.fill();
    label(`${MARK[e.kind]} ${e.from} → ${e.to} · ${kindLabel(e.kind)}`, (pa.x + pb.x) / 2, (pa.y + pb.y) / 2, 11, COLORS[e.kind]);
    g.restore();
  }

  function pick(px, py) {
    for (let i = hits.length - 1; i >= 0; i--) { const h = hits[i]; if (px >= h.x0 && px <= h.x1 && py >= h.y0 && py <= h.y1) return h; }
    return null;
  }

  return { kind: '3d', el: canvas, draw, fit, toWorld, toScreen, pick, drawnEntities: () => drawn };
}
