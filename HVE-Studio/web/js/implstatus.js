// FR-1014: implementation-status screen (stacked progress bars + kanban + table).
// Reads model.implStatus (computed by eabk_model.build_impl_status); never writes to the repository.
import { t, onLang, lang } from './i18n.js';
import { store } from './store.js';
import { el } from './ui.js';
import { xrefLink } from './xref.js';
import { placeRows, listTiers } from './tierlist.js';
import { region, on as vizOn } from './viz.js';

// Colour is never the only cue: every state also has a symbol and a word (AC-093).
const STATE_META = [
  { sym: '○', color: 'var(--color-status-neutral-icon)' },
  { sym: '◔', color: 'var(--color-status-warning-icon)' },
  { sym: '✖', color: 'var(--color-status-danger-icon)' },
  { sym: '✔', color: 'var(--color-status-success-icon)' },
  { sym: '◇', color: 'var(--color-status-info-icon)' },
];
// Japanese: the state names come from the model (managed data); English: the dictionary (impl.st.<n>).
const stateLabel = (i, ja) => (lang() === 'ja' ? ja[i] : t('impl.st.' + i));
const caseText = (cases) => {
  const e = Object.entries(cases || {});
  return e.length ? e.map(([k, n]) => `${k} ${n}`).join(' / ') : '-';
};
// FR-1061: Gantt view state survives re-rendering (model reload, language switch) and axis changes (AC-340).
const gantt = { on: false, axis: 'all' };
const ms = (v) => { const n = typeof v === 'string' ? Date.parse(v) : NaN; return Number.isFinite(n) ? n : null; };
const day = (v) => (typeof v === 'string' ? v.slice(0, 10) : '-');

