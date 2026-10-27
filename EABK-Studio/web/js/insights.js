// FR-1002/1003/1005/1006: decision-oriented views derived only from the loaded model.
import { store } from './store.js';
import { t, onLang } from './i18n.js';
import { el, vscodeUrl } from './ui.js';
import { xrefLink } from './xref.js';
import { placeRows, listTiers } from './tierlist.js';

// A block built from the dictionary is rebuilt in place when the language changes (the screen is not reloaded).
function live(build) {
  let node = build();
  const off = onLang(() => {
    if (!node.isConnected) { off(); return; }
    const next = build();
    node.replaceWith(next);
    node = next;
  });
  return node;
}

export function evidenceTarget(record) {
  return record.file && record.line
    ? { label: `${record.file}:${record.line}`, href: vscodeUrl(record.file, record.line) }
    : { label: t('ins.noloc'), href: '' };
}

// The screens that carry a role-by-role analysis; their words are the dictionary keys ins.page.<route>.n / i / p / d.
const PAGE = { dashboard: 1, map2d: 1, map3d: 1, diagrams: 1, placement: 1, source: 1, tables: 1 };

export function analysis(route) {
  return live(() => {
    const name = t(`ins.page.${route}.n`), info = t(`ins.page.${route}.i`);
    const perspective = t(`ins.page.${route}.p`), decision = t(`ins.page.${route}.d`);
    const roles = ['pm', 'arch', 'swe'].map((id) => [t('persona.' + id), t('ins.role.info', { v: info }), t(`ins.role.${id}.p`, { v: perspective }), t(`ins.role.${id}.d`, { v: decision })]);
    return el('section', { class: 'analysis card', role: 'region', 'aria-label': t('ins.analysis', { name }) },
      el('div', { class: 'analysis-title' }, el('b', {}, t('ins.analysis', { name })), el('span', {}, t('ins.roleread'))),
      el('div', { class: 'analysis-grid' }, roles.map(([role, a, b, c]) =>
        el('article', {}, el('h2', {}, role),
          el('p', {}, el('b', {}, t('ins.l.info')), a),
          el('p', {}, el('b', {}, t('ins.l.persp')), b),
          el('p', {}, el('b', {}, t('ins.l.decide')), c)))));
  });
}

export function decorate(route, host) {
  const page = host.querySelector('.page');
  if (route in PAGE) (page || host).prepend(analysis(route));
  if (route === 'dashboard' && page) page.append(historyProgress());
  if (route === 'placement' && new URLSearchParams(location.hash.split('?')[1] || '').get('kind') === 'runtime') {
    host.replaceChildren(el('div', { class: 'page' }, analysis('placement'), runtimePlacement()));
  }
  if (route === 'diagrams' && new URLSearchParams(location.hash.split('?')[1] || '').get('kind') === 'er') {
    host.replaceChildren(el('div', { class: 'page' }, analysis('diagrams'), entityER()));
  }
}

export function runtimePlacement() {
  return live(() => {
    const runtime = store.model.analysis.runtime;
    const box = (item) => el('article', { class: 'runtime-node card' },
      el('h3', {}, item.name), el('p', {}, t('ins.runsAt', { v: item.runsAt })),
      el('p', {}, t('ins.dataAt', { v: item.data })),
      item.access ? el('p', {}, t('ins.access', { v: item.access })) : null,
      el('p', { class: 'mini mono' }, t('ins.source', { v: item.source })));
    const miss = t('ins.unwritten');
    return el('section', { class: 'visual-section' }, el('h1', {}, t('ins.rt.title')),
      el('p', { class: 'sub' }, t('ins.rt.sub')),
      el('div', { class: 'runtime-flow' }, runtime.components.map(box)),
      el('div', { class: 'tw' }, el('table', { class: 't' },
        el('thead', {}, el('tr', {}, [t('ins.from'), t('ins.to'), t('ins.dir'), t('ins.data'), t('ins.ev')].map((x) => el('th', {}, x)))),
        el('tbody', {}, runtime.flows.map((flow) => el('tr', {},
          el('td', {}, flow.from), el('td', {}, flow.to), el('td', {}, flow.direction),
          el('td', {}, flow.data), el('td', { class: 'mono' }, flow.source)))))),
      el('div', { class: 'card boundary' }, el('h3', {}, t('ins.boundary')),
        runtime.boundaries.length
          ? runtime.boundaries.map((x) => el('p', {},
            el('b', {}, x.name), t('ins.bline', { method: x.method || miss, dir: x.direction || miss, owner: x.owner || miss }),
            el('span', { class: 'mono' }, ' / ' + t('ins.source', { v: x.source }))))
          : el('p', {}, t('common.none')),
        el('p', {}, t('ins.rtfoot', { v: runtime.externalSend.length ? t('ins.defined') : t('common.none') }))));
  });
}

