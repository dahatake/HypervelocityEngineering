// Placement: where business-layer requirements, data (entities / tables) and APIs live in the application components.
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, colorOf, TYPE_COLOR, nodeChip } from './ui.js';

const ui = { rowMode: 'goal', tests: false, sel: null, tab: 'biz' };

export function mount(host) {
  const hk = new URLSearchParams(location.hash.split('?')[1] || '').get('tab');
  if (['biz', 'data', 'items'].includes(hk)) ui.tab = hk;
  const page = el('div', { class: 'page' });
  host.append(page);

  const implFiles = (id) => store.neighbors(id, ['file']).map((x) => store.node(x.id)).filter((f) => f && (ui.tests || f.role !== 'test'));
  function compsOf(reqId) {
    const m = new Map();
    for (const f of implFiles(reqId)) { if (!m.has(f.comp)) m.set(f.comp, []); m.get(f.comp).push(f); }
    return m;
  }

  function matrix(rows, cols, titleOf, rowNodeId) {
    // rows: [{key, label, reqs:[id], nodeId}], cols: component paths
    const cells = new Map();
    let max = 1;
    for (const r of rows) for (const c of cols) {
      const ids = r.reqs.filter((id) => compsOf(id).has(c));
      cells.set(r.key + '\u0001' + c, ids);
      max = Math.max(max, ids.length);
    }
    const table = el('table', { class: 't heat' });
    const names = cols.map((c) => c.split('/').pop());
    let pre = names[0] || '';
    for (const n of names) while (pre && !n.startsWith(pre)) pre = pre.slice(0, -1);
    pre = pre.includes('.') ? pre.slice(0, pre.lastIndexOf('.') + 1) : '';
    table.append(el('thead', {}, el('tr', {}, el('th', {}, titleOf), cols.map((c, i) => el('th', { title: c, style: { writingMode: 'vertical-rl', transform: 'rotate(180deg)', height: '150px', cursor: 'pointer' }, onclick: () => store.select('comp:' + c, { fly: true }) }, names[i].slice(pre.length) || names[i])))));
    table.append(el('tbody', {}, rows.map((r) => el('tr', {},
      el('td', { style: { whiteSpace: 'nowrap', cursor: 'pointer' }, onclick: () => r.nodeId && store.nodes.has(r.nodeId) ? store.select(r.nodeId, { fly: true }) : focusRow(r) }, el('b', {}, r.label), el('span', { class: 'mini' }, ` · ${r.reqs.length}`)),
      cols.map((c) => {
        const ids = cells.get(r.key + '\u0001' + c);
        const a = ids.length / max;
        const isSel = ui.sel && ui.sel.row === r.key && ui.sel.col === c;
        return el('td', { class: 'c', style: { background: ids.length ? `rgba(57,208,255,${0.12 + a * 0.6})` : 'transparent', outline: isSel ? '2px solid #ffb020' : '' }, onclick: () => { ui.sel = { row: r.key, col: c, ids, r }; pickCell(r, c, ids); } }, ids.length || '');
      })))));
    return el('div', { class: 'tw', style: { maxHeight: '55vh' } }, table);
  }

  function focusRow(r) { store.setFocus([...r.reqs, ...r.reqs.flatMap((id) => implFiles(id).map((f) => f.id))], r.label); }

  function pickCell(r, comp, ids) {
    const files = new Set(); const other = new Set();
    for (const id of ids) for (const f of compsOf(id).get(comp) || []) { files.add(f.id); for (const a of store.adj.get(f.id) || []) { const n = store.node(a.id); if (n && ['part', 'api', 'table'].includes(n.type)) other.add(n.id); } }
    const set = [...ids, ...files, ...other, 'comp:' + comp, ...(r.nodeId ? [r.nodeId] : [])];
    store.setFocus(set, `${r.label} × ${comp.split('/').pop()}`);
    render();
  }

  function detail() {
    if (!ui.sel) return el('div', { class: 'mini', style: { marginTop: '12px' } }, t('place.pick'));
    const { ids, col, r } = ui.sel;
    const files = new Map();
    for (const id of ids) for (const f of compsOf(id).get(col) || []) files.set(f.id, f);
    return el('div', { class: 'card', style: { marginTop: '14px' } },
      el('h3', {}, `${r.label} × ${col}`),
      el('div', { class: 'grid cols2' },
        el('div', {}, el('h3', {}, t('type.req') + ` (${ids.length})`), el('div', { class: 'chips' }, ids.map((id) => nodeChip(id)))),
        el('div', {}, el('h3', {}, t('type.file') + ` (${files.size})`), el('div', { class: 'chips' }, [...files.keys()].map((id) => nodeChip(id))))),
      el('div', { class: 'row', style: { marginTop: '10px' } }, el('button', { class: 'btn', onclick: () => (location.hash = '#/map2d') }, '🗺 ' + t('place.to2d')), el('button', { class: 'btn', onclick: () => (location.hash = '#/map3d') }, '🧊 ' + t('place.to3d'))));
  }

  function bizSection(m, cols) {
    const reqs = m.reqs;
    let rows;
    if (ui.rowMode === 'goal') rows = m.goals.map((g) => ({ key: g.id, label: g.id, nodeId: g.id, reqs: reqs.filter((r) => r.goal === g.id).map((r) => r.id) }));
    else if (ui.rowMode === 'group') {
      const mp = new Map(); for (const r of reqs) { const k = r.file.split('/').pop().replace(/\.md$/, ''); if (!mp.has(k)) mp.set(k, []); mp.get(k).push(r.id); }
      rows = [...mp.entries()].map(([k, ids]) => ({ key: k, label: k, reqs: ids }));
    } else {
      const mp = new Map(); for (const r of reqs) { const k = r.kind === 'FR' ? 'FR' : 'NFR-' + r.cat; if (!mp.has(k)) mp.set(k, []); mp.get(k).push(r.id); }
      rows = [...mp.entries()].sort().map(([k, ids]) => ({ key: k, label: k, reqs: ids }));
    }
    if (ui.rowMode === 'goal') for (const r of rows) { const g = m.goals.find((x) => x.id === r.key); r.label = r.key + ' ' + (g?.title || '').slice(0, 20); }
    return el('div', {},
      el('div', { class: 'row', style: { marginBottom: '10px' } }, el('span', { class: 'mini' }, t('place.rows')), ['goal', 'group', 'cat'].map((k) => el('button', { class: 'tabbtn' + (ui.rowMode === k ? ' on' : ''), onclick: () => { ui.rowMode = k; ui.sel = null; render(); } }, t('place.row.' + k)))),
      rows.length && cols.length ? matrix(rows, cols, t('place.biz'), null) : el('div', { class: 'empty' }, t('none')), detail());
  }

  function dataSection(m, cols) {
    const ents = [...store.nodes.values()].filter((n) => n.type === 'entity' && n.deg > 0)
      .map((n) => ({ key: n.id, label: n.label, nodeId: n.id, reqs: store.neighbors(n.id, ['req']).map((x) => x.id) })).filter((r) => r.reqs.length).sort((a, b) => b.reqs.length - a.reqs.length);
    const tbls = [...store.nodes.values()].filter((n) => n.type === 'table' || n.type === 'api');
    return el('div', {},
      el('div', { class: 'mini', style: { marginBottom: '8px' } }, t('place.data.note')),
      ents.length && cols.length ? matrix(ents, cols, t('type.entity'), null) : el('div', { class: 'empty' }, t('none')),
      detail(),
      el('div', { class: 'card', style: { marginTop: '14px' } }, el('h3', {}, 'API / ' + t('type.table')),
        tbls.length ? el('div', { class: 'chips' }, tbls.map((n) => nodeChip(n.id))) : el('div', { class: 'empty' }, t('place.noapi'))));
  }

  function itemsSection() {
    const items = [...store.nodes.values()].filter((n) => ['part', 'api', 'table'].includes(n.type));
    if (!items.length) return el('div', { class: 'empty' }, t('place.noapi'));
    return el('div', { class: 'grid', style: { gridTemplateColumns: 'repeat(auto-fill,minmax(340px,1fr))' } }, items.map((n) => {
      const files = store.neighbors(n.id, ['file']).map((x) => store.node(x.id));
      const comps = [...new Set(files.map((f) => f.comp))];
      const reqs = store.neighbors(n.id, ['req']);
      return el('div', { class: 'card', style: { cursor: 'pointer' }, onclick: () => store.select(n.id, { fly: true }) },
        el('div', { class: 'row' }, el('i', { class: 'dot', style: { background: colorOf(n) } }), el('b', {}, n.label), el('span', { class: 'badge' }, t('type.' + n.type))),
        el('div', { class: 'mini', style: { margin: '6px 0' } }, (n.title || '').slice(0, 160)),
        el('div', { class: 'chips' }, comps.map((c) => nodeChip('comp:' + c))),
        el('div', { class: 'mini', style: { marginTop: '6px' } }, `${files.length} ${t('type.file')} · ${reqs.length} ${t('type.req')}`));
    }));
  }

  function render() {
    const m = store.model;
    const comps = [...store.nodes.values()].filter((n) => n.type === 'component' && (ui.tests || n.kind !== 'test'));
    const ranked = comps.map((c) => ({ c, n: store.neighbors(c.id, ['file']).length })).sort((a, b) => b.n - a.n).map((x) => x.c.path);
    page.replaceChildren(
      el('h1', {}, '🧭 ' + t('nav.placement')), el('p', { class: 'sub' }, t('place.sub')),
      el('div', { class: 'tbar' }, ['biz', 'data', 'items'].map((k) => el('button', { class: 'tabbtn' + (ui.tab === k ? ' on' : ''), onclick: () => { ui.tab = k; ui.sel = null; render(); } }, t('place.tab.' + k))),
        el('label', { class: 'row mini', style: { cursor: 'pointer' } }, el('input', { type: 'checkbox', checked: ui.tests || null, onchange: (e) => { ui.tests = e.target.checked; ui.sel = null; render(); } }), t('place.tests'))),
      ui.tab === 'biz' ? bizSection(m, ranked) : ui.tab === 'data' ? dataSection(m, ranked) : itemsSection());
  }
  render();
  const offs = [store.on('model', render), onLang(render)];
  return { destroy() { offs.forEach((f) => f()); } };
}