export function mount(host) {
  const page = el('div', { class: 'page', 'data-testid': 'impl-status' });
  host.append(page);
  // FR-1080: the page root is a viz region (data-viz="implstatus"); cards and bar segments are joined by key (viz.js).
  const viz = region(page, 'implstatus', { items: '[data-testid="impl-kanban-card"], [data-testid="impl-bar-segment"]',
    keyOf: (n) => (n.dataset.testid === 'impl-kanban-card' ? 'card:' + n.dataset.req : 'seg:' + n.dataset.scope + '|' + n.dataset.group + '|' + n.dataset.state) });
  let cardEls = [];
  // FR-1033: one filter {state, scope?, group?} drives every view; clicking a segment never navigates (AC-204).
  let filter = store.implFilter;
  let mode = 'highlight';
  let statusEl = null;
  const matches = (r) => !filter || ((!filter.state || r.state === filter.state) && (!filter.scope || r[filter.scope] === filter.group));
  const segRef = (seg, rows) => {
    seg._rows = rows;
    const go = () => toggle({ state: seg.dataset.state, scope: seg.dataset.scope === 'all' ? null : seg.dataset.scope, group: seg.dataset.scope === 'all' ? null : seg.dataset.group });
    vizOn(seg, 'click', go);
    vizOn(seg, 'keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
    return seg;
  };
  const toggle = (f) => {
    const same = filter && filter.state === f.state && filter.scope === f.scope && filter.group === f.group;
    store.setImplFilter(same ? null : f);
  };
  const applyFilter = () => {
    const flag = (node, ok) => {
      if (!filter) { node.removeAttribute('data-match'); node.hidden = false; return; }
      node.setAttribute('data-match', ok ? 'true' : 'false');
      node.hidden = mode === 'filter' && !ok && !node.classList.contains('impl-seg');
    };
    let hits = 0;
    page.querySelectorAll('[data-testid="impl-kanban-card"], [data-testid="impl-table"] tbody tr, [data-testid="impl-gantt-table"] tbody tr, [data-testid="impl-gantt-bar"]').forEach((n) => {
      const r = items.find((x) => x.id === n.dataset.req);
      const ok = !!r && matches(r);
      flag(n, ok);
      if (n.dataset.testid === 'impl-kanban-card' && ok) hits++;
    });
    page.querySelectorAll('[data-testid="impl-gantt-group"]').forEach((g) => {
      const on = !!filter && !filter.state && filter.scope === g.dataset.scope && filter.group === g.dataset.group;
      const h = g.querySelector('.impl-gantt-head');
      if (h) h.setAttribute('aria-pressed', on ? 'true' : 'false');
      const w = g.querySelector('.impl-gantt-head .impl-gantt-selword');
      if (w) w.hidden = !on;
    });
    page.querySelectorAll('.impl-seg').forEach((s) => {
      const ok = (s._rows || []).some(matches);
      flag(s, ok);
      s.setAttribute('aria-pressed', filter && filter.state && ok && s.dataset.state === filter.state && (filter.scope ? s.dataset.scope === filter.scope && s.dataset.group === filter.group : s.dataset.scope === 'all') ? 'true' : 'false');
    });
    page.querySelectorAll('[data-testid="impl-kanban-column"]').forEach((c) => { if (filter && filter.state) c.setAttribute('data-match', c.dataset.state === filter.state ? 'true' : 'false'); else c.removeAttribute('data-match'); });
    page.querySelectorAll('.impl-legend button').forEach((b) => b.setAttribute('aria-pressed', filter && filter.state && !filter.scope && b.dataset.state === filter.state ? 'true' : 'false'));
    if (statusEl) {
      statusEl.textContent = !filter ? t('impl3.none')
        : `${t('impl3.applied')}: ${filter.state || ''}${filter.scope ? `${filter.state ? ' × ' : ''}${filter.group}` : ''} — ${hits} ${t('impl3.count')}${hits ? '' : ` (${t('impl3.nomatch')})`}`;
      statusEl.dataset.active = filter ? 'true' : 'false';
    }
  };
  let items = [];

  const render = () => {
    viz.snap();
    const data = store.model.implStatus || { states: [], items: [], excluded: 0 };
    const ja = data.states;
    items = data.items;
    const bar = (scope, group, rows) => {
      const counts = ja.map((s) => rows.filter((r) => r.state === s).length);
      const total = rows.length;
      return el('div', { class: 'impl-bar-row' },
        el('div', { class: 'mini', style: { display: 'flex', justifyContent: 'space-between' } }, el('b', {}, group), el('span', {}, `${total}`)),
        el('div', { class: 'impl-bar', role: 'group', 'aria-label': `${group} ${total}`, 'data-testid': 'impl-bar', 'data-scope': scope, 'data-group': group,
          style: { display: 'flex', height: '26px', borderRadius: '6px', overflow: 'hidden', background: 'var(--color-bg-hover)' } },
        ja.map((s, i) => segRef(el('div', { class: 'impl-seg', role: 'button', tabindex: '0', 'aria-pressed': 'false', 'data-testid': 'impl-bar-segment', 'data-scope': scope, 'data-group': group, 'data-state': s, 'data-count': counts[i],
          title: `${stateLabel(i, ja)}: ${counts[i]}`,
          style: { flex: `${counts[i]} 0 0`, background: STATE_META[i].color, color: 'var(--color-bg-canvas)', display: counts[i] ? 'flex' : 'none', alignItems: 'center', justifyContent: 'center', fontWeight: '700', fontSize: '12px', minWidth: counts[i] ? '26px' : '0' } },
        `${STATE_META[i].sym} ${counts[i]}`), rows.filter((r) => r.state === s)))));
    };
    const groupBy = (key) => {
      const o = {};
      for (const r of items) (o[r[key]] ||= []).push(r);
      return Object.entries(o).sort((a, b) => a[0].localeCompare(b[0]));
    };
    const select = (id) => store.select(id, { fly: false });
    const onKey = (id) => (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(id); } };

    const legend = el('ul', { class: 'row impl-legend', 'aria-label': t('impl2.legend'), style: { listStyle: 'none', padding: 0, gap: '14px' } },
      ja.map((s, i) => el('li', {}, el('button', { type: 'button', 'data-testid': 'impl-legend-state', 'data-state': s, 'aria-pressed': 'false', onclick: () => toggle({ state: s, scope: null, group: null }) },
        el('span', { 'aria-hidden': 'true', style: { color: STATE_META[i].color, fontWeight: '700' } }, STATE_META[i].sym), ' ', stateLabel(i, ja)))));
    statusEl = el('span', { 'data-testid': 'impl-filter-status', role: 'status', 'aria-live': 'polite' });
    const filterBar = el('div', { class: 'impl-filter-bar' }, statusEl,
      el('button', { type: 'button', class: 'btn', 'data-testid': 'impl-filter-mode', onclick: (e) => { mode = mode === 'highlight' ? 'filter' : 'highlight'; e.currentTarget.textContent = t(mode === 'highlight' ? 'impl3.mode.hl' : 'impl3.mode.fl'); applyFilter(); } }, t(mode === 'highlight' ? 'impl3.mode.hl' : 'impl3.mode.fl')),
      el('button', { type: 'button', class: 'btn', 'data-testid': 'impl-filter-clear', onclick: () => store.setImplFilter(null) }, t('impl3.clear')));

    const columns = ja.map((s, i) => {
      const rows = items.filter((r) => r.state === s);
      return el('section', { class: 'card impl-col', 'data-testid': 'impl-kanban-column', 'data-scope': 'all', 'data-state': s, 'data-count': rows.length, 'aria-label': `${stateLabel(i, ja)} ${rows.length}`, style: { minWidth: '200px', flex: '1 1 200px', borderTop: `4px solid ${STATE_META[i].color}` } },
        el('h3', { style: { fontSize: '13px' } }, `${STATE_META[i].sym} ${stateLabel(i, ja)} (${rows.length})`),
        el('div', { style: { display: 'grid', gap: '6px' } }, rows.map((r) => el('div', { class: 'chip impl-card', 'data-testid': 'impl-kanban-card', 'data-req': r.id, 'data-state': r.state,
          tabindex: '0', style: { textAlign: 'left', whiteSpace: 'normal', overflowWrap: 'anywhere' }, onclick: () => select(r.id),
          onkeydown: (e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); select(r.id); } } },
        el('span', { class: 'mono' }, xrefLink(r.id)), ' ', r.title, r.blocked ? el('b', { class: 'badge fail', style: { marginLeft: '6px' } }, '⏸ ' + t('impl2.stalled')) : ''))));
    });

    const table = el('table', { class: 'tbl', 'data-testid': 'impl-table' },
      el('thead', {}, el('tr', {}, ['col.id', 'col.title', 'col.status', 'impl2.cases'].map((k) => el('th', { scope: 'col' }, t(k))))),
      el('tbody', {}, items.map((r) => {
        const i = ja.indexOf(r.state);
        return el('tr', { tabindex: '0', 'data-req': r.id, 'data-state': r.state, onclick: () => select(r.id), onkeydown: onKey(r.id) },
          el('td', { class: 'mono' }, r.id), el('td', {}, r.title),
          el('td', {}, `${STATE_META[i]?.sym || ''} ${stateLabel(i, ja)}`, r.blocked ? el('b', { class: 'badge fail', style: { marginLeft: '6px' } }, '⏸ ' + t('impl2.stalled')) : ''),
          el('td', {}, caseText(r.cases)));
      })));

    // FR-1063 AC-349: 要求を上位層（種類→区分→領域）でまとめ、各層の状態の内訳を件数で示す（内訳の合計は層の件数と一致）。
    const collect = (node) => [...node.items, ...[...node.children.values()].flatMap(collect)];
    // i18n-data: the kind name of a hierarchy item is a managed-data value
    const placed = placeRows(items, (r) => ({ kind: '要求', id: r.id }), '要求');
    const tiers = listTiers(placed, {
      extra: (node) => {
        const rows = collect(node);
        return el('p', { class: 'tier-breakdown mini', 'data-testid': 'tier-status-breakdown', 'aria-label': `${t('tier.breakdown')}` },
          el('span', { class: 'tier-breakdown-label' }, t('tier.breakdown') + ': '),
          ja.map((s, i) => el('span', { class: 'tier-breakdown-item', 'data-state': s }, `${STATE_META[i].sym} ${stateLabel(i, ja)} ${rows.filter((x) => x.row.state === s).length}`)),
          // 層の件数は FR-1062 の導出の件数。この画面に状態の登録がない要求は「状態の登録なし」として数え、内訳の合計が層の件数と一致する。
          el('span', { class: 'tier-breakdown-item', 'data-state': '' }, `– ${t('tier.nostate')} ${Math.max(0, node.count - rows.length)}`));
      },
      itemNode: (it) => el('div', { class: 'tier-item', role: 'treeitem', 'data-testid': 'tier-item', 'data-id': it.id, 'data-state': it.row.state },
        el('span', { class: 'mono' }, xrefLink(it.id)), ' ', it.row.title, ' ',
        el('span', { class: 'tier-state' }, `${STATE_META[ja.indexOf(it.row.state)]?.sym || ''} ${stateLabel(ja.indexOf(it.row.state), ja)}`)),
    });
    // FR-1061: Gantt chart (actual test period per requirement). Read-only; selection/filter are the shared ones (AC-340).
    const ganttBody = el('div', { 'data-testid': 'impl-gantt-body' });
    const barAction = (r) => {
      if (store.selected === r.id) { store.clear(); store.setImplFilter(null); } else { select(r.id); store.setImplFilter({ state: r.state, scope: null, group: null }); }
    };
    const headAction = (scope, group) => toggle({ state: null, scope, group });
    const navKeys = (act) => (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); act(); return; }
      if (e.key === 'Escape') { e.preventDefault(); store.clear(); store.setImplFilter(null); return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const all = [...ganttBody.querySelectorAll('[data-gnav]')];
        const i = all.indexOf(e.currentTarget);
        const nx = all[i + (e.key === 'ArrowDown' ? 1 : -1)];
        if (nx) nx.focus();
      }
    };
    const refreshGantt = () => {
      const frs = items.filter((r) => /^FR-\d+$/.test(r.id)); // FR-1061: one row per approved FR (NFRs are not charted)
      const dated = frs.filter((r) => ms(r.start) !== null && ms(r.end) !== null);
      const undated = frs.length - dated.length;
      let lo = Math.min(...dated.map((r) => ms(r.start))), hi = Math.max(...dated.map((r) => ms(r.end)));
      if (!dated.length) { lo = 0; hi = 1; }
      if (hi <= lo) hi = lo + 86400000;
      const span = hi - lo;
      const pct = (v) => ((v - lo) / span) * 100;
      const ticks = dated.length ? [0, 1, 2, 3, 4].map((k) => ({ k, at: lo + (span * k) / 4 })) : [];
      const axisRow = el('div', { class: 'impl-gantt-row impl-gantt-axisrow', 'aria-hidden': 'true' }, el('div', { class: 'impl-gantt-label mini' }, t('gantt.time')),
        el('div', { class: 'impl-gantt-track' }, ticks.map((x) => el('span', { class: 'impl-gantt-tick mini', style: { left: `${(x.k / 4) * 100}%`, transform: x.k === 4 ? 'translateX(-100%)' : x.k ? 'translateX(-50%)' : 'none' } }, new Date(x.at).toISOString().slice(0, 10)))));
      const row = (r) => {
        const i = ja.indexOf(r.state);
        const left = pct(ms(r.start)), width = Math.max(pct(ms(r.end)) - left, 1.2);
        const word = `${STATE_META[i]?.sym || ''} ${stateLabel(i, ja)}`;
        const side = left + width > 65 ? { right: `${100 - left}%` } : { left: `${left + width}%` };
        const sel = el('b', { class: 'impl-gantt-selword', hidden: store.selected !== r.id }, '◆ ' + t('gantt.sel'));
        const bar = el('div', { class: 'impl-gantt-bar', role: 'button', tabindex: '0', 'aria-pressed': store.selected === r.id ? 'true' : 'false', 'data-gnav': '1', 'data-testid': 'impl-gantt-bar', 'data-req': r.id,
          'data-start': r.start, 'data-end': r.end, 'data-state': r.state, 'aria-label': `${r.id} ${r.title} ${stateLabel(i, ja)} ${day(r.start)} – ${day(r.end)}${r.blocked ? ' ' + t('impl2.stalled') : ''}`,
          title: `${r.id} ${r.title}: ${day(r.start)} – ${day(r.end)}`, style: { left: `${left}%`, width: `${width}%`, background: STATE_META[i]?.color }, onclick: () => barAction(r), onkeydown: navKeys(() => barAction(r)) },
        el('span', { 'aria-hidden': 'true' }, STATE_META[i]?.sym || ''));
        return el('div', { class: 'impl-gantt-row' },
          el('div', { class: 'impl-gantt-label', onclick: () => barAction(r) }, el('span', { class: 'mono' }, r.id), ' ', r.title, r.blocked ? el('b', { class: 'badge fail', style: { marginLeft: '6px' } }, '⏸ ' + t('impl2.stalled')) : '', ' ', sel),
          el('div', { class: 'impl-gantt-track' }, bar, el('span', { class: 'impl-gantt-word mini', style: side }, word + (r.blocked ? ' ⏸' : ''))));
      };
      const groups = [];
      if (gantt.axis === 'all') groups.push([null, dated]);
      else {
        const o = {};
        for (const r of dated) (o[r[gantt.axis]] ||= []).push(r);
        Object.entries(o).sort((a, b) => a[0].localeCompare(b[0])).forEach((g) => groups.push(g));
      }
      const chart = el('div', { class: 'impl-gantt', 'data-testid': 'impl-gantt', 'data-axis': gantt.axis, role: 'group', 'aria-label': t('gantt.title') }, axisRow,
        dated.length ? groups.map(([g, rs]) => (g === null ? rs.map(row)
          : el('div', { 'data-testid': 'impl-gantt-group', 'data-group': g, 'data-scope': gantt.axis },
            el('div', { class: 'impl-gantt-head', role: 'button', tabindex: '0', 'aria-pressed': 'false', 'data-gnav': '1', onclick: () => headAction(gantt.axis, g), onkeydown: navKeys(() => headAction(gantt.axis, g)) },
              el('b', {}, g), ' ', el('span', { class: 'mini' }, `(${rs.length})`), ' ', el('b', { class: 'impl-gantt-selword', hidden: true }, '◆ ' + t('gantt.sel'))),
            rs.map(row)))).flat() : el('p', { class: 'mini' }, t('gantt.none')));
      const lgd = el('ul', { class: 'row impl-gantt-legend', 'data-testid': 'impl-gantt-legend', 'aria-label': t('gantt.legend'), style: { listStyle: 'none', padding: 0, gap: '14px' } },
        ja.map((s, i) => el('li', {}, el('span', { class: 'impl-gantt-swatch', 'aria-hidden': 'true', style: { background: STATE_META[i].color } }, STATE_META[i].sym), ' ', stateLabel(i, ja))),
        el('li', {}, el('b', { class: 'badge fail' }, '⏸ ' + t('impl2.stalled'))), el('li', {}, el('b', {}, '◆ ' + t('gantt.sel'))));
      const tbl = el('table', { class: 'tbl', 'data-testid': 'impl-gantt-table' },
        el('thead', {}, el('tr', {}, ['col.id', 'col.title', 'col.status', 'gantt.start', 'gantt.end'].map((k) => el('th', { scope: 'col' }, t(k))))),
        el('tbody', {}, frs.map((r) => {
          const i = ja.indexOf(r.state);
          const ok = ms(r.start) !== null && ms(r.end) !== null;
          return el('tr', { tabindex: '0', 'data-req': r.id, 'data-state': r.state, onclick: () => select(r.id), onkeydown: onKey(r.id) },
            el('td', { class: 'mono' }, r.id), el('td', {}, r.title),
            el('td', {}, `${STATE_META[i]?.sym || ''} ${stateLabel(i, ja)}`, r.blocked ? el('b', { class: 'badge fail', style: { marginLeft: '6px' } }, '⏸ ' + t('impl2.stalled')) : ''),
            el('td', {}, ok ? r.start : t('gantt.undated.cell')), el('td', {}, ok ? r.end : t('gantt.undated.cell')));
        })));
      ganttBody.replaceChildren(chart, lgd,
        el('p', { class: 'mini', 'data-testid': 'impl-gantt-undated', 'data-count': undated }, `${t('gantt.undated')}: ${undated}`),
        el('details', {}, el('summary', {}, t('gantt.tbl')), el('div', { style: { overflow: 'auto' } }, tbl)));
      cardEls = [...page.querySelectorAll('[data-req]')];
    };
    const axisSel = el('select', { 'data-testid': 'impl-gantt-axis', 'aria-label': t('gantt.axis'), onchange: (e) => { gantt.axis = e.target.value; refreshGantt(); mark(); applyFilter(); } },
      [['all', 'impl2.all'], ['goal', 'impl2.goal'], ['priority', 'impl2.priority']].map(([v, k]) => el('option', { value: v, selected: gantt.axis === v }, t(k))));
    axisSel.value = gantt.axis;
    const ganttShown = gantt.on && !!store.model.implStatus;
    const ganttCard = ganttShown ? el('section', { class: 'card', style: { marginTop: '16px' }, 'aria-label': t('gantt.title') },
      el('h2', {}, t('gantt.title')), el('p', { class: 'sub' }, t('gantt.sub')),
      el('label', { class: 'mini' }, t('gantt.axis') + ': ', axisSel), ganttBody) : '';
    const viewBtn = el('button', { type: 'button', class: 'btn', 'data-testid': 'impl-gantt-toggle', 'aria-pressed': gantt.on ? 'true' : 'false',
      onclick: () => { gantt.on = !gantt.on; refocus = true; render(); } }, (gantt.on ? '▣ ' : '▢ ') + t('gantt.view'));

    page.replaceChildren(
      el('h1', {}, '🚀 ' + t('nav.implstatus')),
      el('p', { class: 'sub' }, t('impl2.sub')),
      legend, filterBar, el('div', { style: { margin: '8px 0' } }, viewBtn),
      el('section', { class: 'card impl-tiers', 'data-testid': 'impl-tiers' }, el('h2', {}, t('impl.tiers')), el('p', { class: 'mini' }, t('impl.tiers.sub')), tiers),
      el('div', { class: 'card' }, el('h2', {}, t('impl2.all')), bar('all', t('impl2.all'), items)),
      el('div', { class: 'grid cols2', style: { marginTop: '16px' } },
        el('div', { class: 'card' }, el('h2', {}, t('impl2.goal')), el('div', { style: { display: 'grid', gap: '10px' } }, groupBy('goal').map(([g, rs]) => bar('goal', g, rs)))),
        el('div', { class: 'card' }, el('h2', {}, t('impl2.priority')), el('div', { style: { display: 'grid', gap: '10px' } }, groupBy('priority').map(([g, rs]) => bar('priority', g, rs))))),
      ganttCard,
      el('p', { class: 'mini', 'data-testid': 'impl-excluded', 'data-count': data.excluded, style: { marginTop: '12px' } }, `${t('impl2.excluded')}: ${data.excluded}`),
      el('h2', { style: { marginTop: '16px' } }, t('impl2.kanban')),
      el('div', { class: 'row', style: { alignItems: 'stretch', flexWrap: 'wrap', gap: '10px' } }, columns),
      el('h2', { style: { marginTop: '16px' } }, t('impl2.table')),
      el('div', { style: { overflow: 'auto' } }, table));
    if (ganttShown) refreshGantt();
    viz.sync();
    cardEls = [...page.querySelectorAll('[data-req]')];
    mark();
    applyFilter();
    if (refocus) { refocus = false; page.querySelector('[data-testid="impl-gantt-toggle"]')?.focus(); }
  };
  let refocus = false;
  const mark = () => {
    cardEls.forEach((c) => c.classList.toggle('on', c.dataset.req === store.selected));
    page.querySelectorAll('[data-testid="impl-gantt-bar"]').forEach((b) => {
      const on = b.dataset.req === store.selected;
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      const w = b.closest('.impl-gantt-row')?.querySelector('.impl-gantt-selword');
      if (w) w.hidden = !on;
    });
  };
  render();
  const offs = [store.on('implfilter', (f) => { filter = f; applyFilter(); }), store.on('model', render), onLang(render), store.on('select', mark)];
  return { destroy() { offs.forEach((f) => f()); viz.destroy(); } };
}
