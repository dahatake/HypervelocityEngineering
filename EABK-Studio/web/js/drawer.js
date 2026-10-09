// Detail drawer for the selected node.
import { t, onLang, lang } from './i18n.js';
import { store } from './store.js';
import { el, colorOf, typeLabel, statusBadge, nodeChip, vscodeUrl, toast, TYPE_ORDER } from './ui.js';

export function initDrawer(root) {
  const render = () => {
    const id = store.selected, n = id && store.node(id);
    if (!n) { root.hidden = true; root.replaceChildren(); return; }
    root.hidden = false;
    const m = store.model;
    const kids = [];
    const section = (title, body) => body && (Array.isArray(body) ? body.length : true) ? el('section', {}, el('h4', {}, title), body) : null;
    const chips = (ids, max = 60) => ids.length ? el('div', { class: 'chips' }, ids.slice(0, max).map((x) => nodeChip(x)), ids.length > max ? el('span', { class: 'mini' }, '+' + (ids.length - max)) : '') : null;
    const kv = (pairs) => el('dl', { class: 'kv' }, pairs.filter(([, v]) => v).flatMap(([k, v]) => [el('dt', {}, k), el('dd', {}, v)]));
    const loc = (file, line) => file ? el('div', { class: 'row mini' }, el('span', { class: 'mono' }, `${file}${line ? ':' + line : ''}`), el('a', { href: vscodeUrl(file, line), title: 'VS Code' }, '↗ VS Code')) : null;
    const byType = (types) => store.neighbors(id, types).map((x) => x.id);
    const rel = new Map();
    for (const a of store.adj.get(id) || []) { const ty = store.node(a.id)?.type; if (!ty) continue; if (!rel.has(ty)) rel.set(ty, []); rel.get(ty).push(a.id); }

    let head = [el('div', { class: 'typ' }, el('i', { class: 'dot', style: { background: colorOf(n) } }), typeLabel(n), ' · ', el('span', { class: 'mono' }, n.id)), el('h2', {}, n.type === 'req' || n.type === 'goal' ? n.title : n.label)];
    const used = new Set();
    if (n.type === 'req') {
      const r = store.reqMap.get(n.id);
      head.push(el('div', { class: 'row' }, statusBadge(r.statusKind, r.status), r.priority ? el('span', { class: 'badge' }, r.priority) : '', r.goal ? nodeChip(r.goal) : '', el('span', { class: 'badge ' + (n.impl === 'done' ? 'ok' : n.impl === 'none' ? 'bad' : '') }, t('impl.' + n.impl))));
      kids.push(section(t('d.text'), el('div', {}, r.text)),
        section(t('d.acs'), r.acs.map((a) => el('div', { class: 'ac' }, el('div', { class: 'row' }, nodeChip(a.id), a.level ? el('span', { class: 'badge' }, a.level) : '', a.blocked ? el('span', { class: 'badge bad' }, 'BLOCKED ' + a.blocked.slice(0, 40)) : ''), el('div', {}, a.text)))),
        section(t('d.info'), kv([[t('col.origin'), r.origin], [t('col.sources'), r.sources], [t('col.assets'), r.assets], [t('col.priority'), r.priorityNote]])),
        section(t('type.entity'), chips(byType(['entity']))),
        section(t('type.param'), el('div', { class: 'chips' }, byType(['param']).map((p) => nodeChip(p, store.node(p).label + ' · ' + store.node(p).title.slice(0, 30))))),
        section(t('type.question'), chips(byType(['question']))),
        section(t('d.impl'), chips(byType(['file']).filter((f) => store.node(f).role !== 'test'))),
        section(t('d.tests'), chips([...byType(['file']).filter((f) => store.node(f).role === 'test'), ...byType(['case'])])),
        section(t('type.part') + ' / API / ' + t('type.table'), chips(byType(['part', 'api', 'table']))),
        section(t('d.refs'), chips(store.neighbors(id).filter((x) => x.rel === 'ref').map((x) => x.id))),
        section(t('d.src'), loc(n.file, n.line)),
        r.body ? el('section', {}, el('details', {}, el('summary', { class: 'mini', style: { cursor: 'pointer' } }, t('d.raw')), el('div', { class: 'pre' }, r.body))) : null);
      ['entity', 'param', 'question', 'file', 'part', 'api', 'table', 'case', 'ac', 'goal'].forEach((x) => used.add(x));
    } else if (n.type === 'goal') {
      const g = m.goals.find((x) => x.id === id);
      const reqs = byType(['req']);
      const done = reqs.filter((x) => store.node(x).impl === 'done').length;
      head.push(el('div', { class: 'row' }, el('span', { class: 'badge' }, `${reqs.length} ${t('type.req')}`), el('span', { class: 'badge ok' }, `${t('impl.done')} ${done}`)));
      kids.push(section(t('col.metric'), g?.metric), section(t('col.method'), g?.method), section(t('d.src'), loc(n.file, n.line)), section(t('type.req'), chips(reqs, 80)));
      used.add('req');
    } else if (n.type === 'ac') {
      const r = store.reqMap.get(n.req);
      const a = r?.acs.find((x) => x.id === id);
      head.push(el('div', { class: 'row' }, a?.level ? el('span', { class: 'badge' }, a.level) : '', nodeChip(n.req)));
      kids.push(section(t('d.text'), el('div', {}, a?.text)), section('BLOCKED', a?.blocked ? el('div', { class: 'badge bad' }, a.blocked) : null), section(t('d.src'), loc(n.file, n.line)));
    } else if (n.type === 'file') {
      kids.push(section(t('d.info'), kv([[t('col.path'), el('span', { class: 'mono' }, n.path)], [t('col.comp'), nodeChip('comp:' + n.comp)], [t('col.module'), n.module], [t('col.role'), n.role === 'test' ? 'test' : 'impl']])),
        el('section', {}, el('a', { class: 'btn', href: vscodeUrl(n.path) }, '↗ ' + t('d.open'))));
    } else if (n.type === 'component') {
      const files = byType(['file']);
      kids.push(section(t('d.info'), kv([[t('col.path'), n.path], [t('type.file'), files.length]])));
    } else if (n.type === 'part') {
      const p = m.catalog.parts.find((x) => 'part:' + x.name === id);
      kids.push(section(t('col.purpose'), p?.purpose), section(t('d.src'), loc(n.file, n.line)));
    } else if (n.type === 'case') {
      const c = m.cases.find((x) => x.id === id);
      head.push(el('div', { class: 'row' }, el('span', { class: 'badge ' + (c?.status === 'pass' ? 'pass' : c?.status === 'fail' ? 'fail' : '') }, c?.status), el('span', { class: 'badge' }, c?.layer)));
      kids.push(section(t('d.info'), kv([['command', c?.command && el('span', { class: 'mono' }, c.command)], ['last run', c?.last_run_at], ['commit', c?.last_commit], ['evidence', c?.evidence && el('span', { class: 'mono' }, c.evidence)]])));
    } else if (n.type === 'question') {
      const q = m.questions.find((x) => x.id === id);
      kids.push(section(t('col.question'), q?.question), section(t('col.options'), q?.options), section(t('col.recommend'), q?.recommend), section(t('col.state'), q && el('span', { class: 'badge' }, q.state)), section(t('col.answer'), q?.answer), section(t('d.src'), loc(n.file, n.line)));
    } else if (n.type === 'param') {
      const p = m.params.find((x) => x.id === id);
      kids.push(section(t('d.info'), kv([[t('col.name'), p?.name], [t('col.value'), p && `${p.value} ${p.unit}`], [t('col.basis'), p?.basis], [t('col.status'), p?.status]])), section(t('d.src'), loc(n.file, n.line)));
    } else if (n.type === 'entity') {
      const term = m.terms.find((x) => 'ent:' + x.term === id) || m.terms.find((x) => x.term === n.label);
      const sm = m.stateMachines.find((x) => 'ent:' + x.entity === id);
      kids.push(section(t('col.definition'), term?.definition || (n.title !== n.label ? n.title : '')), section(t('col.forbidden'), term?.forbidden && term.forbidden !== 'なし' ? term.forbidden : null),
        sm ? section(t('dgm.states'), el('div', {}, el('div', { class: 'chips' }, sm.states.map((s) => el('span', { class: 'badge' }, s))), el('div', { style: { marginTop: '8px' } }, el('a', { class: 'btn ghost', href: '#/diagrams', onclick: () => { } }, '▦ ' + t('dgm.states'))))) : null,
        section(t('d.src'), loc(n.file, n.line)));
    } else if (n.type === 'persona') {
      const p = m.personas.find((x) => 'persona:' + x.name === id);
      kids.push(section(t('d.info'), kv([[t('col.work'), p?.work], [t('col.decision'), p?.decision], [t('col.data'), p?.data], [t('col.role'), p?.role]])));
    } else if (n.type === 'external') {
      const p = m.integrations.find((x) => 'ext:' + x.name === id);
      kids.push(section(t('d.info'), kv([[t('col.method'), p?.method], [t('col.meaning'), p?.meaning], [t('col.owner'), p?.owner]])));
    } else if (n.type === 'api' || n.type === 'table') kids.push(section(t('d.src'), loc(n.file, n.line)));

    // remaining relations as chips
    for (const ty of TYPE_ORDER) {
      if (used.has(ty) || !rel.has(ty) || ty === 'component' && n.type === 'file') continue;
      if (n.type === 'req') continue;
      kids.push(section(t('type.' + ty), chips(rel.get(ty), 80)));
    }
    root.replaceChildren(el('button', { class: 'x', onclick: () => store.clear(), title: 'Esc' }, '×'), ...head,
      el('section', {}, el('div', { class: 'row' },
        el('button', { class: 'btn', onclick: () => { location.hash = '#/map2d'; store.select(id, { fly: true }); } }, '🗺 ' + t('place.to2d')),
        el('button', { class: 'btn', onclick: () => { location.hash = '#/map3d'; store.select(id, { fly: true }); } }, '🧊 ' + t('place.to3d')),
        el('button', { class: 'btn ghost', onclick: () => navigator.clipboard?.writeText(n.id).then(() => toast(t('d.copied'))) }, '⧉ ' + t('d.copy')))),
      ...kids.filter(Boolean));
    root.scrollTop = 0;
  };
  store.on('select', render); store.on('model', render); onLang(render);
  render();
}
