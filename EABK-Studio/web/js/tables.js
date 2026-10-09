// Table views: every kind of record in the data layer, sortable, filterable, and linked to the map selection.
import { t, onLang } from './i18n.js';
import { store, norm } from './store.js';
import { el, statusBadge, nodeChip, colorOf } from './ui.js';

let tab = 'reqs';
const state = { q: '', only: false, filters: {}, sort: { reqs: { k: 'id', d: 1 }, acs: { k: 'id', d: 1 } } };

const cell = (v) => (Array.isArray(v) ? v.join(', ') : v ?? '');

function defs(m) {
  const nodes = store.nodes;
  const reqNode = (id) => nodes.get(id);
  return {
    reqs: {
      cols: [['id'], ['title'], ['status'], ['priority'], ['goal'], ['impl'], ['acs'], ['blocked'], ['group']],
      filters: ['status', 'priority', 'goal', 'impl', 'group'],
      rows: () => m.reqs.map((r) => ({
        nodeId: r.id, id: r.id, title: r.title, status: r.statusKind, statusRaw: r.status, priority: r.priority, goal: r.goal,
        impl: reqNode(r.id)?.impl || '', acs: r.acs.length, blocked: r.blocked.join(' '), group: r.file.split('/').pop().replace(/\.md$/, ''),
      })),
    },
    acs: {
      cols: [['id'], ['req'], ['level'], ['blocked'], ['text']],
      filters: ['level'],
      rows: () => m.reqs.flatMap((r) => r.acs.map((a) => ({ nodeId: a.id, id: a.id, req: r.id, level: a.level, blocked: a.blocked, text: a.text }))),
    },
    cases: {
      cols: [['id'], ['title'], ['reqs'], ['acs'], ['layer'], ['status'], ['last_run_at']],
      filters: ['layer', 'status'],
      rows: () => m.cases.map((c) => ({ nodeId: c.id, id: c.id, title: c.title, reqs: (c.requirement_ids || []).join(', '), acs: (c.ac_ids || []).join(', '), layer: c.layer, status: c.status, last_run_at: c.last_run_at })),
    },
    parts: {
      cols: [['name'], ['purpose'], ['files'], ['reqs']],
      filters: [],
      rows: () => m.catalog.parts.map((p) => ({ nodeId: 'part:' + p.name, name: p.name, purpose: p.purpose, files: p.files.join(', '), reqs: p.reqs.length })),
    },
    apis: {
      cols: [['kind'], ['name'], ['owner'], ['files'], ['reqs']],
      filters: ['kind'],
      rows: () => [
        ...m.catalog.apis.map((a) => ({ nodeId: 'api:' + a.name, kind: 'API', name: a.name, owner: '', files: a.files.join(', '), reqs: a.reqs.join(', ') })),
        ...m.catalog.tables.map((a) => ({ nodeId: 'tbl:' + a.name, kind: t('type.table'), name: a.name, owner: a.owner, files: a.files.join(', '), reqs: a.reqs.join(', ') })),
      ],
    },
    files: {
      cols: [['path'], ['comp'], ['module'], ['role'], ['reqs']],
      filters: ['comp', 'role'],
      rows: () => [...nodes.values()].filter((n) => n.type === 'file').map((n) => ({ nodeId: n.id, path: n.path, comp: n.comp, module: n.module, role: n.role === 'test' ? 'test' : 'impl', reqs: store.neighbors(n.id, ['req']).length })),
    },
    params: { cols: [['id'], ['name'], ['value'], ['unit'], ['basis'], ['status']], filters: [], rows: () => m.params.map((p) => ({ nodeId: p.id, ...p })) },
    questions: { cols: [['id'], ['severity'], ['question'], ['state'], ['answer']], filters: ['severity', 'state'], rows: () => m.questions.map((q) => ({ nodeId: q.id, ...q })) },
    terms: { cols: [['term'], ['definition'], ['forbidden']], filters: [], rows: () => m.terms.map((x) => ({ nodeId: 'ent:' + x.term, ...x })) },
    personas: { cols: [['name'], ['work'], ['decision'], ['data'], ['role']], filters: [], rows: () => m.personas.map((p) => ({ nodeId: 'persona:' + p.name, ...p })) },
    integrations: { cols: [['name'], ['method'], ['meaning'], ['owner']], filters: [], rows: () => m.integrations.map((p) => ({ nodeId: 'ext:' + p.name, ...p })) },
    decisions: { cols: [['date'], ['target'], ['decision'], ['basis'], ['run']], filters: [], rows: () => m.decisions.map((p) => ({ ...p })) },
    audits: { cols: [['id'], ['date'], ['category'], ['severity'], ['where'], ['summary'], ['state']], filters: ['category', 'severity', 'state'], rows: () => m.audits.map((p) => ({ ...p })) },
    sources: { cols: [['id'], ['title'], ['version'], ['kind']], filters: [], rows: () => m.sources.map((p) => ({ ...p })) },
    runs: { cols: (m.runs[0] ? Object.keys(m.runs[0]).slice(0, 8) : []).map((k) => [k]), filters: [], rows: () => m.runs.map((r) => ({ ...r })) },
  };
}

