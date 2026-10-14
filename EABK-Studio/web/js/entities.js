// Entity × use-case matrix (FR-1021) and entity detail (FR-1022).  Data: model.entities (derived by scripts/entities.py,
// see eabk_model.build_entities) joined with the requirements, state machines and graph already in the store.
import { t, onLang } from './i18n.js';
import { store, norm } from './store.js';
import { el, statusBadge, nodeChip, vscodeUrl, typeLabel } from './ui.js';
import { mountShell } from './semzoom.js';
import { create2d } from './sz2d.js';

const WORDS = ['作成', '参照', '更新', '削除'];
const SYMBOL = { 作成: 'C', 参照: 'R', 更新: 'U', 削除: 'D' };
const state = { rowq: '', colq: '', sort: 'name', col: null, text: false };

const word = (w) => (WORDS.includes(w) ? t('eu.w.' + w) : w);
const usageText = (ws) => ws.map((w) => `${SYMBOL[w] || '·'} ${word(w)}`).join(' / ');
const scnLabel = (n) => t('eu.scn', { n });
const csvCell = (s) => (/[",\n]/.test(s) ? '"' + String(s).replace(/"/g, '""') + '"' : String(s));

function loc(file, line) {
  if (!file) return el('span', { class: 'mini' }, t('eu.unwritten'));
  return el('span', { class: 'row mini' }, el('span', { class: 'mono' }, `${file}${line ? ':' + line : ''}`), el('a', { href: vscodeUrl(file, line), title: 'VS Code' }, '↗'));
}

// Columns: requirements that use at least one entity, requirements without an entity, then usage scenarios.
function buildColumns(m) {
  const used = new Map();
  for (const e of m.entities.entities) for (const u of e.usecases) if (!used.has(u.requirement)) used.set(u.requirement, u.title);
  const cols = [...used].map(([id, title]) => ({ kind: 'req', id, title, key: id }));
  const none = [];
  for (const r of m.reqs) if (!used.has(r.id) && r.statusKind !== 'retired' && r.statusKind !== 'rejected') none.push({ kind: 'req', id: r.id, title: r.title, key: r.id, none: true });
  const scn = Object.keys(m.entities.scenarios).map((n) => ({ kind: 'scn', id: Number(n), title: m.entities.scenarios[n], key: 'S' + n }));
  return [...cols, ...none, ...scn];
}

// The cell for (entity, column): {has: bool, words: [...]}
function cellOf(e, c) {
  const ucs = e.usecases.filter((u) => (c.kind === 'req' ? u.requirement === c.id : u.scenarios.includes(c.id)));
  if (!ucs.length) return null;
  const ws = WORDS.filter((w) => ucs.some((u) => u.usages.includes(w)));
  return ws;
}
const cellText = (ws) => (ws === null ? '' : ws.length ? usageText(ws) : t('eu.used'));
const colHead = (c) => (c.kind === 'req' ? c.id : scnLabel(c.id));

function matrixText(rows, cols) {
  const lines = [[t('eu.entity'), ...cols.map(colHead)].map(csvCell).join(',')];
  for (const e of rows) lines.push([e.name, ...cols.map((c) => cellText(cellOf(e, c)))].map(csvCell).join(','));
  return lines.join('\n') + '\n';
}

function download(name, text) {
  const url = URL.createObjectURL(new Blob(['\ufeff' + text], { type: 'text/csv;charset=utf-8' }));
  const a = el('a', { href: url, download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function matrixView(host, m) {
  const ents = m.entities.entities;
  const allCols = buildColumns(m);
  const rq = norm(state.rowq), cq = norm(state.colq);
  let rows = ents.filter((e) => !rq || norm(e.name + ' ' + e.description).includes(rq));
  let cols = allCols.filter((c) => !cq || norm(c.id + ' ' + c.title + ' ' + (c.none ? t('eu.noent') : '')).includes(cq));
  if (state.sort === 'use') rows = [...rows].sort((a, b) => b.usecases.length - a.usecases.length || a.name.localeCompare(b.name));
  const unused = ents.filter((e) => !e.usecases.length);

  const controls = el('div', { class: 'row eu-controls' },
    el('input', { type: 'search', value: state.rowq, 'aria-label': t('eu.rowq'), placeholder: t('eu.rowq'), oninput: (ev) => { state.rowq = ev.target.value; redraw(ev.target); } }),
    el('input', { type: 'search', value: state.colq, 'aria-label': t('eu.colq'), placeholder: t('eu.colq'), oninput: (ev) => { state.colq = ev.target.value; redraw(ev.target); } }),
    el('label', { class: 'mini' }, t('eu.sort') + ' ',
      el('select', { onchange: (ev) => { state.sort = ev.target.value; redraw(); } },
        ...['name', 'use'].map((k) => el('option', { value: k, selected: state.sort === k ? true : null }, t('eu.sort.' + k))))),
    el('button', { class: 'btn ghost', onclick: () => download('entity-usecase-matrix.csv', matrixText(rows, cols)) }, '⭳ ' + t('eu.csv')),
    el('button', { class: 'btn ghost', 'aria-expanded': String(state.text), onclick: () => { state.text = !state.text; redraw(); } }, '≣ ' + t('eu.text')),
    state.col ? el('button', { class: 'btn ghost', onclick: () => { state.col = null; redraw(); } }, `${t('eu.colsel')}: ${state.col} ✕ ${t('eu.clear')}`) : null);

  const table = el('table', { class: 'eu-matrix' });
  table.append(el('thead', {}, el('tr', {},
    el('th', { scope: 'col' }, t('eu.entity')),
    ...cols.map((c) => el('th', { scope: 'col', class: state.col === c.key ? 'sel' : '', title: `${c.id} ${c.title}${c.none ? ' — ' + t('eu.noent') : ''}` },
      el('button', { class: 'eu-h', 'aria-pressed': String(state.col === c.key), onclick: () => { state.col = state.col === c.key ? null : c.key; if (c.kind === 'req' && store.node(c.id) && state.col) store.select(c.id); redraw(); } },
        colHead(c), c.none ? el('small', {}, ' ' + t('eu.noent')) : null))))));
  const body = el('tbody');
  for (const e of rows) {
    body.append(el('tr', {},
      el('th', { scope: 'row', class: e.usecases.length ? '' : 'eu-unused', 'data-unused': e.usecases.length ? null : t('eu.unused') },
        el('button', { class: 'eu-h', title: e.description || '', onclick: () => { location.hash = '#/entities?entity=' + encodeURIComponent(e.name); } }, e.name)),
      ...cols.map((c) => {
        const ws = cellOf(e, c);
        return el('td', { class: (ws === null ? '' : 'on ') + (state.col === c.key ? 'sel' : '') }, cellText(ws));
      })));
  }
  table.append(body);

  const extra = [];
  if (!rows.length || !cols.length) extra.push(el('div', { class: 'empty' }, t('eu.nomatch')));
  if (unused.length) extra.push(el('p', { class: 'mini eu-unusedlist' }, `${t('eu.unusedlist')}: `, ...unused.map((e) => el('span', { class: 'badge' }, e.name))));
  const entless = allCols.filter((c) => c.none);
  if (entless.length) extra.push(el('p', { class: 'mini' }, `${t('eu.noentcols')}: `, ...entless.map((c) => el('span', { class: 'badge' }, c.id))));
  extra.push(el('p', { class: 'mini' }, `${t('eu.legend')}: ` + WORDS.map((w) => `${SYMBOL[w]} ${word(w)}`).join(' / ') + ` / ${t('eu.used')}`));
  extra.push(el('details', {}, el('summary', { class: 'mini' }, t('eu.cols')),
    el('ul', { class: 'eu-cols' }, ...allCols.map((c) => el('li', {}, el('b', {}, colHead(c)), ' ', c.title)))));
  if (state.text) extra.push(el('textarea', { class: 'eu-text', readonly: true, rows: Math.min(20, rows.length + 2), 'aria-label': t('eu.text') }, matrixText(rows, cols)));

  host.replaceChildren(controls, el('div', { class: 'eu-scroll' }, table), ...extra);
  function redraw(focusEl) {
    const pos = focusEl ? focusEl.selectionStart : null;
    matrixView(host, m);
    if (focusEl) { const again = [...host.querySelectorAll('input')].find((i) => i.getAttribute('aria-label') === focusEl.getAttribute('aria-label')); again?.focus(); if (pos != null) again?.setSelectionRange(pos, pos); }
  }
}

function detailView(host, m, name) {
  const e = m.entities.entities.find((x) => x.name === name);
  const back = el('a', { class: 'btn ghost', href: '#/entities' }, t('eu.back'));
  if (!e) { host.replaceChildren(back, el('div', { class: 'warnbox' }, t('eu.notfound'))); return; }
  const nodeId = 'ent:' + e.name;
  const sm = m.stateMachines.find((x) => x.entity === e.name);
  const none = () => el('span', { class: 'mini' }, t('eu.nodata'));
  const unwritten = () => el('span', { class: 'mini' }, t('eu.unwritten'));
  const section = (title, ...body) => el('section', { class: 'eu-sec' }, el('h2', {}, title), ...body);

  const reqs = e.usecases.map((u) => ({ u, r: store.reqMap.get(u.requirement) }));
  const scn = [...new Set(e.usecases.flatMap((u) => u.scenarios))].sort((a, b) => a - b);
  const partIds = [];
  for (const { u } of reqs) for (const a of store.neighbors(u.requirement, ['part', 'api', 'component'])) if (!partIds.includes(a.id)) partIds.push(a.id);

  host.replaceChildren(
    el('div', { class: 'row' }, back,
      el('a', { class: 'btn ghost', href: '#/diagrams?kind=entities&select=' + encodeURIComponent(nodeId) }, t('eu.toER')),
      el('a', { class: 'btn ghost', href: '#/diagrams?kind=layers&select=' + encodeURIComponent(nodeId) }, t('eu.toLayers'))),
    el('h1', {}, '🔗 ' + e.name),
    section(t('eu.d.desc'), e.description ? el('div', {}, e.description) : unwritten(), el('div', {}, t('eu.src') + ': ', loc(e.position.file, e.position.line))),
    section(t('eu.d.states'), sm && sm.rows && sm.rows.length
      ? el('table', { class: 'eu-sub' }, el('thead', {}, el('tr', {}, el('th', {}, t('eu.state')), el('th', {}, t('eu.cond')), el('th', {}, t('eu.src')))),
        el('tbody', {}, ...sm.rows.map((r) => el('tr', {}, el('td', {}, r.state), el('td', {}, r.condition || t('eu.nodata')), el('td', {}, loc(sm.file, r.line))))))
      : none()),
    section(t('eu.d.reqs'), reqs.length
      ? el('table', { class: 'eu-sub' }, el('thead', {}, el('tr', {}, ['ID', '', '', t('eu.usage'), t('eu.src')].map((h) => el('th', {}, h)))),
        el('tbody', {}, ...reqs.map(({ u, r }) => el('tr', {},
          el('td', {}, store.node(u.requirement) ? nodeChip(u.requirement, u.requirement) : u.requirement),
          el('td', {}, u.title),
          el('td', {}, r ? statusBadge(r.statusKind, r.status) : ''),
          el('td', {}, u.usages.length ? usageText(u.usages) : t('eu.used')),
          el('td', {}, r ? loc(r.file, r.line) : unwritten())))))
      : none()),
    section(t('eu.d.scn'), scn.length
      ? el('ul', {}, ...scn.map((n) => el('li', {}, `${n}. ${m.entities.scenarios[String(n)]}`)))
      : none()),
    section(t('eu.d.tables'), e.tables.length
      ? el('ul', {}, ...e.tables.map((tb) => el('li', {}, el('b', {}, tb.name), ' ', loc(tb.file))))
      : unwritten()),
    section(t('eu.d.parts'), partIds.length
      ? el('div', { class: 'chips' }, partIds.map((id) => el('span', {}, nodeChip(id), ' ', el('small', { class: 'mini' }, typeLabel(store.node(id))))))
      : none()));
}

export function mount(host) {
  const page = el('div', { class: 'page eu' });
  host.append(page);
  let zoom = null;   // FR-1027: semantic zoom of the relations and columns, below the matrix (the matrix keeps its place)
  const render = () => {
    zoom?.destroy(); zoom = null;
    const m = store.model;
    const name = new URLSearchParams(location.hash.split('?')[1] || '').get('entity');
    const body = el('div');
    page.replaceChildren(el('h1', {}, '🔗 ' + t('eu.title')), body);
    if (!m.entities || !m.entities.entities.length) {
      page.replaceChildren(el('h1', {}, '🔗 ' + t('eu.title')),
        el('div', { class: 'empty' }, el('h2', {}, t('eu.none.h')), el('p', {}, t('eu.none.d')), m.entities && !m.entities.available ? el('p', { class: 'mini' }, t('eu.unavail')) : null));
      return;
    }
    if (name) { page.replaceChildren(el('div', { class: 'eu-detail' })); detailView(page.firstChild, m, name); return; }
    page.append(el('p', { class: 'sub' }, t('eu.sub')));
    const mat = el('div');
    page.append(mat);
    matrixView(mat, m);
    const zoomHost = el('div', { class: 'eu-zoom' });
    page.append(zoomHost);
    zoom = mountShell(zoomHost, { mode: 'entities', createRenderer: create2d, height: 560,
      links: [{ id: 'sz-to-2d', label: () => t('sz.to2d'), href: '#/map2d' }, { id: 'sz-to-3d', label: () => t('sz.to3d'), href: '#/map3d' }] });
  };
  render();
  const offs = [onLang(render), store.on('model', render)];
  return { destroy() { offs.forEach((f) => f()); zoom?.destroy(); } };
}