// FR-1006 AC-050 / FR-1013 AC-084 AC-085: one ER view shared by the ER page and the diagrams "data relation" tab.
// Entities and their related tables (tables sharing a requirement) carry data-id = model node id.
export function entityER() {
  return live(buildEntityER);
}
function buildEntityER() {
  const reqs = store.model.reqs.filter((r) => r.entities.length);
  const related = reqs.filter((r) => r.relation);
  const entities = [...new Set(reqs.flatMap((r) => r.entities))];
  const entNode = (name) => [...store.nodes.values()].find((n) => n.type === 'entity' && (n.label === name || n.id === 'ent:' + name));
  const tablesOf = (name) => {
    const m = new Map();
    for (const r of reqs.filter((x) => x.entities.includes(name))) for (const a of store.neighbors(r.id, ['table'])) { if (!m.has(a.id)) m.set(a.id, []); m.get(a.id).push(r.id); }
    return m;
  };
  const pick = (id) => () => store.select(id, { fly: true });
  const key = (id) => (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); store.select(id, { fly: true }); } };
  const box = (name) => {
    const n = entNode(name), tbls = tablesOf(name);
    const head = el('b', {}, name);
    const attrs = n ? { 'data-id': n.id, tabindex: 0, role: 'button', onclick: pick(n.id), onkeydown: key(n.id) } : {};
    return el('div', { class: 'entity-box', ...attrs }, head,
      el('div', { class: 'mini' }, t('er.tables') + ': ', tbls.size ? [...tbls.entries()].map(([id, rs]) => el('span', { class: 'chip', 'data-id': id, tabindex: 0, role: 'button', title: `${t('er.evidence')}: ${rs.join(', ')}`, onclick: (e) => { e.stopPropagation(); pick(id)(); }, onkeydown: (e) => { e.stopPropagation(); key(id)(e); } }, `▦ ${store.node(id)?.label || id} (${rs.join(', ')}) `)) : t('er.notable')));
  };
  return el('section', { class: 'visual-section' }, el('h1', {}, t('er.title')),
    entities.length ? el('div', { class: 'er-grid' }, entities.map(box)) : el('div', { class: 'empty' }, t('er.noent')),
    related.map((r) => el('div', { class: 'relation-row' }, el('b', {}, r.id), ` ${t('er.evidence')}: ${r.relation}`)),
    reqs.filter((r) => !r.relation).map((r) => el('div', { class: 'warnbox' }, `${r.entities.join(t('ins.sep'))}: ${t('er.norelwarn', { id: r.id })} [${t('er.norel')}]`)));
}

