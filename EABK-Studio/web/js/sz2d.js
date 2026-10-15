// 2D renderer of the semantic zoom (SVG, only the part inside the viewport is drawn).  FR-1027 / FR-1028 / NFR-PERF-004.
import { svgEl } from './ui.js';
import { t } from './i18n.js';
import { L, KINDS, kindLabel, keyMark, parseRef } from './semzoom.js';

const KCLASS = { 外部キー: 'k-fk', 参照: 'k-ref', 使用: 'k-use' };
const MARK = { 外部キー: '◆', 参照: '◇', 使用: '▫' };   // a mark and a word in addition to line style and colour (NFR-UX-010 AC-186)
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clampN = (n, a, b) => Math.min(b, Math.max(a, n));

export function create2d(ctx) {
  const { d, view, api } = ctx;
  const svg = svgEl('svg', { class: 'sz-svg', 'aria-hidden': 'true', focusable: 'false' });
  let drawn = 0;

  const size = () => ctx.size();
  const fit = () => { const { W, H } = size(), w = d.world; return Math.max(1e-4, 0.92 * Math.min((W || 1) / (w.x1 - w.x0), (H || 1) / (w.y1 - w.y0))); };
  const toWorld = (px, py) => { const { W, H } = size(), k = ctx.k(); return { x: (px - W / 2) / k + view.cx, y: (py - H / 2) / k + view.cy }; };
  const toScreen = (wx, wy) => { const { W, H } = size(), k = ctx.k(); return { x: (wx - view.cx) * k + W / 2, y: (wy - view.cy) * k + H / 2 }; };

  function rectOf(name, level) { const p = d.pos.get(name); return { x: p.x, y: p.y, w: p.w, h: level === 'detail' ? p.detH : p.midH }; }
  function toward(r, to) {
    const c = { x: r.x + r.w / 2, y: r.y + r.h / 2 }, dx = to.x - c.x, dy = to.y - c.y;
    const s = Math.min(dx ? (r.w / 2) / Math.abs(dx) : Infinity, dy ? (r.h / 2) / Math.abs(dy) : Infinity, 1);
    return { x: c.x + dx * s, y: c.y + dy * s };
  }

  function draw() {
    const { W, H } = size(), k = ctx.k(), level = ctx.level();
    svg.setAttribute('width', W); svg.setAttribute('height', H); svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
    const px = (n) => n / k;
    const pad = 40 / k;
    const v = { x0: view.cx - W / 2 / k - pad, x1: view.cx + W / 2 / k + pad, y0: view.cy - H / 2 / k - pad, y1: view.cy + H / 2 / k + pad };
    const small = d.names.length <= 80;   // small models are drawn completely; larger ones only inside the viewport (virtualisation)
    const hit = (x, y, w, h) => small || (x + w >= v.x0 && x <= v.x1 && y + h >= v.y0 && y <= v.y1);
    const root = svgEl('g', { transform: `translate(${W / 2} ${H / 2}) scale(${k}) translate(${-view.cx} ${-view.cy})` });
    const selCluster = view.selected ? d.clusterOf.get(view.selected) : null;
    drawn = 0;

    for (const c of d.clusters) {   // cluster frames (the "overview" content; a faint frame at the other levels)
      const r = d.rects.get(c.id);
      if (!hit(r.x, r.y, r.w, r.h)) continue;
      const sel = selCluster === c;
      const g = svgEl('g', { class: 'sz-cluster' + (sel ? ' sel' : '') + (level === 'overview' ? '' : ' faint'), 'data-cluster': c.id, 'data-count': String(c.count),
        role: 'button', tabindex: '-1', 'aria-label': t('sz.cluster', { id: c.id, n: c.count }) });
      g.append(svgEl('rect', { x: r.x, y: r.y, width: r.w, height: r.h, rx: px(10), class: 'sz-cl-box' }));
      const fs = level === 'overview' ? px(15) : clampN(px(13), 11, 26);
      const inner = svgEl('svg', { x: r.x, y: r.y, width: r.w, height: r.h, overflow: 'hidden' });
      inner.append(svgEl('text', { x: px(10), y: fs + px(5), 'font-size': fs, class: 'sz-cl-title' }, `${sel ? '◉ ' : ''}${c.id} · ${t('sz.entities', { n: c.count })}`));
      if (level === 'overview') {
        const rowsTxt = c.lines || c.entities.map((n) => `▪ ${n}`);
        const lines = Math.max(0, Math.min(10, Math.floor((r.h * k - 44) / 17)));
        rowsTxt.slice(0, lines).forEach((s, i) => inner.append(svgEl('text', { x: px(12), y: px(40 + 17 * i), 'font-size': px(13), class: 'sz-cl-name' + (c.entities[i] === view.selected && !c.lines ? ' sel' : '') }, s)));
        if (rowsTxt.length > lines && lines > 0) inner.append(svgEl('text', { x: px(12), y: px(40 + 17 * lines), 'font-size': px(12), class: 'sz-cl-name' }, `… +${rowsTxt.length - lines}`));
      }
      g.append(inner);
      root.append(g);
    }

    if (level !== 'overview') {
      const entLayer = svgEl('g', { class: 'sz-ents' });
      const edgeLayer = svgEl('g', { class: 'sz-edges', 'pointer-events': 'none' });
      const seen = new Set();
      for (const n of d.names) {
        const r = rectOf(n, level);
        if (!hit(r.x, r.y, r.w, r.h)) continue;
        seen.add(n); drawn++;
        entLayer.append(entity(n, r, level, k, px));
      }
      for (const e of d.edges) {
        if (e.usage || e.from === e.to) continue;
        if (!seen.has(e.from) && !seen.has(e.to)) {
          const a = rectOf(e.from, level), b = rectOf(e.to, level);
          if (!hit(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.abs(a.x - b.x) + L.BOX_W, Math.abs(a.y - b.y) + a.h)) continue;
        }
        edgeLayer.append(edge(e, level, px));
      }
      if (level === 'detail') for (const n of seen) columnEdges(n, edgeLayer, px);
      root.append(entLayer, edgeLayer);
    }
    svg.replaceChildren(root);
  }

  function entity(n, r, level, k, px) {
    const e = d.byName.get(n), selected = view.selected === n;
    const related = !!view.selected && d.nbr.get(view.selected).has(n);
    const dim = (!!view.selected && !selected && !related) || !api.matches(n);
    const nc = e.columns.length;
    const g = svgEl('g', { class: 'sz-ent' + (selected ? ' sel' : '') + (related ? ' rel' : '') + (dim ? ' dim' : ''), 'data-entity': n, 'data-level': level,
      'data-highlight': related ? 'true' : null, 'data-selected': selected ? 'true' : null, 'data-dim': dim ? 'true' : null,
      role: 'button', tabindex: '-1', 'aria-label': `${n}${nc ? ` — ${nc} ${t('sz.alt.cols')}` : ` — ${t('sz.nocols')}`}` });
    g.append(svgEl('rect', { x: r.x, y: r.y, width: r.w, height: r.h, rx: 6, class: 'sz-ent-box' }));
    const inner = svgEl('svg', { x: r.x, y: r.y, width: r.w, height: r.h, overflow: 'hidden', 'pointer-events': 'none' });
    const fs = clampN(px(14), 9, 16);
    inner.append(svgEl('text', { x: 10, y: (L.HEAD_H + fs * 0.7) / 2, 'font-size': fs, class: 'sz-ent-name' }, n));
    const badge = selected ? `◉ ${t('sz.badge.selected')}` : related ? `↔ ${t('sz.badge.related')}` : '';
    if (badge) inner.append(svgEl('text', { x: r.w - 8, y: (L.HEAD_H + fs * 0.7) / 2, 'font-size': fs * 0.8, 'text-anchor': 'end', class: 'sz-badge' }, badge));
    inner.append(svgEl('line', { x1: 0, y1: L.HEAD_H, x2: r.w, y2: L.HEAD_H, class: 'sz-sep' }));
    g.append(inner);

    if (level === 'mid') {
      const uses = d.uses.get(n);
      const shown = uses.slice(0, L.MAX_USES);
      const ug = svgEl('g', { 'pointer-events': 'none' });
      shown.forEach((u, i) => {
        const ge = svgEl('g', { class: 'sz-edge k-use sz-chip', 'data-edge': '', 'data-from': u.from, 'data-to': u.to, 'data-kind': '使用' });
        ge.append(svgEl('text', { x: r.x + 10, y: r.y + L.HEAD_H + L.USE_ROW * i + 12, 'font-size': 11.5 }, `${MARK['使用']} ${n} → ${u.to} · ${kindLabel('使用')}`));
        ug.append(ge);
      });
      if (uses.length > shown.length) ug.append(svgEl('text', { x: r.x + 10, y: r.y + L.HEAD_H + L.USE_ROW * shown.length + 12, 'font-size': 11.5 }, t('sz.moreuses', { n: uses.length - shown.length })));
      g.append(ug);
    } else {
      const ci = svgEl('svg', { x: r.x, y: r.y + L.HEAD_H, width: r.w, height: r.h - L.HEAD_H, overflow: 'hidden' });
      if (!nc) ci.append(svgEl('text', { x: 10, y: L.ROW_H - 4, 'font-size': 12, class: 'sz-nocols' }, `⚠ ${t('sz.nocols')}`));
      e.columns.slice(0, L.MAX_ROWS).forEach((c, i) => ci.append(column(n, c, i, r)));
      if (nc > L.MAX_ROWS) ci.append(svgEl('text', { x: 10, y: L.ROW_H * L.MAX_ROWS + L.ROW_H - 4, 'font-size': 12, class: 'sz-more' }, `… ${t('sz.more', { n: nc - L.MAX_ROWS })}`));
      g.append(ci);
    }
    return g;
  }

  function column(n, c, i, r) {
    const sel = view.selected === n && view.column === c.name;
    const mark = keyMark(c.key);
    const ref = parseRef(c.ref);
    const row = svgEl('g', { class: 'sz-col' + (sel ? ' sel' : ''), 'data-column': c.name, 'data-col-entity': n, 'data-name': c.name, 'data-key': c.key || '', 'data-ref': c.ref || '',
      role: 'button', tabindex: '-1', 'aria-label': `${c.name} ${c.type || ''} ${c.key || ''} ${c.ref || ''}`.trim() });
    row.append(svgEl('rect', { x: 2, y: i * L.ROW_H, width: r.w - 4, height: L.ROW_H, class: 'sz-col-bg' }));
    const tx = svgEl('text', { x: 8, y: i * L.ROW_H + L.ROW_H - 4, 'font-size': 12 });
    tx.append(svgEl('tspan', { class: 'sz-key' }, mark ? mark.padEnd(3, ' ') : '   '), svgEl('tspan', { class: 'sz-cname' }, `${c.name}`),
      svgEl('tspan', { class: 'sz-ctype', dx: 6 }, c.type ? `: ${c.type}` : ''));
    if (c.origin === '補完') tx.append(svgEl('tspan', { class: 'sz-ctype', dx: 4 }, '＋'));
    if (c.mismatch && c.mismatch.length) tx.append(svgEl('tspan', { class: 'sz-warn', dx: 4 }, '≠'));
    if (c.ref) tx.append(svgEl('tspan', { class: ref && d.byName.has(ref.entity) ? 'sz-ref' : 'sz-ctype', dx: 6, 'data-goto': ref && d.byName.has(ref.entity) ? c.ref : null }, `→ ${c.ref}`));
    row.append(tx);
    return row;
  }

  function edge(e, level, px) {
    const a = rectOf(e.from, level), b = rectOf(e.to, level);
    const ca = { x: a.x + a.w / 2, y: a.y + a.h / 2 }, cb = { x: b.x + b.w / 2, y: b.y + b.h / 2 };
    const pa = toward(a, cb), pb = toward(b, ca);
    const hl = view.selected && (e.from === view.selected || e.to === view.selected);
    const dim = view.selected && !hl;
    const g = svgEl('g', { class: `sz-edge ${KCLASS[e.kind] || ''}${hl ? ' hl' : ''}${dim ? ' dim' : ''}`, 'data-edge': '', 'data-from': e.from, 'data-to': e.to, 'data-kind': e.kind });
    g.append(svgEl('line', { x1: pa.x, y1: pa.y, x2: pb.x, y2: pb.y, class: 'sz-line' }));
    const ang = Math.atan2(pb.y - pa.y, pb.x - pa.x), s = clampN(px(9), 6, 22);
    g.append(svgEl('polygon', { points: `${pb.x},${pb.y} ${pb.x - s * Math.cos(ang - 0.4)},${pb.y - s * Math.sin(ang - 0.4)} ${pb.x - s * Math.cos(ang + 0.4)},${pb.y - s * Math.sin(ang + 0.4)}`, class: 'sz-arrow' }));
    const fs = clampN(px(11), 8, 13), text = `${MARK[e.kind] || ''} ${e.from} → ${e.to} · ${kindLabel(e.kind)}`;
    const mx = (pa.x + pb.x) / 2, my = (pa.y + pb.y) / 2, w = text.length * fs * 0.6 + 8;
    g.append(svgEl('rect', { x: mx - w / 2, y: my - fs, width: w, height: fs * 1.5, rx: 3, class: 'sz-lbl-bg' }), svgEl('text', { x: mx, y: my + fs * 0.1, 'font-size': fs, 'text-anchor': 'middle', class: 'sz-lbl' }, text));
    return g;
  }

  function columnEdges(n, layer, px) {
    const e = d.byName.get(n), p = d.pos.get(n);
    e.columns.forEach((c, i) => {
      const r = parseRef(c.ref);
      if (!r || !d.byName.has(r.entity) || i >= L.MAX_ROWS) return;
      const q = d.pos.get(r.entity), ti = d.cols.get(r.entity).get(r.column);
      const right = q.x + q.w / 2 >= p.x + p.w / 2 && r.entity !== n;
      const sx = right ? p.x + p.w : p.x, sy = p.y + L.HEAD_H + i * L.ROW_H + L.ROW_H / 2;
      const tx = r.entity === n ? p.x + p.w : right ? q.x : q.x + q.w;
      const ty = q.y + (ti != null && ti < L.MAX_ROWS ? L.HEAD_H + ti * L.ROW_H + L.ROW_H / 2 : L.HEAD_H / 2);
      const dir = right || r.entity === n ? 1 : -1;
      const g = svgEl('g', { class: 'sz-cedge', 'data-column-edge': '', 'data-from': `${n}.${c.name}`, 'data-to': c.ref });
      g.append(svgEl('path', { d: `M${sx},${sy} C${sx + dir * 70},${sy} ${tx - dir * 70},${ty} ${tx},${ty}`, class: 'sz-cpath' }), svgEl('circle', { cx: tx, cy: ty, r: px(3.5), class: 'sz-cdot' }));
      layer.append(g);
    });
  }

  // tooltip + click delegation
  svg.addEventListener('click', (ev) => {
    if (api.dragged()) return;
    const go = ev.target.closest('[data-goto]');
    if (go) { api.gotoRef(go.getAttribute('data-goto')); return; }
    const col = ev.target.closest('[data-column]');
    if (col) { api.selectColumn(col.getAttribute('data-col-entity'), col.getAttribute('data-name')); return; }
    const en = ev.target.closest('[data-entity]');
    if (en) { api.select(en.getAttribute('data-entity')); return; }
    const cl = ev.target.closest('[data-cluster]');
    if (cl) { api.zoomToCluster(cl.getAttribute('data-cluster')); return; }
    api.select(null);
  });
  svg.addEventListener('pointermove', (ev) => {
    const en = ev.target.closest && ev.target.closest('[data-entity]');
    if (!en) { api.hideTip(); return; }
    const e = d.byName.get(en.getAttribute('data-entity'));
    api.tip(`<b>${esc(e.name)}</b><div class="mini">${esc(e.description || '')}</div><div class="mini">${e.columns.length ? e.columns.length + ' ' + esc(t('sz.alt.cols')) : esc(t('sz.nocols'))}</div>`, ev.clientX, ev.clientY);
  });
  svg.addEventListener('pointerleave', () => api.hideTip());

  return { kind: '2d', el: svg, draw, fit, toWorld, toScreen, drawnEntities: () => drawn };
}
