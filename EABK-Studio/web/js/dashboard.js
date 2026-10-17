// Dashboard: product-manager overview with clickable charts (click -> highlight on the map).
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, statusText, STATUS_COLOR, TYPE_COLOR, animateNumber, businessIcon, token } from './ui.js';

const PALETTE = ['--viz-sel', '--viz-accent-2', '--viz-accent-3', '--viz-api', '--viz-goal', '--viz-entity', '--viz-external', '--viz-param'];
let persona = 'Product Manager';

function focusAndGo(ids, label) {
  if (!ids.length) return;
  store.setFocus(ids, label);
  location.hash = '#/map2d';
}

// ドーナツ図は svg ではなく CSS の円錐グラデーションで描く（アイコン以外の大きな svg を持たない。FR-1048 AC-268）。
// 区分ごとの操作は凡例（legend）から行う。数値と名前は凡例と読み上げ名にも載せる。
function donut(data) {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  let acc = 0;
  const stops = [];
  for (const d of data) {
    if (!d.value) continue;
    const from = acc / total * 100;
    acc += d.value;
    stops.push(d.color + ' ' + from + '% ' + (acc / total * 100) + '%');
  }
  const ring = el('div', { class: 'donut', role: 'img', 'aria-label': data.filter((d) => d.value).map((d) => d.label + ' ' + d.value).join(', ') + ' / ' + t('dash.total') + ' ' + total,
    style: { background: 'conic-gradient(' + (stops.join(', ') || 'var(--color-border-default) 0 100%') + ')' } },
  el('div', { class: 'donut-hole' }, el('b', {}, total), el('span', {}, t('dash.total'))));
  return ring;
}
function legend(data) {
  return el('div', { class: 'legend', style: { flexDirection: 'column', gap: '6px' } }, data.map((d) => el('span', { style: { cursor: 'pointer' }, onclick: () => focusAndGo(d.ids || [], d.label) },
    el('i', { class: 'dot', style: { background: d.color } }), `${d.label} `, el('b', { style: { color: 'var(--color-fg-default)' } }, d.value))));
}

function hbars(rows, opt = {}) {
  const max = Math.max(1, ...rows.map((r) => r.total ?? r.value));
  return el('div', { style: { display: 'grid', gap: '7px' } }, rows.map((r) => {
    const parts = r.parts || [{ value: r.value, color: r.color || token('--viz-sel'), ids: r.ids }];
    const wrap = el('div', { class: 'bar', style: { height: '12px', width: ((r.total ?? r.value) / max * 100) + '%', display: 'flex', background: 'var(--color-bg-hover)', minWidth: '6px' } },
      parts.map((p) => el('i', { style: { width: ((p.value) / ((r.total ?? r.value) || 1) * 100) + '%', background: p.color, borderRadius: 0, cursor: 'pointer' }, title: `${p.label || ''} ${p.value}`, onclick: () => focusAndGo(p.ids || [], `${r.label} / ${p.label || ''}`) })));
    return el('div', {}, el('div', { class: 'mini', style: { display: 'flex', justifyContent: 'space-between', marginBottom: '3px' } }, el('span', {}, r.label), el('b', { style: { color: 'var(--color-fg-default)' } }, r.right ?? (r.total ?? r.value))), wrap);
  }));
}