function historyProgress() {
  return live(buildHistory);
}
function buildHistory() {
  const m = store.model;
  const pass = m.cases.filter((c) => c.status === 'pass').length;
  const recordLabel = (record) => record.id || record['run-id'] || record.target || record.name || record.label || 'record';
  const sourceLink = (record) => {
    const target = evidenceTarget(record);
    return target.href
    ? el('a', {
      class: 'mono',
      href: target.href,
      title: t('ins.ev.open', { cat: record.category, status: record.status }),
    }, target.label)
    : el('span', { class: 'mono' }, target.label);
  };
  const evidence = (title, groups) => {
    const count = groups.reduce((n, group) => n + group.records.length, 0);
    const open = () => {
      const drawer = document.getElementById('drawer');
      drawer.hidden = true;
      drawer.style.left = '8px';
      drawer.style.right = 'auto';
      drawer.style.width = 'min(440px, 35vw)';
      drawer.replaceChildren(el('h2', {}, t('ins.ev.title', { title })),
        ...groups.map((group) => el('section', {},
          el('h3', {}, `${group.label} (${group.records.length})`),
          group.records.length
            ? el('ul', {}, group.records.map((record) => el('li', {},
              el('b', {}, recordLabel(record)),
              record.date ? t('ins.ev.date', { v: record.date }) : t('ins.ev.nodate'),
              record.status ? t('ins.ev.state', { v: record.status }) : '',
              t('ins.ev.src'), sourceLink(record))))
            : el('p', { class: 'empty' }, t('ins.ev.none')))),
        el('button', { class: 'btn', onclick: () => (drawer.hidden = true) }, t('ins.close')));
      drawer.hidden = false;
    };
    return el('figure', { class: 'card evidence-chart', 'aria-label': title },
      el('figcaption', {}, title),
      el('button', { role: 'button', class: 'chart-button', onclick: open },
        t('ins.ev.btn', { groups: groups.length, count })),
      el('div', { class: 'dimension-list' }, groups.map((group) =>
        el('span', { class: 'badge' }, `${group.label}: ${group.records.length}`))));
  };
  const by = (records, key) => Object.entries(records.reduce((out, record) => {
    const label = key(record) || t('tier.n.unclassified');
    (out[label] ||= []).push(record);
    return out;
  }, {})).map(([label, records]) => ({ label, records }));
  const goalGroups = by(m.reqs, (r) => r.goal);
  const typeGroups = by([...store.nodes.values()], (n) => n.type);
  const historyGroups = Object.entries((m.analysis.history || []).reduce((out, record) => {
    ((out[record.category] ||= {})[record.status] ||= []).push(record);
    return out;
  }, {})).map(([label, states]) => ({
    label,
    groups: Object.entries(states).map(([status, records]) => ({ label: status, records })),
  }));
  // FR-1032 / FR-1031: record chips wrap inside their box; each chip's ID is a link.
  // i18n-data: the category names of the history records are managed-data values (shown as written)
  const KIND = { 決定記録: 'decision', 実行履歴: 'run', 要求状態: 'requirement', 実装登録: 'impl' };
  const chipBoxes = Object.entries(KIND).map(([label, kind]) => {
    const records = (m.analysis.history || []).filter((r) => r.category === label);
    const chip = (r) => {
      const id = String(r.id || '');
      const link = store.nodes.has(id) ? xrefLink(id)
        : (() => { const tg = evidenceTarget(r); return tg.href ? el('a', { class: 'mono xref', href: tg.href, title: `${label} ${id}` }, id || tg.label) : el('span', { class: 'mono' }, id || '-'); })();
      return el('span', { class: 'hchip', 'data-testid': 'history-chip', 'data-kind': kind }, link, r.status ? el('span', { class: 'hstatus' }, ` ${r.status}`) : '');
    };
    return el('section', { class: 'card history-box', 'data-testid': 'history-box', 'data-kind': kind, 'aria-label': `${label} ${records.length}` },
      el('h3', {}, `${label} (${records.length})`),
      records.length ? el('div', { class: 'hchips' }, records.map(chip))
        : el('p', { class: 'empty', 'data-testid': 'history-empty' }, t('none')));
  });
  return el('section', { class: 'visual-section' }, el('h2', {}, t('ins.hist.title')),
    el('p', { class: 'sub' }, t('ins.hist.asof', { v: m.meta.generatedAt })),
    el('div', { class: 'progress-summary' }, el('span', {}, t('ins.hist.pass')),
      el('strong', { 'data-testid': 'system-test-pass-count' }, String(pass)),
      el('span', {}, t('ins.hist.of', { n: m.cases.length }))),
    el('div', { class: 'grid cols2 history-grid' }, ...chipBoxes),
    el('div', { class: 'grid cols2 history-grid' },
      ...historyGroups.map((category) => evidence(category.label, category.groups)),
      evidence(t('tier.n.goals'), goalGroups),
      evidence(t('ins.hist.types'), typeGroups)));
}

// FR-1063 AC-349: 表の行を上位層（種類→区分→領域）の見出しの下にまとめる。leaf の領域ごとに同じ見出しの表を置く。
function tierTable(headers, placed, rowOf, emptyPath) {
  return listTiers(placed, {
    openAreas: true,
    empty: placed.length ? undefined : [emptyPath],
    extra: (node) => (node.level === 'area' && node.items.length
      ? el('div', { class: 'tw' }, el('table', { class: 't' }, el('thead', {}, el('tr', {}, headers.map((x) => el('th', {}, x)))), el('tbody', {}, node.items.map((it) => rowOf(it.row)))))
      : null),
  });
}

// i18n-data: the names of the hierarchy (kind, division, area) are managed-data values; they are translated by hier.js (tierName)
const EMPTY_REQ_PATH = ['要求', '機能', '未分類'];

