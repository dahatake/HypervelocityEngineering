// FR-1042: external integration catalog (FR-1035) — list; the detail (16 viewpoints, requirements, ACs) opens in the drawer.
// Read-only: only the model built from the data layer is used; nothing is written and nothing is fetched.
import { t, onLang } from './i18n.js';
import { store, norm } from './store.js';
import { el } from './ui.js';
import { idRef } from './xref.js';
import { placeRows, listTiers } from './tierlist.js';

const state = { q: '', sort: { k: 'id', d: 1 } };
const COLS = ['id', 'name', 'partner', 'direction', 'method', 'dataClass', 'pii', 'status', 'reqs', 'gaps'];
const cell = (v) => (Array.isArray(v) ? v.join(', ') : v ?? '');

function rowsOf(m) {
  return (m.integrationCatalog || []).map((c) => ({
    nodeId: c.id, id: c.id, name: c.name, partner: c.partner, direction: c.direction, method: c.method, dataClass: c.dataClass,
    pii: c.pii, status: c.status, reqs: c.refs || c.reqs, gaps: `${t('int.missing')} ${c.missing} / ${t('int.tbd')} ${c.tbd}`, flag: c.flag,
        // i18n-data: "なし" is the managed-data value meaning "none"
  flags: [c.pii.trim() && c.pii.trim() !== 'なし' ? t('int.flag.pii') : '', /^TBD/i.test(c.authz.trim()) ? t('int.flag.auth') : ''].filter(Boolean),
  }));
}

export function mount(host) {
  const page = el('div', { class: 'page' });
  host.append(page);
  let fill = () => {};
  const render = () => {
    const m = store.model;
    const rows = rowsOf(m);
    if (!rows.length) {
      page.replaceChildren(el('h1', {}, '🔌 ' + t('nav.integrations')), el('p', { class: 'sub' }, t('navd.integrations')),
        el('div', { class: 'empty', 'data-testid': 'integrations-none' }, t('int.none')),
        // i18n-data: the names of the hierarchy are managed-data values
  listTiers([], { empty: [['外部連携', '連携カタログ', '未分類']], openAreas: true }));
      fill = () => {};
      return;
    }
    const input = el('input', { type: 'search', value: state.q, placeholder: t('int.filter'), 'aria-label': t('int.filter'), oninput: (e) => { state.q = e.target.value; fill(); } });
    const countEl = el('span', { class: 'mini' });
    const mkHead = () => el('tr', {}, COLS.map((k) => el('th', { onclick: () => { const c = state.sort; state.sort = { k, d: c.k === k ? -c.d : 1 }; render(); } },
      t('int.col.' + k), state.sort.k === k ? (state.sort.d > 0 ? ' ▲' : ' ▼') : '')).concat([el('th', {}, t('int.detail'))]));
    const tierHost = el('div', { class: 'tier-list-host', 'data-testid': 'integration-tiers' });
    page.replaceChildren(el('h1', {}, '🔌 ' + t('nav.integrations')), el('p', { class: 'sub' }, t('int.sub')),
      el('div', { class: 'tbar' }, input, countEl, el('button', { class: 'btn ghost', onclick: () => exportCsv(rows) }, '⤓ ' + t('int.csv'))),
      tierHost);
    const link = (id) => el('a', { href: '#/integrations?select=' + encodeURIComponent(id), class: 'mono', onclick: (e) => { e.preventDefault(); e.stopPropagation(); store.select(id, {}); } }, id);
    const reqLink = (id) => idRef(id);
    fill = () => {
      const set = store.activeSet();
      const q = norm(state.q);
      let list = rows.filter((r) => !q || norm(COLS.map((k) => cell(r[k])).join(' ')).includes(q));
      const s = state.sort;
      list = [...list].sort((a, b) => String(cell(a[s.k])).localeCompare(String(cell(b[s.k])), undefined, { numeric: true }) * s.d);
      countEl.textContent = `${list.length} / ${rows.length}`;
      // FR-1063 AC-348: 行を上位層（種類→区分→領域）の見出しの下にまとめる。
      const mkRow = (r) => el('tr', {
        'data-testid': 'integration-row', 'data-id': r.id,
        class: (r.id === store.selected ? 'sel ' : '') + (set && set.has(r.id) && r.id !== store.selected ? 'hl' : ''),
        onclick: () => store.select(r.id, {}),
      }, COLS.map((k) => {
        if (k === 'id') return el('td', {}, link(r.id));
        if (k === 'reqs') return el('td', {}, r.reqs.flatMap((x, i) => [i ? ', ' : '', reqLink(x)]));
        if (k === 'gaps') return el('td', {}, el('span', {}, r.gaps), ...r.flags.map((f) => el('span', { class: 'badge bad', style: { marginLeft: '6px' } }, '⚑ ' + f)));
        return el('td', {}, el('div', { class: 'clamp' }, String(cell(r[k])).slice(0, 400)));
      }).concat([el('td', {}, el('button', { class: 'btn ghost', type: 'button', 'aria-label': `${t('int.detail')} ${r.id}`, onclick: (e) => { e.stopPropagation(); store.select(r.id, {}); } }, t('int.detail')))]));
      // i18n-data: the kind name of a hierarchy item is a managed-data value
  const placed = placeRows(list, (r) => ({ kind: '外部連携', id: r.id }), t('nav.integrations'));
      tierHost.replaceChildren(listTiers(placed, {
        openAreas: true,
        extra: (node) => (node.level === 'area' && node.items.length
          ? el('div', { class: 'tw' }, el('table', { class: 't' }, el('thead', {}, mkHead()), el('tbody', {}, node.items.map((it) => mkRow(it.row)))))
          : null),
      }));
    };
    fill();
  };
  render();
  const offs = [store.on('model', render), onLang(render), store.on('select', () => fill())];
  return { destroy() { offs.forEach((f) => f()); } };
}

function exportCsv(rows) {
  const q = (v) => '"' + String(cell(v)).replace(/"/g, '""') + '"';
  const csv = [COLS.map((k) => q(t('int.col.' + k))).join(','), ...rows.map((r) => COLS.map((k) => q(r[k])).join(','))].join('\r\n');
  const a = el('a', { href: URL.createObjectURL(new Blob(['\ufeff' + csv], { type: 'text/csv' })), download: 'eabk-integrations.csv' });
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