export function mount(host) {
  const page = el('div', { class: 'page' });
  host.append(page);
  const render = () => {
    const m = store.model;
    const reqs = m.reqs;
    const by = (fn) => { const o = {}; for (const r of reqs) { const k = fn(r); (o[k] ||= []).push(r.id); } return o; };
    const stat = by((r) => r.statusKind);
    const open = m.questions.filter((q) => !/回答済み|解決済み|取り下げ|クローズ/.test(q.state));
    const blocked = reqs.filter((r) => r.blocked.length);
    const nodes = store.nodes;
    const implDone = reqs.filter((r) => nodes.get(r.id)?.impl === 'done');
    const acs = reqs.flatMap((r) => r.acs);
    const pass = m.cases.filter((c) => c.status === 'pass').length;
    const files = [...nodes.values()].filter((n) => n.type === 'file');
    const comps = [...nodes.values()].filter((n) => n.type === 'component');
    const approvedPct = reqs.length ? Math.round((stat.approved?.length || 0) / reqs.length * 1000) / 10 : 0;
    const implPct = reqs.length ? Math.round(implDone.length / reqs.length * 1000) / 10 : 0;

    const kpi = (v, label, ids, sfx = '') => {
      const vEl = el('div', { class: 'v' }, '0');
      const card = el('div', { class: 'card kpi', style: { cursor: ids ? 'pointer' : 'default' }, onclick: () => ids && focusAndGo(ids, label) }, vEl, el('div', { class: 'l' }, label));
      animateNumber(vEl, v);
      if (sfx) {
        if (document.documentElement.classList.contains('snapshot')) vEl.textContent = v + sfx;
        else setTimeout(() => (vEl.textContent = v + sfx), 1000);
      }
      return card;
    };

    const statusData = Object.entries(stat).map(([k, ids]) => ({ label: statusText(k, ''), value: ids.length, color: STATUS_COLOR[k] || STATUS_COLOR.unknown, ids }));
    const prio = by((r) => r.priority || '-');
    const prioData = Object.entries(prio).sort().map(([k, ids], i) => ({ label: k, value: ids.length, color: token(PALETTE[i % PALETTE.length]), ids }));
    const groups = {};
    for (const r of reqs) { const g = r.file.split('/').pop().replace(/\.md$/, ''); (groups[g] ||= []).push(r); }
    const groupRows = Object.entries(groups).map(([g, rs]) => {
      const d = rs.filter((r) => nodes.get(r.id)?.impl === 'done'), nn = rs.filter((r) => nodes.get(r.id)?.impl !== 'done');
      return { label: g, total: rs.length, right: `${d.length}/${rs.length}`, parts: [{ label: t('impl.done'), value: d.length, color: token('--color-status-success-icon'), ids: d.map((r) => r.id) }, { label: t('impl.none'), value: nn.length, color: token('--color-border-strong'), ids: nn.map((r) => r.id) }] };
    }).sort((a, b) => b.total - a.total);
    const levels = {};
    for (const r of reqs) for (const a of r.acs) (levels[a.level || '-'] ||= []).push(r.id);
    const levelRows = Object.entries(levels).sort((a, b) => b[1].length - a[1].length).map(([k, ids]) => ({ label: k, value: ids.length, color: token('--viz-ac'), ids: [...new Set(ids)] }));
    const goalRows = m.goals.map((g) => {
      const rs = reqs.filter((r) => r.goal === g.id), d = rs.filter((r) => nodes.get(r.id)?.impl === 'done');
      return { g, rs, d, pct: rs.length ? Math.round(d.length / rs.length * 100) : 0 };
    });
    const caseRows = Object.entries(m.cases.reduce((o, c) => ((o[c.status || '-'] = (o[c.status || '-'] || 0) + 1), o), {}));

    page.replaceChildren(
      el('h1', {}, t('dash.title')),
      el('p', { class: 'sub' }, `${m.meta.name} · `, el('span', { class: 'mono' }, m.meta.repo), ` · ${t('dash.generated')} ${m.meta.generatedAt}`),
      m.meta.error ? el('div', { class: 'warnbox' }, t('err.nodata')) : '',
      el('div', { class: 'grid kpis' },
        kpi(reqs.length, t('dash.reqs'), reqs.map((r) => r.id)),
        kpi(approvedPct, t('dash.approved') + ' %', stat.approved, '%'),
        kpi(implPct, t('dash.impl') + ' %', implDone.map((r) => r.id), '%'),
        kpi(acs.length, t('dash.acs')),
        kpi(m.cases.length ? Math.round(pass / m.cases.length * 100) : 0, t('dash.pass') + ' %', m.cases.map((c) => c.id), '%'),
        kpi(open.length, t('dash.openq'), open.map((q) => q.id)),
        kpi(blocked.length, t('dash.blocked'), blocked.map((r) => r.id)),
        kpi(files.length, t('dash.files') + ` / ${comps.length} ` + t('dash.comps'), files.map((f) => f.id))),
      el('div', { class: 'grid cols2', style: { marginTop: '16px' } },
        el('div', { class: 'card' }, cardHeading('req', t('dash.status')), el('div', { class: 'row', style: { gap: '24px', flexWrap: 'nowrap' } }, donut(statusData), legend(statusData))),
        el('div', { class: 'card' }, cardHeading('req', t('dash.priority')), el('div', { class: 'row', style: { gap: '24px', flexWrap: 'nowrap' } }, donut(prioData), legend(prioData))),
        el('div', { class: 'card' }, cardHeading('goal', t('dash.goals')),
          el('div', { style: { display: 'grid', gap: '12px' } }, goalRows.map(({ g, rs, d, pct }) => el('div', { style: { cursor: 'pointer' }, onclick: () => { store.setFocus(rs.map((r) => r.id), g.id); location.hash = '#/map2d'; } },
            el('div', { class: 'mini', style: { display: 'flex', justifyContent: 'space-between' } }, el('span', {}, el('span', { class: 'mono' }, g.id), ' ', (g.title || '').slice(0, 56)), el('b', { style: { color: 'var(--color-fg-default)' } }, `${d.length}/${rs.length}`)),
            el('div', { class: 'bar' }, el('i', { style: { width: pct + '%' } })))))),
        el('div', { class: 'card' }, cardHeading('entity', t('dash.groups')), hbars(groupRows)),
        el('div', { class: 'card' }, cardHeading('test', t('dash.levels')), hbars(levelRows)),
        el('div', { class: 'card' }, cardHeading('test', t('dash.cases')),
          caseRows.length ? el('div', { class: 'row' }, caseRows.map(([k, n]) => el('span', { class: 'badge ' + (k === 'pass' ? 'pass' : k === 'fail' ? 'fail' : '') }, `${k} ${n}`))) : el('div', { class: 'empty' }, t('none')),
          el('div', { class: 'mini', style: { marginTop: '10px' } }, m.registry.length ? m.registry.map((x) => `${x.kind}:${x.state} ${x.count}`).join(' · ') : '')),
        el('div', { class: 'card', style: { gridColumn: '1 / -1' } }, cardHeading('progress', t('dash.runs')),
          m.runs.length ? el('div', { style: { overflow: 'auto' } }, runsTable(m.runs)) : el('div', { class: 'empty' }, t('none')))));
  };
  render();
  const offs = [store.on('model', render), onLang(render)];
  return { destroy() { offs.forEach((f) => f()); } };
}

function cardHeading(kind, label) {
  return el('h3', { class: 'card-heading' }, businessIcon(kind, label), el('span', {}, label));
}

function runsTable(runs) {
  const keys = Object.keys(runs[0]).filter((k) => !k.startsWith('_')).slice(0, 7);
  return el('table', { class: 't' }, el('thead', {}, el('tr', {}, keys.map((k) => el('th', {}, k)))),
    el('tbody', {}, runs.slice(-8).reverse().map((r) => el('tr', {}, keys.map((k) => el('td', {}, el('div', { class: 'clamp' }, (r[k] || '').slice(0, 160))))))));
}