export function mountStructure(host) {
  const page = live(() => {
    const analysis = store.model.analysis.structure;
    // i18n-data: the kind name of a hierarchy item is a managed-data value
    const placed = placeRows(analysis.differences.map((d) => d), (d) => ({ kind: '要求', id: d.target }), (d) => [t('ins.st.diff'), t('ins.st.kind', { v: d.kind }), t('ins.st.layer', { v: d.layer })]);
    return el('div', { class: 'page' }, el('h1', {}, t('ins.st.title')),
      el('p', { class: 'sub' }, t('ins.st.sub')),
      el('div', { class: 'grid cols2 layer-list' }, analysis.layers.map((layer) =>
        el('article', { class: 'card' }, el('h2', {}, layer.name),
          el('p', {}, t('ins.st.actual', { v: layer.actual })), el('p', {}, t('ins.st.ideal', { v: layer.ideal })),
          el('p', {}, t('ins.st.delta', { v: layer.delta })), el('p', {}, t('ins.st.rule', { v: layer.rule })),
          el('p', {}, t('ins.st.reason', { v: layer.reason })),
          el('p', { class: 'mini mono' }, t('ins.source', { v: layer.source }))))),
      tierTable(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'h7', 'h8'].map((k) => t('ins.st.' + k)), placed,
        (diff) => el('tr', {},
          el('td', {}, diff.layer), el('td', {}, diff.kind), el('td', {}, diff.target),
          el('td', {}, diff.actual), el('td', {}, diff.ideal), el('td', {}, diff.rule),
          el('td', {}, diff.reason), el('td', { class: 'mono' }, diff.source)), [t('ins.st.diff'), t('tier.n.unclassified'), t('tier.n.unclassified')]));
  });
  host.append(page);
  return { destroy() {} };
}

export function mountConsistency(host) {
  const page = live(() => {
    const rows = new Map();
    for (const r of store.model.reqs) rows.set(r.id, { id: r.id, req: true, ac: r.acs.length > 0, test: false, cat: false, file: false });
    for (const f of store.model.catalog.features) {
      const row = rows.get(f.req) || { id: f.req, req: false, ac: false, test: false, cat: false, file: false };
      row.cat = true; row.file = (f.impl || []).length > 0; rows.set(f.req, row);
    }
    for (const c of store.model.cases) for (const id of c.requirement_ids || []) if (rows.has(id)) rows.get(id).test = true;
    const outcome = (r) => !r.req ? t('ins.co.noref') : [r.req, r.ac, r.test, r.cat, r.file].every(Boolean) ? t('ins.co.ok') : t('ins.co.missing');
    // i18n-data: the kind name of a hierarchy item is a managed-data value
    const placed = placeRows([...rows.values()], (r) => ({ kind: '要求', id: r.id }), '要求');
    return el('div', { class: 'page' }, el('h1', {}, t('ins.co.title')),
      tierTable(['ID', t('ins.co.h.verdict'), t('ins.co.req'), 'AC', t('ins.co.test'), t('ins.co.cat'), t('ins.co.file')], placed,
        (r) => el('tr', {},
          el('td', {}, r.id), el('td', {}, outcome(r)),
          ...[['req', t('ins.co.req')], ['ac', 'AC'], ['test', t('ins.co.test')], ['cat', t('ins.co.cat')], ['file', t('ins.co.file')]]
            .map(([k, label]) => el('td', {}, `${label} ${r[k] ? '✓' : '—'}`))), EMPTY_REQ_PATH));
  });
  host.append(page);
  return { destroy() {} };
}

