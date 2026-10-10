// Source mapping: which requirements, parts and tests each source path in the catalog belongs to (names only; no code is read).
import { t, onLang } from './i18n.js';
import { store, norm } from './store.js';
import { el, svgEl, colorOf, nodeChip, showTip, hideTip, vscodeUrl } from './ui.js';

const ui = { q: '', tests: true };

function split(items, rect, out) {
  if (items.length === 1) { out.set(items[0].key, rect); return; }
  const total = items.reduce((s, i) => s + i.w, 0);
  let acc = 0, k = 0;
  for (; k < items.length - 1; k++) { acc += items[k].w; if (acc >= total / 2) { k++; break; } }
  k = Math.max(1, Math.min(items.length - 1, k));
  const a = items.slice(0, k), b = items.slice(k);
  const wa = a.reduce((s, i) => s + i.w, 0) / total;
  if (rect.w >= rect.h) { split(a, { x: rect.x, y: rect.y, w: rect.w * wa, h: rect.h }, out); split(b, { x: rect.x + rect.w * wa, y: rect.y, w: rect.w * (1 - wa), h: rect.h }, out); }
  else { split(a, { x: rect.x, y: rect.y, w: rect.w, h: rect.h * wa }, out); split(b, { x: rect.x, y: rect.y + rect.h * wa, w: rect.w, h: rect.h * (1 - wa) }, out); }
}

