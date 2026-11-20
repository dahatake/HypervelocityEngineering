// FR-1095: the release judgment — the view "Release decision" of the implementation-status item (FR-1041's nine items
// stay nine). Everything shown comes from model.release, which the server derives from the goals, the approved
// requirements, the ledger and the question sheet (HVE-Studio/release.py).
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, icon } from './ui.js';
import { xrefLink } from './xref.js';
import { releaseBadge } from './steps.js';
import { listTiers, hierarchy } from './tierlist.js';

const VERDICT_ICON = { met: 'success', unmet: 'warning', undetermined: 'info', none: 'info' };

function idLink(id) {
  return store.nodes.has(id) ? xrefLink(id, id) : el('span', { class: 'mono' }, id);
}

export function implTabs(active) {
  const tab = (id, href) => el('a', { role: 'tab', href, class: 'src-tab' + (active === id ? ' on' : ''), 'aria-selected': String(active === id), 'data-testid': 'impl-tab-' + id }, t('rel.tab.' + id));
  return el('nav', { class: 'src-tabs', role: 'tablist', 'aria-label': t('rel.tabs') }, tab('impl', '#/implstatus'), tab('release', '#/release'));
}

function reasonText(r) {
  const base = t('rel.reason.' + r.code, { goal: r.goal || '', detail: r.detail || '' });
  return r.repo ? `${r.repo}: ${base}` : base;
}

function render(page) {
  const rel = store.model?.release || { state: 'unknown', reasons: [{ code: 'pending' }], goals: [], items: [] };
  const fmt = (s) => s || t('rel.none');
  const head = el('section', { class: 'card release-head', 'data-testid': 'release-state', 'data-state': rel.state, role: 'region', 'aria-label': t('rel.title') },
    el('div', { class: 'release-big' }, releaseBadge(rel), el('p', {}, t('rel.state.' + rel.state + '.d'))),
    rel.reasons.length ? el('ul', { class: 'release-reasons', 'data-testid': 'release-reasons' }, rel.reasons.map((r) => el('li', {}, reasonText(r)))) : null,
    el('p', { class: 'mini' }, t('rel.times', { ledger: fmt(rel.ledgerRunAt), model: fmt(rel.modelAt) })),
    el('p', { class: 'mini' }, t('rel.approvals', { n: rel.approvalRequests || 0 })));
  const repos = rel.repos && rel.repos.length > 1
    ? el('section', { class: 'card', 'data-testid': 'release-repos' }, el('h2', {}, t('rel.repos')),
      el('ul', {}, rel.repos.map((r) => el('li', { 'data-repo': r.name }, el('b', {}, r.name), ' ', releaseBadge(r), ' ', t('rel.items.n', { n: r.items })))))
    : null;
  const goals = el('section', { class: 'card', 'data-testid': 'release-goals' }, el('h2', {}, t('rel.goals')),
    rel.goals.length
      ? el('div', { class: 'tw' }, el('table', { class: 't' },
        el('thead', {}, el('tr', {}, [t('col.id'), t('col.title'), t('rel.verdict'), t('rel.cases')].map((h) => el('th', {}, h)))),
        el('tbody', {}, rel.goals.map((g) => el('tr', { 'data-goal': g.id, 'data-verdict': g.verdict },
          el('td', { class: 'mono' }, idLink(g.id)), el('td', {}, g.title),
          el('td', {}, el('span', { class: 'verdict v-' + g.verdict }, icon(VERDICT_ICON[g.verdict], { size: 16 }), t('rel.verdict.' + g.verdict))),
          el('td', { class: 'mini' }, Object.entries(g.counts).map(([k, v]) => `${k} ${v}`).join(' · ') || '0'))))))
      : el('p', {}, t('rel.nogoals')));
  const items = el('section', { class: 'card', 'data-testid': 'release-items' }, el('h2', {}, t('rel.items', { n: rel.items.length })),
    rel.items.length
      ? el('ol', { class: 'release-items' }, rel.items.map((it) => el('li', { 'data-kind': it.kind, 'data-id': it.id },
        el('span', { class: 'chip' }, t('rel.kind.' + it.kind)), ' ', idLink(it.id), ' ', el('span', {}, it.title),
        it.refs?.length ? el('span', { class: 'mini' }, ' (', ...it.refs.flatMap((r, i) => [i ? ', ' : '', idLink(r)]), ')') : null)))
      : el('p', { 'data-testid': 'release-items-empty' }, t('rel.items.none')));
  // FR-1063: like every screen, the release view also shows the requirements' upper tiers (FR-1062) with counts
  const tiers = el('section', { class: 'card', 'data-testid': 'release-tiers' }, el('h2', {}, t('dash.tiers')), el('p', { class: 'mini' }, t('dash.tiers.sub')),
    listTiers(hierarchy().items, {
      itemNode: (it) => el('div', { class: 'tier-item', role: 'treeitem', 'data-testid': 'tier-item', 'data-id': it.id },
        store.nodes.has(it.id) ? xrefLink(it.id, it.id) : el('span', { class: 'mono' }, it.id), it.title ? el('span', { class: 'tier-item-title' }, ` ${it.title}`) : null),
    }));
  page.replaceChildren(...[implTabs('release'), el('h1', {}, t('rel.title')), el('p', { class: 'sub' }, t('rel.sub')), head, repos, goals, items, tiers].filter(Boolean));
}

export function mount(host) {
  const page = el('div', { class: 'page release-page' });
  host.append(page);
  render(page);
  const offModel = store.on('model', () => render(page));
  const offLang = onLang(() => render(page));
  return { destroy() { offModel(); offLang(); } };
}
