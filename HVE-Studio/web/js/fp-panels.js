// FR-1092: the chrome around the board — header buttons, search, the side panel, Health, Recent work, Screens, Flows,
// the question box, zoom buttons, menus. Everything it shows comes from the map data; nothing is sent anywhere.
import { chain, describe as describeItem, membersOf } from './fp-data.js';

const KIND_LABEL = { ui: 'ui', service: 'service', worker: 'worker', library: 'library', feature: 'feature', data: 'data', config: 'config', test: 'test', script: 'script', infra: 'infra', external: 'external' };
const SYSTEM_GROUPS = [['ui', 'fp.group.ui'], ['service', 'fp.group.service'], ['worker', 'fp.group.worker'], ['external', 'fp.group.external'], ['library', 'fp.group.library'], ['test', 'fp.group.test'], ['script', 'fp.group.script']];

export function mountPanels(ctx, { headerEl, panelEl, stageWrap }) {
  const { S, t, el, icon } = ctx;
  let menu = null, pop = null, modal = null, searchBox = null, askBox = null, results = null;

  const fmt = (n) => Number(n || 0).toLocaleString();
  const openCount = () => S.g.health.issues.filter((i) => !S.dismissed.has(i.id) && i.severity !== 'low').length;
  const recentCount = () => (S.g.recent.tasks || []).reduce((n, x) => n + x.items.length, 0);
  const btn = (cls, text, onclick, extra = {}) => el('button', { type: 'button', class: cls, onclick, ...extra }, text);

  // ------------------------------------------------------------ closing things
  function closeMenus() { menu?.remove(); menu = null; pop?.remove(); pop = null; results?.replaceChildren(); }
  function closeModal() { modal?.remove(); modal = null; }
  function closeOverlays() { const any = !!(menu || pop || modal || results?.childElementCount); closeMenus(); closeModal(); return any; }

  // ------------------------------------------------------------ search
  function searchAll(q) {
    const tk = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!tk.length) return [];
    const hit = (text) => tk.every((w) => text.includes(w));
    const out = [];
    for (const [id, n] of S.m.nodes) if (hit([n.label, n.id, n.summary].join(' ').toLowerCase())) out.push({ id, label: n.label, sub: t('fp.type.' + (KIND_LABEL[n.kind] || 'library')), rank: 0 });
    for (const s of S.g.screens) if (hit([s.name, s.url, s.description].join(' ').toLowerCase())) out.push({ id: s.id, label: s.name, sub: t('fp.screen') + ' · ' + s.url, rank: 1, screen: s });
    for (const [id, f] of S.m.files) if (hit([f.name, f.p, f.d].join(' ').toLowerCase())) out.push({ id, label: f.name, sub: f.p, rank: 2 });
    for (const [id, r] of S.m.routes) if (hit([r.name, r.m, r.p, r.d].join(' ').toLowerCase())) out.push({ id, label: `${r.m} ${r.p}`, sub: r.name, rank: 3 });
    return out.sort((a, b) => a.rank - b.rank).slice(0, 12);
  }
  function renderResults() {
    const list = searchAll(searchBox.value);
    results.replaceChildren(...list.map((h) => el('button', { type: 'button', class: 'fp-hit', 'data-testid': 'fp-hit', onclick: () => { closeMenus(); searchBox.value = ''; h.screen ? showScreen(h.screen) : ctx.reveal(h.id); } },
      el('span', { class: 'fp-hit-t' }, h.label), el('small', { class: 'mini' }, h.sub))));
  }

  // ------------------------------------------------------------ header
  function header() {
    const g = S.g, nOpen = openCount(), nRecent = recentCount();
    const atTop = !S.view && !S.answer;
    searchBox ||= el('input', { type: 'search', 'data-testid': 'fp-search', placeholder: t('fp.search'), 'aria-label': t('fp.search'), autocomplete: 'off', oninput: renderResults,
      onkeydown: (e) => { if (e.key === 'Enter') { const first = results.querySelector('.fp-hit'); first?.click(); } } });
    searchBox.placeholder = t('fp.search'); searchBox.setAttribute('aria-label', t('fp.search'));
    if (askBox) { askBox.placeholder = t('fp.ask.ph'); askBox.setAttribute('aria-label', t('fp.ask.ph')); }
    results ||= el('div', { class: 'fp-results', role: 'listbox' });
    headerEl.replaceChildren(
      el('div', { class: 'fp-brand' }, icon('codebase', 20), el('b', {}, g.project.name),
        atTop ? '' : btn('fp-iconbtn', '←', () => ctx.up(), { 'data-testid': 'fp-back', title: t('fp.up'), 'aria-label': t('fp.up') }),
        g.meta.authored ? el('span', { class: 'fp-live mini', title: t('fp.authored') }, t('fp.authored.short')) : ''),
      el('div', { class: 'fp-search' }, searchBox, el('span', { class: 'fp-kbd' }, '/'), results),
      el('div', { class: 'fp-actions' },
        btn('fp-act', [icon('config', 15), t('fp.health'), nOpen ? el('span', { class: 'fp-badge bad' }, String(nOpen)) : ''], openHealth, { 'data-testid': 'fp-health' }),
        btn('fp-act', [icon('worker', 15), t('fp.recent'), nRecent ? el('span', { class: 'fp-badge ok' }, String(nRecent)) : ''], openRecent, { 'data-testid': 'fp-recent' }),
        btn('fp-act', [icon('ui', 15), t('fp.screens')], openScreens, { 'data-testid': 'fp-screens' }),
        btn('fp-act', [icon('feature', 15), t('fp.tour')], () => g.tour.length && ctx.startFlow({ title: t('fp.tour'), steps: g.tour }, 'tour'), { 'data-testid': 'fp-tour', disabled: g.tour.length ? null : true }),
        btn('fp-act', [icon('route', 15), t('fp.flows')], openFlows, { 'data-testid': 'fp-flows' }),
        btn('fp-iconbtn', icon('config', 16), openFilters, { 'data-testid': 'fp-filters', title: t('fp.filters'), 'aria-label': t('fp.filters') }),
        btn('fp-iconbtn', icon('file', 16), () => ctx.togglePanel(), { 'data-testid': 'fp-panel-toggle', title: t('fp.panel'), 'aria-label': t('fp.panel') })));
    if (pop) headerEl.append(pop);       // the filter menu stays open while a switch redraws the board
  }

  // ------------------------------------------------------------ side panel
  const tile = (n, label) => el('div', { class: 'fp-tile' }, el('b', {}, fmt(n)), el('span', {}, label));
  const section = (title, count, body) => el('section', { class: 'fp-sec' }, el('h3', {}, title, count != null ? el('span', { class: 'mini' }, ' ' + count) : ''), body);
  const rowBtn = (id, extra) => {
    const d = describeItem(S.m, id, t);
    return el('button', { type: 'button', class: 'fp-row', 'data-testid': 'fp-link', onclick: () => ctx.reveal(id) }, icon(d.icon, 14), el('span', { class: 'fp-row-t' }, S.technical ? d.dev : d.title), extra ? el('small', { class: 'mini' }, extra) : '');
  };
  function neighbours(id) {
    const view = ctx.viewOf(id), data = ctx.boardOf(S.m, view, S.kinds), used = new Map(), uses = new Map();
    for (const e of data.edges) { if (e.b === id) used.set(e.a, (used.get(e.a) || 0) + e.w); if (e.a === id) uses.set(e.b, (uses.get(e.b) || 0) + e.w); }
    return { used: [...used].sort((a, b) => b[1] - a[1]), uses: [...uses].sort((a, b) => b[1] - a[1]) };
  }
  function panel() {
    if (S.answer) return answerPanel();
    const id = S.sel || S.view;
    if (!id) return overviewPanel();
    const d = describeItem(S.m, id, t), g = S.g;
    const kids = id.startsWith('n:') || id.startsWith('d:') || id.startsWith('f:') ? membersOf(S.m, id) : [];
    const node = S.m.nodes.get(id), file = S.m.files.get(id), route = S.m.routes.get(id);
    const stats = node ? node.stats : file ? { files: 1, loc: file.loc, endpoints: (S.m.routeOf.get(id) || []).length } : id.startsWith('d:') ? { files: ctx.folderFiles(S.m, id).length, loc: 0, endpoints: 0 } : null;
    const nb = id.startsWith('s:') || id.startsWith('r:') ? neighbours(id) : neighbours(id);
    const rec = S.m.recent.get(id);
    const eps = (node || id.startsWith('d:') ? ctx.allFiles(S.m, id).flatMap((f) => S.m.routeOf.get(f) || []) : id.startsWith('f:') ? S.m.routeOf.get(id) || [] : []);
    panelEl.replaceChildren(
      el('div', { class: 'fp-kind' }, icon(d.icon, 16), el('span', {}, d.type === 'node' ? t('fp.type.' + (KIND_LABEL[d.kind] || 'library')) : t('fp.type.' + d.type))),
      el('h2', { 'data-testid': 'fp-name' }, S.technical ? d.dev : d.title),
      route ? el('div', { class: 'fp-route mono' }, el('b', {}, route.m), ' ', route.p) : '',
      d.desc ? el('p', { class: 'fp-lead' }, d.desc) : '',
      d.path ? el('div', { class: 'fp-path mono' }, el('span', {}, d.path), btn('fp-iconbtn', icon('file', 14), () => ctx.copy(d.path), { title: t('fp.copy.path'), 'aria-label': t('fp.copy.path') })) : '',
      d.note ? el('div', { class: 'fp-note' }, el('span', { class: 'fp-dot' }), d.note) : '',
      rec ? el('div', { class: 'fp-recent-note' }, el('b', {}, t(rec.change === 'new' ? 'fp.tag.new' : 'fp.tag.changed')), ' ', rec.task.title || t('fp.recent.uncommitted')) : '',
      stats ? el('div', { class: 'fp-tiles' }, tile(stats.files, t('fp.stat.files')), tile(stats.loc, t('fp.stat.lines')), tile(stats.endpoints, t('fp.stat.endpoints'))) : '',
      el('div', { class: 'row fp-buttons' },
        (id.startsWith('n:') || id.startsWith('d:') || id.startsWith('f:')) && S.sel ? btn('btn', t('fp.open'), () => ctx.openItem(id), { 'data-testid': 'fp-open' }) : '',
        d.path && !id.startsWith('n:') && !id.startsWith('d:') ? el('a', { class: 'btn ghost', href: ctx.editorUrl(d.path, d.line), 'data-testid': 'fp-editor' }, t('fp.editor')) : '',
        btn('btn ghost', t('fp.ask.this'), () => { askBox.value = t('fp.ask.template', { name: d.title }); askBox.focus(); })),
      kids.length && !id.startsWith('f:') ? section(t('fp.inside.h'), kids.length, el('div', { class: 'fp-list' }, ...kids.slice(0, 40).map((k) => rowBtn(k, kidMeta(k))))) : '',
      kids.length && id.startsWith('f:') ? section(t('fp.inside.h'), kids.length, el('div', { class: 'fp-list' }, ...kids.slice(0, 40).map((k) => rowBtn(k)))) : '',
      eps.length && !id.startsWith('f:') ? section(t('fp.endpoints'), eps.length, el('div', { class: 'fp-list' }, ...eps.slice(0, 30).map((r) => rowBtn(r, S.m.routes.get(r).p)))) : '',
      section(t('fp.usedby.h'), nb.used.length, nb.used.length ? el('div', { class: 'fp-list' }, ...nb.used.slice(0, 30).map(([x, w]) => rowBtn(x, '×' + w))) : el('div', { class: 'mini' }, t('cg.none'))),
      section(t('fp.uses.h'), nb.uses.length, nb.uses.length ? el('div', { class: 'fp-list' }, ...nb.uses.slice(0, 30).map(([x, w]) => rowBtn(x, '×' + w))) : el('div', { class: 'mini' }, t('cg.none'))));
    void g;
  }
  function kidMeta(k) {
    if (k.startsWith('n:')) { const n = S.m.nodes.get(k); return n?.stats ? t('fp.foot.files', { n: n.stats.files }) : ''; }
    if (k.startsWith('f:')) return t('fp.foot.lines', { n: S.m.files.get(k).loc });
    if (k.startsWith('d:')) return t('fp.foot.files', { n: ctx.folderFiles(S.m, k).length });
    return '';
  }
  function overviewPanel() {
    const g = S.g, top = (S.m.kids.get('') || []).map((id) => S.m.nodes.get(id));
    const sum = (k) => top.filter((n) => n.kind !== 'external').reduce((s, n) => s + (n.stats?.[k] || 0), 0);
    const tasks = g.recent.tasks || [];
    panelEl.replaceChildren(
      el('div', { class: 'fp-kind' }, icon('codebase', 16), el('span', {}, t('fp.codebase'))),
      el('h2', { 'data-testid': 'fp-name' }, g.project.name), g.project.summary ? el('p', { class: 'fp-lead' }, g.project.summary) : '',
      el('div', { class: 'fp-tiles' }, tile(sum('files'), t('fp.stat.files')), tile(sum('loc'), t('fp.stat.lines')), tile(sum('endpoints'), t('fp.stat.endpoints'))),
      g.meta.problems?.length ? el('div', { class: 'warnbox' }, g.meta.problems.slice(0, 5).join(' / ')) : '',
      el('p', { class: 'mini' }, el('a', { href: '#/codegraph', 'data-testid': 'open-network' }, t('fp.network'))),
      tasks.length ? section(t('fp.recent'), tasks.length, el('div', { class: 'fp-tasks' }, ...tasks.slice(0, 3).map(taskCard))) : '',
      section(t('fp.systems'), top.length, el('div', { class: 'fp-list' }, ...SYSTEM_GROUPS.flatMap(([kind, key]) => {
        const list = top.filter((n) => n.kind === kind);
        return list.length ? [el('div', { class: 'fp-group mini' }, t(key)), ...list.map((n) => rowBtn('n:' + n.id, n.kind === 'external' ? '' : t('fp.foot.files', { n: n.stats?.files || 0 })))] : [];
      }))));
  }
  function taskCard(task) {
    const ids = task.items.map((i) => (S.m.files.has('f:' + i.ref) ? 'f:' + i.ref : i.ref)).filter((x) => S.m.files.has(x) || S.m.routes.has(x));
    return el('div', { class: 'fp-task' }, el('b', {}, task.title || t('fp.recent.uncommitted')), task.request ? el('div', { class: 'mini' }, t('fp.you.asked') + ' ' + task.request) : '',
      el('div', { class: 'mini' }, t('fp.recent.n', { n: ids.length }) + (task.commit ? ' · ' + task.commit : '')),
      ids.length ? btn('btn ghost', t('fp.recent.show', { n: ids.length }), () => { closeModal(); ctx.showAnswer({ title: task.title || t('fp.recent.uncommitted'), ids, steps: [], kind: 'recent' }); }, { 'data-testid': 'fp-show-recent' }) : '');
  }
  function answerPanel() {
    const a = S.answer;
    panelEl.replaceChildren(
      el('div', { class: 'fp-kind' }, icon('route', 16), el('span', {}, t('fp.answer'))),
      el('h2', { 'data-testid': 'fp-name' }, a.title),
      a.none ? el('p', { class: 'fp-lead' }, t(a.kind === 'nopath' ? 'fp.ans.nopath' : a.kind === 'unknown' ? 'fp.ans.unknown' : 'fp.ans.empty')) : '',
      a.steps.length ? el('ol', { class: 'fp-steps' }, ...a.steps.map((s, i) => el('li', {}, el('button', { type: 'button', class: 'fp-row', onclick: () => ctx.centerOn([s.id]) }, el('span', { class: 'fp-stepno' }, String(i + 1)), el('span', { class: 'fp-row-t' }, ctx.labelOf(S.m, s.id, S.technical)), s.note ? el('small', { class: 'mini' }, s.note) : '')))) : '',
      !a.steps.length && a.ids.length ? el('div', { class: 'fp-list' }, ...a.ids.slice(0, 40).map((id) => rowBtn(id))) : '',
      el('p', { class: 'mini' }, t('fp.ans.note')),
      el('div', { class: 'row' }, btn('btn', t('fp.back.map'), () => ctx.up(), { 'data-testid': 'fp-back-map' })));
  }

  // ------------------------------------------------------------ modals
  function openModal(title, body, testid) {
    closeMenus(); closeModal();
    modal = el('div', { class: 'fp-modal-wrap', onclick: (e) => { if (e.target === modal) closeModal(); } },
      el('div', { class: 'fp-modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': title, 'data-testid': testid },
        el('div', { class: 'fp-modal-h' }, el('h2', {}, title), btn('fp-iconbtn', '×', closeModal, { 'aria-label': t('fp.close'), 'data-testid': 'fp-close' })), body));
    stageWrap.parentElement.append(modal);
    modal.querySelector('button,[tabindex]')?.focus();
  }
  function healthTitle(i) { return t('fp.h.' + i.title.key, { file: i.title.file || '', n: i.title.n ?? '' }); }
  function openHealth() {
    const h = S.g.health, open = h.issues.filter((i) => !S.dismissed.has(i.id)), done = h.issues.filter((i) => S.dismissed.has(i.id));
    const c = h.checked || {};
    const card = (i, dismissed) => el('div', { class: 'fp-issue ' + i.severity + (dismissed ? ' done' : ''), 'data-testid': 'fp-issue' },
      el('div', { class: 'fp-issue-h' }, el('span', { class: 'fp-sev' }, t('fp.sev.' + i.severity)), el('b', {}, healthTitle(i))),
      el('p', {}, t('fp.h.detail.' + i.title.key)),
      el('ul', { class: 'mini' }, ...Object.entries(i.notes || {}).slice(0, 6).map(([id, note]) => el('li', {}, el('span', { class: 'mono' }, ctx.labelOf(S.m, id, true)), ' ' + note))),
      el('div', { class: 'row' },
        btn('btn ghost', t('fp.h.show'), () => { closeModal(); showOnMap(i.items); }, { 'data-testid': 'fp-h-show' }),
        btn('btn ghost', t('fp.h.fix'), () => ctx.copy(i.fix), { 'data-testid': 'fp-h-fix' }),
        dismissed ? btn('btn ghost', t('fp.h.again'), () => { S.dismissed.delete(i.id); ctx.saveDismissed(); openHealth(); header(); }, { 'data-testid': 'fp-h-again' })
          : btn('btn ghost', t('fp.h.not'), () => { S.dismissed.add(i.id); ctx.saveDismissed(); openHealth(); header(); }, { 'data-testid': 'fp-h-not' })));
    openModal(t('fp.health'), el('div', { class: 'fp-modal-b' },
      el('p', { class: 'mini' }, t('fp.h.note')),
      open.length ? el('div', {}, ...open.map((i) => card(i, false))) : el('p', { class: 'fp-lead', 'data-testid': 'fp-h-clean' }, t('fp.h.clean')),
      el('section', { class: 'fp-sec' }, el('h3', {}, t('fp.h.checked')), el('ul', { class: 'mini', 'data-testid': 'fp-h-checked' },
        el('li', {}, t('fp.h.checked.files', { n: c.files ?? 0 })), el('li', {}, t('fp.h.checked.eps', { n: c.endpoints ?? 0, m: c.mutating ?? 0 })),
        c.looksLikeServer && !c.endpoints ? el('li', { class: 'fp-warn' }, t('fp.h.checked.noeps')) : '')),
      done.length ? el('section', { class: 'fp-sec' }, el('h3', {}, t('fp.h.dismissed', { n: done.length })), ...done.map((i) => card(i, true))) : ''), 'fp-health-modal');
  }
  async function showOnMap(items) {
    const ids = items.filter((x) => S.m.files.has(x) || S.m.routes.has(x) || S.m.nodes.has(x));
    if (!ids.length) return;
    let view = ctx.viewOf(ids[0]);
    for (const id of ids.slice(1)) view = ctx.lcaView(view.startsWith('n:') || view.startsWith('f:') ? view : ids[0], id) || '';
    if (ids.length === 1) view = ctx.viewOf(ids[0]);
    await ctx.go(view);
    const set = new Set(); const cards = new Set(ctx.board.cards.keys());
    for (const id of ids) { const mm = ctx.memberFor(S.m, S.view, id, cards); if (mm) set.add(mm); }
    ctx.setMarks(set);
    ctx.centerOn([...set]);
  }
  function openRecent() {
    const tasks = S.g.recent.tasks || [];
    openModal(t('fp.recent'), el('div', { class: 'fp-modal-b' }, tasks.length ? el('div', { class: 'fp-tasks' }, ...tasks.map(taskCard)) : el('p', { class: 'fp-lead' }, t('fp.recent.none'))), 'fp-recent-modal');
  }
  function showScreen(s) {
    closeModal();
    ctx.showAnswer({ title: s.name, ids: s.behind.map((b) => b.id), steps: s.behind.map((b) => ({ id: b.id, note: t('fp.behind.' + b.kind) })), kind: 'screen' });
  }
  function openScreens() {
    const list = S.g.screens;
    openModal(t('fp.screens'), el('div', { class: 'fp-modal-b' }, el('p', { class: 'mini' }, t('fp.screens.sub')),
      list.length ? el('div', { class: 'fp-list' }, ...list.map((s) => el('button', { type: 'button', class: 'fp-row big', 'data-testid': 'fp-screen', onclick: () => showScreen(s) },
        el('span', { class: 'fp-row-t' }, s.name), el('small', { class: 'mono' }, s.url), s.description ? el('small', { class: 'mini' }, s.description) : '', el('small', { class: 'mini' }, t('fp.screens.behind', { n: s.behind.length }))))) : el('p', { class: 'fp-lead' }, t('fp.screens.none'))), 'fp-screens-modal');
  }
  function openFlows() {
    const flows = S.g.flows;
    openModal(t('fp.flows'), el('div', { class: 'fp-modal-b' }, flows.length ? el('div', { class: 'fp-list' }, ...flows.map((f) => el('button', { type: 'button', class: 'fp-row big', 'data-testid': 'fp-flow', onclick: () => { closeModal(); ctx.startFlow(f, 'flow'); } },
      el('span', { class: 'fp-row-t' }, f.title), el('small', { class: 'mini' }, t('fp.flow.steps', { n: f.steps.length }) + (f.auto ? ' · ' + t('fp.flow.auto') : '')), f.description ? el('small', { class: 'mini' }, f.description) : ''))) : el('p', { class: 'fp-lead' }, t('fp.flows.none'))), 'fp-flows-modal');
  }
  function openFilters(e) {
    closeMenus();
    const present = [...new Set(S.g.links.map((l) => l.k))].sort();
    const row = (label, checked, on, testid) => el('label', { class: 'row mini cg-toggle' }, el('input', { type: 'checkbox', checked: checked || null, 'data-testid': testid, onchange: (ev) => on(ev.target.checked) }), label);
    pop = el('div', { class: 'fp-pop', 'data-testid': 'fp-filters-pop' }, el('h3', {}, t('fp.conn')),
      ...present.map((k) => row(S.technical ? t('fp.kind.' + k + '.tech') : t('fp.kind.' + k), S.kinds.has(k), (on) => ctx.toggleKind(k, on), 'fp-kind-' + k)),
      el('h3', {}, t('fp.display')), row(t('fp.technical'), S.technical, ctx.toggleTechnical, 'fp-technical'), row(t('fp.recent.hl'), S.recentOn, ctx.toggleRecent, 'fp-recent-hl'));
    headerEl.append(pop);
    e?.stopPropagation?.();
  }
  function contextMenu(target, ev) {
    closeMenus();
    const items = [];
    if (target.id) {
      const d = describeItem(S.m, target.id, t);
      if (/^(n|d|f):/.test(target.id)) items.push([t('fp.open'), () => ctx.openItem(target.id)]);
      items.push([t('fp.details'), () => ctx.select(S.sel === target.id ? null : target.id) || (S.sel !== target.id && ctx.select(target.id))]);
      items.push([t('fp.copy.name'), () => ctx.copy(d.title)]);
      if (d.path) { items.push([t('fp.copy.path'), () => ctx.copy(d.path)]); if (!/^(n|d):/.test(target.id)) items.push([t('fp.editor'), () => { location.href = ctx.editorUrl(d.path, d.line); }]); }
      items.push([t('fp.ask.this'), () => { askBox.value = t('fp.ask.template', { name: d.title }); askBox.focus(); }]);
    } else if (target.edge) {
      items.push([t('fp.ask.conn'), () => { askBox.value = `${ctx.labelOf(S.m, target.edge.a)} → ${ctx.labelOf(S.m, target.edge.b)}`; askBox.focus(); }]);
    } else {
      items.push([t('fp.up'), () => ctx.up()], [t('fp.overview'), () => ctx.go('')], [t('fp.fit'), () => ctx.fit()], [t('fp.search.short'), () => focusSearch()]);
    }
    menu = el('div', { class: 'fp-menu', role: 'menu', 'data-testid': 'fp-menu', style: { left: ev.clientX + 'px', top: ev.clientY + 'px' } }, ...items.map(([label, run]) => el('button', { type: 'button', role: 'menuitem', onclick: () => { closeMenus(); run(); } }, label)));
    document.body.append(menu);
  }
  const focusSearch = () => { searchBox?.focus(); searchBox?.select(); };

  // ------------------------------------------------------------ question box and zoom buttons (built once)
  askBox = el('input', { type: 'text', 'data-testid': 'fp-ask', placeholder: t('fp.ask.ph'), 'aria-label': t('fp.ask.ph'), autocomplete: 'off',
    onkeydown: (e) => { if (e.key === 'Enter') { ctx.ask(askBox.value); } } });
  stageWrap.append(el('div', { class: 'fp-askbar' }, el('div', { class: 'fp-ask-note mini' }, t('fp.ask.note')), el('div', { class: 'fp-ask' }, askBox, btn('fp-iconbtn', '↑', () => ctx.ask(askBox.value), { 'aria-label': t('fp.ask.go'), 'data-testid': 'fp-ask-go' }))),
    el('div', { class: 'fp-zoom' }, btn('fp-iconbtn', '−', () => ctx.zoomBy(1 / 1.2), { 'aria-label': t('fp.zoom.out'), 'data-testid': 'fp-zoom-out' }), btn('fp-iconbtn', '⤢', () => ctx.fit(), { 'aria-label': t('fp.fit'), 'data-testid': 'fp-fit' }),
      btn('fp-iconbtn', '+', () => ctx.zoomBy(1.2), { 'aria-label': t('fp.zoom.in'), 'data-testid': 'fp-zoom-in' })));
  return { header, panel, closeOverlays, closeMenus, modalOpen: () => !!modal, focusSearch, contextMenu };
}
void chain;