export function mount(host) {
  const page = el('div', { class: 'page' });
  host.append(page);

  function treemap(files) {
    const Wt = 1100, Ht = 560;
    const comps = new Map();
    for (const f of files) { if (!comps.has(f.comp)) comps.set(f.comp, []); comps.get(f.comp).push(f); }
    const citems = [...comps.entries()].map(([k, fs]) => ({ key: k, w: fs.reduce((s, f) => s + 1 + store.neighbors(f.id, ['req']).length, 0), fs })).sort((a, b) => b.w - a.w);
    const out = new Map();
    if (citems.length) split(citems, { x: 0, y: 0, w: Wt, h: Ht }, out);
    const svg = svgEl('svg', { viewBox: `0 0 ${Wt} ${Ht}`, width: '100%', style: 'max-width:1300px;display:block', preserveAspectRatio: 'xMidYMid meet' });
    const set = store.hover ? store.related(store.hover, 1) : store.activeSet();
    for (const c of citems) {
      const r = out.get(c.key), pad = 3;
      svg.append(svgEl('rect', { x: r.x + pad, y: r.y + pad, width: Math.max(0, r.w - pad * 2), height: Math.max(0, r.h - pad * 2), rx: 10, fill: 'rgba(120,150,255,.06)', stroke: 'rgba(140,170,255,.35)' }));
      if (r.w > 90 && r.h > 40) svg.append(svgEl('text', { x: r.x + 12, y: r.y + 22, 'font-size': 13, 'font-weight': 700, fill: '#cfe0ff' }, c.key.length > r.w / 8 ? c.key.split('/').pop() : c.key));
      const inner = { x: r.x + 8, y: r.y + 30, w: r.w - 16, h: r.h - 38 };
      if (inner.w < 8 || inner.h < 8) continue;
      const fout = new Map();
      split(c.fs.map((f) => ({ key: f.id, w: 1 + store.neighbors(f.id, ['req']).length })).sort((a, b) => b.w - a.w), inner, fout);
      for (const f of c.fs) {
        const fr = fout.get(f.id); if (!fr) continue;
        const nreq = store.neighbors(f.id, ['req']).length, on = !set || set.has(f.id);
        const col = colorOf(f);
        const g = svgEl('g', { class: 'node-g', style: `opacity:${on ? 1 : 0.16}` },
          svgEl('rect', { x: fr.x + 1, y: fr.y + 1, width: Math.max(0, fr.w - 2), height: Math.max(0, fr.h - 2), rx: 4, fill: col, 'fill-opacity': 0.18 + Math.min(0.6, nreq / 14), stroke: f.id === store.selected ? '#fff' : col, 'stroke-width': f.id === store.selected ? 2.5 : 0.8 }));
        if (fr.w > 56 && fr.h > 18) g.append(svgEl('text', { x: fr.x + 5, y: fr.y + 14, 'font-size': 10.5, fill: '#fff' }, f.label.length * 6 > fr.w ? f.label.slice(0, Math.floor(fr.w / 6)) + '…' : f.label));
        g.addEventListener('click', () => store.select(f.id, { fly: true }));
        g.addEventListener('mouseenter', (e) => { store.setHover(f.id); showTip(`<b style="color:${col}">${f.label}</b><div class="mini">${f.path}</div><div>${nreq} ${t('type.req')}</div>`, e.clientX, e.clientY); });
        g.addEventListener('mousemove', (e) => showTip(`<b style="color:${col}">${f.label}</b><div class="mini">${f.path}</div><div>${nreq} ${t('type.req')}</div>`, e.clientX, e.clientY));
        g.addEventListener('mouseleave', () => { store.setHover(null); hideTip(); });
        svg.append(g);
      }
    }
    return svg;
  }

  function fileList(files) {
    const q = norm(ui.q);
    const list = files.filter((f) => !q || norm(f.path).includes(q));
    const byComp = new Map();
    for (const f of list) { if (!byComp.has(f.comp)) byComp.set(f.comp, []); byComp.get(f.comp).push(f); }
    const set = store.activeSet();
    return el('div', {}, [...byComp.entries()].sort().map(([c, fs]) => el('details', { open: set ? fs.some((f) => set.has(f.id)) || null : null, style: { marginBottom: '8px' } },
      el('summary', { style: { cursor: 'pointer', padding: '6px 0' } }, el('b', {}, c), el('span', { class: 'mini' }, ` · ${fs.length}`)),
      fs.sort((a, b) => a.path.localeCompare(b.path)).map((f) => {
        const reqs = store.neighbors(f.id, ['req']).length, parts = store.neighbors(f.id, ['part', 'api', 'table']);
        return el('div', { class: 'res' + (f.id === store.selected ? ' on' : ''), style: set && !set.has(f.id) ? { opacity: 0.35 } : {}, onclick: () => store.select(f.id, { fly: true }) },
          el('i', { class: 'dot', style: { background: colorOf(f) } }), el('span', { class: 't mono' }, f.path.replace(c + '/', ''), el('small', {}, `${reqs} ${t('type.req')}${parts.length ? ' · ' + parts.map((p) => store.node(p.id).label).join(', ') : ''}`)),
          el('a', { class: 'mini', href: vscodeUrl(f.path), title: 'VS Code', onclick: (e) => e.stopPropagation() }, '↗'));
      }))));
  }

  function render() {
    const files = [...store.nodes.values()].filter((n) => n.type === 'file' && (ui.tests || n.role !== 'test'));
    page.replaceChildren(el('h1', {}, '🗂 ' + t('nav.source')), el('p', { class: 'sub' }, t('src.sub')),
      el('div', { class: 'tbar' }, el('input', { type: 'search', placeholder: t('src.filter'), value: ui.q, oninput: (e) => { ui.q = e.target.value; refresh(); } }),
        el('label', { class: 'row mini', style: { cursor: 'pointer' } }, el('input', { type: 'checkbox', checked: ui.tests || null, onchange: (e) => { ui.tests = e.target.checked; render(); } }), t('src.tests')),
        el('span', { class: 'mini' }, t('src.legend'))),
      files.length ? el('div', { class: 'grid', style: { gridTemplateColumns: 'minmax(0,1.6fr) minmax(300px,1fr)', alignItems: 'start' } },
        el('div', { class: 'card', id: 'tm' }, treemap(files)), el('div', { class: 'card', id: 'fl', style: { maxHeight: '70vh', overflow: 'auto' } }, fileList(files))) : el('div', { class: 'empty' }, t('src.none')));
  }
  function refresh() {
    const files = [...store.nodes.values()].filter((n) => n.type === 'file' && (ui.tests || n.role !== 'test'));
    const tm = page.querySelector('#tm'), fl = page.querySelector('#fl');
    if (tm) tm.replaceChildren(treemap(files));
    if (fl) fl.replaceChildren(fileList(files));
  }
  render();
  const offs = [store.on('model', render), store.on('select', refresh), onLang(render)];
  return { destroy() { offs.forEach((f) => f()); hideTip(); } };
}