export function mount(host) {
  const hk = new URLSearchParams(location.hash.split('?')[1] || '').get('tab');
  if (hk) tab = hk;
  const page = el('div', { class: 'page' });
  host.append(page);
  let fill = () => {};

  const render = () => {
    const m = store.model;
    const D = defs(m);
    if (!D[tab]) tab = 'reqs';
    const def = D[tab];
    const rows = def.rows();
    const colLabel = (k) => (tab === 'runs' ? k : t('col.' + k));

    const tabBar = el('div', { class: 'tbar' }, Object.keys(D).map((k) => el('button', { class: 'tabbtn' + (k === tab ? ' on' : ''), onclick: () => { tab = k; state.filters = {}; render(); } }, t('tab.' + k), el('small', {}, D[k].rows().length))));
    const input = el('input', { type: 'search', value: state.q, placeholder: t('tbl.filter'), oninput: (e) => { state.q = e.target.value; fill(); } });
    const only = el('label', { class: 'row mini', style: { cursor: 'pointer' } }, el('input', { type: 'checkbox', checked: state.only || null, onchange: (e) => { state.only = e.target.checked; fill(); } }), t('tbl.only'));
    const selects = (def.filters || []).map((k) => {
      const vals = [...new Set(rows.map((r) => cell(r[k])))].filter((v) => v !== '').sort();
      return el('select', { onchange: (e) => { state.filters[k] = e.target.value; fill(); } }, el('option', { value: '' }, colLabel(k) + ': ' + t('tbl.all')), vals.map((v) => el('option', { value: v, selected: state.filters[k] === v || null }, v)));
    });
    const countEl = el('span', { class: 'mini' });
    const head = el('tr', {}, def.cols.map(([k]) => el('th', { onclick: () => { const cur = state.sort[tab]; state.sort[tab] = { k, d: cur && cur.k === k ? -cur.d : 1 }; render(); } }, colLabel(k), state.sort[tab]?.k === k ? (state.sort[tab].d > 0 ? ' ▲' : ' ▼') : '')));
    const tbody = el('tbody');
    page.replaceChildren(el('h1', {}, '📋 ' + t('nav.tables')), el('p', { class: 'sub' }, t('tbl.sub')), tabBar,
      el('div', { class: 'tbar' }, input, ...selects, only, countEl, el('button', { class: 'btn ghost', onclick: () => exportCsv(def, rows, colLabel) }, '⤓ CSV')),
      el('div', { class: 'tw' }, el('table', { class: 't' }, el('thead', {}, head), tbody)));

    fill = () => {
      const set = store.activeSet();
      const q = norm(state.q);
      let list = rows.filter((r) => {
        for (const [k, v] of Object.entries(state.filters)) if (v && cell(r[k]) !== v) return false;
        if (q && !norm(Object.values(r).map(cell).join(' ')).includes(q)) return false;
        if (state.only && set && !(r.nodeId && set.has(r.nodeId))) return false;
        return true;
      });
      const s = state.sort[tab];
      if (s) list = [...list].sort((a, b) => String(cell(a[s.k])).localeCompare(String(cell(b[s.k])), undefined, { numeric: true }) * s.d);
      countEl.textContent = `${list.length} / ${rows.length}`;
      tbody.replaceChildren(...list.slice(0, 1500).map((r) => {
        const hl = set && r.nodeId && set.has(r.nodeId);
        return el('tr', { class: (r.nodeId && r.nodeId === store.selected ? 'sel ' : '') + (hl && r.nodeId !== store.selected ? 'hl' : ''), onclick: () => { if (r.nodeId && store.nodes.has(r.nodeId)) store.select(r.nodeId, {}); } },
          def.cols.map(([k]) => {
            const v = r[k];
            if (tab === 'reqs' && k === 'status') return el('td', {}, statusBadge(r.status, r.statusRaw));
            if (k === 'id' && r.nodeId && store.nodes.has(r.nodeId)) return el('td', { class: 'mono' }, el('span', { style: { color: colorOf(store.node(r.nodeId)) } }, v));
            if ((k === 'req' || k === 'goal') && store.nodes.has(v)) return el('td', {}, nodeChip(v));
            if (tab === 'cases' && k === 'status') return el('td', {}, el('span', { class: 'badge ' + (v === 'pass' ? 'pass' : v === 'fail' ? 'fail' : '') }, v));
            if (k === 'impl') return el('td', {}, el('span', { class: 'badge ' + (v === 'done' ? 'ok' : v === 'none' ? 'bad' : '') }, t('impl.' + (v || 'unlisted'))));
            return el('td', { class: k === 'path' || k === 'files' ? 'mono' : '' }, el('div', { class: 'clamp' }, String(cell(v)).slice(0, 400)));
          }));
      }));
      const sel = tbody.querySelector('tr.sel');
      if (sel) sel.scrollIntoView({ block: 'nearest' });
    };
    fill();
  };
  render();
  const offs = [store.on('model', render), onLang(render), store.on('select', () => fill())];
  return { destroy() { offs.forEach((f) => f()); } };
}

function exportCsv(def, rows, colLabel) {
  const q = (v) => '"' + String(cell(v)).replace(/"/g, '""') + '"';
  const csv = [def.cols.map(([k]) => q(colLabel(k))).join(','), ...rows.map((r) => def.cols.map(([k]) => q(r[k])).join(','))].join('\r\n');
  const a = el('a', { href: URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' })), download: 'eabk-' + tab + '.csv' });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