export function mountMaintenance(host) {
    const reqs = new Map(store.model.reqs.map((r) => [r.id, r]));
    const featureCounts = store.model.catalog.features.reduce((counts, feature) => {
      counts.set(feature.req, (counts.get(feature.req) || 0) + 1);
      return counts;
    }, new Map());
    let page;
    const build = () => {
    const pg = el('div', { class: 'page' },
      el('h1', {}, t('nav.maintenance')),
      el('p', { class: 'sub' }, t('ins.mt.sub')),
      el('div', { class: 'warnbox' }, t('ins.mt.warn')));
    const list = el('div', { class: 'maintenance-list' });
    const candidates = [];
    for (const feature of store.model.catalog.features) {
      const req = reqs.get(feature.req);
      const mismatch = !req || feature.title !== req.title || feature.status !== req.status;
      if (!mismatch) continue;
      candidates.push(el('button', { class: 'maintenance-item', 'data-req': feature.req, onclick: () => preview(feature.req) },
        el('b', {}, feature.req),
        el('span', {}, req ? `${feature.title} → ${req.title}` : t('ins.mt.noref')),
        el('span', {}, req ? `${feature.status} → ${req.status}` : t('ins.mt.e.unsupported'))));
    }
    // FR-1063 AC-349: 保守候補を上位層（種類→区分→領域）の見出しの下にまとめる。要求正本にない参照先は「未分類」。
    // i18n-data: the kind name of a hierarchy item is a managed-data value
    const placed = placeRows(candidates, (b) => ({ kind: '要求', id: b.dataset.req }), '要求');
    list.append(listTiers(placed, {
      openAreas: true,
      empty: placed.length ? undefined : [EMPTY_REQ_PATH],
      itemNode: (it) => it.row,
    }));
    if (!candidates.length) list.append(el('p', { class: 'empty' }, t('ins.mt.empty')));
    pg.append(list);
    return pg;
    };
    page = build();
    host.append(page);
    // the language changes: the page is rebuilt in place (an open preview is closed; nothing has been applied yet)
    const offLang = onLang(() => { document.querySelector('.maintenance-modal')?.remove(); const next = build(); page.replaceWith(next); page = next; });

    const ERR_KEY = { unsupported: 'unsupported', 'invalid-input': 'invalid', 'preview-conflict': 'conflict', 'write-error': 'write', 'outside-preview': 'outside', 'verify-failure': 'verify' };
    const errorText = (code) => (ERR_KEY[code] ? t('ins.mt.e.' + ERR_KEY[code]) : '');
    const request = async (path, body) => {
      const response = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-EABK-Studio': '1' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw data;
      return data;
    };
    const showError = (failure, retry) => {
      document.querySelector('.maintenance-modal')?.remove();
      const alert = el('div', { class: 'card maintenance-result', role: 'alert' },
        el('b', {}, errorText(failure.error) || failure.error || t('ins.mt.err')),
        el('p', {}, failure.detail || ''),
        el('p', {}, t('ins.mt.restored')),
        el('div', { class: 'row' },
          el('button', { class: 'btn', onclick: retry }, t('ins.mt.retry')),
          el('button', { class: 'btn ghost', onclick: () => alert.remove() }, t('ins.mt.cancel'))));
      page.prepend(alert);
    };
    const preview = async (id) => {
      if (!reqs.has(id)) {
        showError({ error: 'unsupported', detail: t('ins.mt.d.req') }, () => preview(id));
        return;
      }
      if (featureCounts.get(id) !== 1) {
        showError({ error: 'invalid-input', detail: t('ins.mt.d.input') }, () => preview(id));
        return;
      }
      const card = el('div', { class: 'card' },
        el('h2', {}, t('ins.mt.pv')),
        el('p', {}, t('ins.mt.loading', { id })),
        el('button', { class: 'btn ghost', onclick: () => modal.remove() }, t('ins.mt.cancel')));
      const modal = el('div', { class: 'modal maintenance-modal', role: 'dialog', 'aria-label': t('ins.mt.pv') }, card);
      document.body.append(modal);
      try {
        const data = await request('/api/maintenance/preview', { id });
        card.replaceChildren(
            el('h2', {}, t('ins.mt.pv')),
            el('p', {}, `${data.path} — ${data.id}`),
            ...data.changes.map((change) => el('p', {}, `${change.column}: ${change.before} → ${change.after}`)),
            el('p', { class: 'mono' }, data.verify),
            el('div', { class: 'row' },
              el('button', { class: 'btn', onclick: async () => {
                try {
                  const result = await request('/api/maintenance/apply', { token: data.token });
                  modal.remove();
                  const status = el('div', { class: 'card maintenance-result', role: 'status' },
                    `exit ${result.exit}: ${result.message} — ${result.path}`);
                  page.prepend(status);
                } catch (failure) {
                  showError(failure, () => preview(id));
                }
              } }, t('ins.mt.apply')),
              el('button', { class: 'btn ghost', onclick: () => modal.remove() }, t('ins.mt.cancel'))));
      } catch (failure) {
        showError(failure, () => preview(id));
      }
    };
  return { destroy() { offLang(); document.querySelector('.maintenance-modal')?.remove(); } };
}
