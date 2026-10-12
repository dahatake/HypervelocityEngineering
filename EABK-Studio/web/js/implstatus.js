// FR-1014: implementation-status screen (stacked progress bars + kanban + table).
// Reads model.implStatus (computed by eabk_model.build_impl_status); never writes to the repository.
import { t, onLang, lang } from './i18n.js';
import { store } from './store.js';
import { el } from './ui.js';

// Colour is never the only cue: every state also has a symbol and a word (AC-093).
const STATE_META = [
  { sym: '○', color: '#6b7a9c', en: 'Not started' },
  { sym: '◔', color: '#ffb020', en: 'Registered · no test registered' },
  { sym: '✖', color: '#ff5c7a', en: 'Registered · test not passing' },
  { sym: '✔', color: '#34e0a1', en: 'Test passed' },
  { sym: '◇', color: '#7dd3fc', en: 'Registered · outside system test' },
];
const stateLabel = (i, ja) => (lang() === 'ja' ? ja[i] : STATE_META[i].en);
const caseText = (cases) => {
  const e = Object.entries(cases || {});
  return e.length ? e.map(([k, n]) => `${k} ${n}`).join(' / ') : '-';
};

export function mount(host) {
  const page = el('div', { class: 'page', 'data-testid': 'impl-status' });
  host.append(page);
  let cardEls = [];

  const render = () => {
    const data = store.model.implStatus || { states: [], items: [], excluded: 0 };
    const ja = data.states;
    const items = data.items;
    const bar = (scope, group, rows) => {
      const counts = ja.map((s) => rows.filter((r) => r.state === s).length);
      const total = rows.length;
      return el('div', { class: 'impl-bar-row' },
        el('div', { class: 'mini', style: { display: 'flex', justifyContent: 'space-between' } }, el('b', {}, group), el('span', {}, `${total}`)),
        el('div', { class: 'impl-bar', role: 'group', 'aria-label': `${group} ${total}`, 'data-testid': 'impl-bar', 'data-scope': scope, 'data-group': group,
          style: { display: 'flex', height: '26px', borderRadius: '6px', overflow: 'hidden', background: '#1b2442' } },
        ja.map((s, i) => el('div', { class: 'impl-seg', 'data-testid': 'impl-bar-segment', 'data-scope': scope, 'data-group': group, 'data-state': s, 'data-count': counts[i],
          title: `${stateLabel(i, ja)}: ${counts[i]}`,
          style: { flex: `${counts[i]} 0 0`, background: STATE_META[i].color, color: '#0b1020', display: counts[i] ? 'flex' : 'none', alignItems: 'center', justifyContent: 'center', fontWeight: '700', fontSize: '12px', minWidth: counts[i] ? '26px' : '0' } },
        `${STATE_META[i].sym} ${counts[i]}`))));
    };
    const groupBy = (key) => {
      const o = {};
      for (const r of items) (o[r[key]] ||= []).push(r);
      return Object.entries(o).sort((a, b) => a[0].localeCompare(b[0]));
    };
    const select = (id) => store.select(id, { fly: false });
    const onKey = (id) => (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(id); } };

    const legend = el('ul', { class: 'row impl-legend', 'aria-label': t('impl2.legend'), style: { listStyle: 'none', padding: 0, gap: '14px' } },
      ja.map((s, i) => el('li', {}, el('span', { 'aria-hidden': 'true', style: { color: STATE_META[i].color, fontWeight: '700' } }, STATE_META[i].sym), ' ', stateLabel(i, ja))));

    const columns = ja.map((s, i) => {
      const rows = items.filter((r) => r.state === s);
      return el('section', { class: 'card impl-col', 'data-testid': 'impl-kanban-column', 'data-scope': 'all', 'data-state': s, 'data-count': rows.length, 'aria-label': `${stateLabel(i, ja)} ${rows.length}`, style: { minWidth: '200px', flex: '1 1 200px', borderTop: `4px solid ${STATE_META[i].color}` } },
        el('h3', { style: { fontSize: '13px' } }, `${STATE_META[i].sym} ${stateLabel(i, ja)} (${rows.length})`),
        el('div', { style: { display: 'grid', gap: '6px' } }, rows.map((r) => el('button', { type: 'button', class: 'chip impl-card', 'data-testid': 'impl-kanban-card', 'data-req': r.id, 'data-state': r.state,
          'aria-label': `${r.id} ${r.title} ${stateLabel(i, ja)}${r.blocked ? ' ' + t('impl2.stalled') : ''}`, style: { textAlign: 'left', whiteSpace: 'normal' }, onclick: () => select(r.id) },
        el('span', { class: 'mono' }, r.id), ' ', r.title, r.blocked ? el('b', { class: 'badge fail', style: { marginLeft: '6px' } }, '⏸ ' + t('impl2.stalled')) : ''))));
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

    page.replaceChildren(
      el('h1', {}, '🚀 ' + t('nav.implstatus')),
      el('p', { class: 'sub' }, t('impl2.sub')),
      legend,
      el('div', { class: 'card' }, el('h2', {}, t('impl2.all')), bar('all', t('impl2.all'), items)),
      el('div', { class: 'grid cols2', style: { marginTop: '16px' } },
        el('div', { class: 'card' }, el('h2', {}, t('impl2.goal')), el('div', { style: { display: 'grid', gap: '10px' } }, groupBy('goal').map(([g, rs]) => bar('goal', g, rs)))),
        el('div', { class: 'card' }, el('h2', {}, t('impl2.priority')), el('div', { style: { display: 'grid', gap: '10px' } }, groupBy('priority').map(([g, rs]) => bar('priority', g, rs))))),
      el('p', { class: 'mini', 'data-testid': 'impl-excluded', 'data-count': data.excluded, style: { marginTop: '12px' } }, `${t('impl2.excluded')}: ${data.excluded}`),
      el('h2', { style: { marginTop: '16px' } }, t('impl2.kanban')),
      el('div', { class: 'row', style: { alignItems: 'stretch', flexWrap: 'wrap', gap: '10px' } }, columns),
      el('h2', { style: { marginTop: '16px' } }, t('impl2.table')),
      el('div', { style: { overflow: 'auto' } }, table));
    cardEls = [...page.querySelectorAll('[data-req]')];
    mark();
  };
  const mark = () => cardEls.forEach((c) => c.classList.toggle('on', c.dataset.req === store.selected));
  render();
  const offs = [store.on('model', render), onLang(render), store.on('select', mark)];
  return { destroy() { offs.forEach((f) => f()); } };
}
