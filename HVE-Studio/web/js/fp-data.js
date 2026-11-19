// FR-1092: the model behind the floorplan — items (parts, files, endpoints), the chain of parents, what a view contains,
// and how a line between two files shows up on a board (summed per pair of cards). Pure data, no drawing.
// Ids: `n:<part>` a part · `f:<path>` a file · `r:<n>` an endpoint · `d:<part>|<folder>` a folder chip · `s:<path>::<name>` a function.
export const FOLDER_AT = 24;                    // a part with more files of its own than this groups them into folder chips
export const KIND_ORDER = ['import', 'call', 'http', 'rpc', 'event', 'queue', 'data', 'config'];

export function indexModel(g) {
  const m = { g, nodes: new Map(), files: new Map(), routes: new Map(), kids: new Map(), own: new Map(), routeOf: new Map(), out: new Map(), inn: new Map(), notes: new Map(), recent: new Map(), recentTop: new Map() };
  for (const n of g.nodes) m.nodes.set('n:' + n.id, n);
  for (const n of g.nodes) {
    const p = n.parent ? 'n:' + n.parent : '';
    (m.kids.get(p) || m.kids.set(p, []).get(p)).push('n:' + n.id);
  }
  for (const f of g.files) {
    m.files.set('f:' + f.p, f);
    const k = 'n:' + f.n;
    (m.own.get(k) || m.own.set(k, []).get(k)).push('f:' + f.p);
  }
  for (const r of g.routes) {
    m.routes.set(r.id, r);
    (m.routeOf.get('f:' + r.f) || m.routeOf.set('f:' + r.f, []).get('f:' + r.f)).push(r.id);
  }
  for (const l of g.links) {
    (m.out.get(l.a) || m.out.set(l.a, []).get(l.a)).push(l);
    (m.inn.get(l.b) || m.inn.set(l.b, []).get(l.b)).push(l);
  }
  for (const a of g.annotations || []) m.notes.set('f:' + a.path, a);
  for (const t of g.recent?.tasks || []) for (const it of t.items) {
    const id = m.files.has('f:' + it.ref) ? 'f:' + it.ref : it.ref;
    if (!m.recent.has(id)) m.recent.set(id, { change: it.change, note: it.note, task: t });
  }
  // a part shows "N changed" when files inside it changed
  for (const id of m.recent.keys()) for (const up of chain(m, id).slice(1)) m.recentTop.set(up, (m.recentTop.get(up) || 0) + 1);
  return m;
}

const folderOf = (p) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');
export const parentOf = (m, id) => {
  if (id.startsWith('n:')) { const n = m.nodes.get(id); return n && n.parent ? 'n:' + n.parent : ''; }
  if (id.startsWith('f:')) return 'n:' + m.files.get(id)?.n;
  if (id.startsWith('r:')) return 'f:' + m.routes.get(id)?.f;
  if (id.startsWith('s:')) return 'f:' + id.slice(2).split('::')[0];
  if (id.startsWith('d:')) return 'n:' + id.slice(2).split('|')[0];
  return '';
};
/** [id, parent, grandparent, ...] without the empty root. */
export function chain(m, id) {
  const out = [];
  for (let c = id, guard = 0; c && guard < 12; c = parentOf(m, c), guard++) out.push(c);
  return out;
}
export const isInside = (m, id, container) => chain(m, id).includes(container);

/** Common leading folder of the files a part owns (so folder chips are relative to it). */
function commonFolder(files) {
  let base = null;
  for (const f of files) {
    const parts = folderOf(f.slice(2)).split('/').filter(Boolean);
    if (base === null) { base = parts; continue; }
    let i = 0;
    while (i < base.length && i < parts.length && base[i] === parts[i]) i++;
    base = base.slice(0, i);
  }
  return (base || []).join('/');
}

/** Members shown inside a view. */
export function membersOf(m, view) {
  if (view === '') return (m.kids.get('') || []).slice();
  if (view.startsWith('n:')) {
    const kids = (m.kids.get(view) || []).slice();
    const own = m.own.get(view) || [];
    return kids.concat(own.length > FOLDER_AT ? foldersOf(m, view, own, commonFolder(own)) : own);
  }
  if (view.startsWith('d:')) {
    const [nid, folder] = view.slice(2).split('|');
    const own = (m.own.get('n:' + nid) || []).filter((f) => f.slice(2).startsWith(folder + '/'));
    return foldersOf(m, 'n:' + nid, own, folder);
  }
  if (view.startsWith('f:')) {
    const f = m.files.get(view);
    return (m.routeOf.get(view) || []).concat(m.fileSyms?.get(view) || (f?.s || []).map((s) => `s:${f.p}::${s[0]}`));
  }
  return [];
}
function foldersOf(m, nodeId, files, base) {
  const nid = nodeId.slice(2), groups = new Map(), out = [];
  for (const f of files) {
    const rest = base ? f.slice(2).slice(base.length + 1) : f.slice(2);
    const head = rest.includes('/') ? rest.split('/')[0] : '';
    (groups.get(head) || groups.set(head, []).get(head)).push(f);
  }
  for (const [head, list] of groups) {
    if (head && list.length >= 3) out.push(`d:${nid}|${base ? base + '/' + head : head}`);
    else out.push(...list);
  }
  return out;
}
export const folderLabel = (id) => id.slice(2).split('|')[1].split('/').pop();
export const folderFiles = (m, id) => { const [nid, folder] = id.slice(2).split('|'); return (m.own.get('n:' + nid) || []).filter((f) => f.slice(2).startsWith(folder + '/')); };

/** Which member of `view` stands for `id` (null when `id` is outside the view). */
export function memberFor(m, view, id, members) {
  const set = members instanceof Set ? members : new Set(members);
  for (const c of chain(m, id)) if (set.has(c)) return c;
  if (id.startsWith('f:') && view.startsWith('n:')) {          // a file inside a folder chip of this view
    for (const mem of set) if (mem.startsWith('d:') && mem.slice(2).split('|')[0] === view.slice(2) && id.slice(2).startsWith(mem.split('|')[1] + '/')) return mem;
  }
  if (id.startsWith('f:') && view.startsWith('d:')) {
    for (const mem of set) if (mem.startsWith('d:') && mem.slice(2).split('|')[0] === view.slice(2).split('|')[0] && id.slice(2).startsWith(mem.split('|')[1] + '/')) return mem;
  }
  return null;
}
/** The outside item that stands for `id` next to `view`: the child of the lowest common parent that holds it. */
export function outsideFor(m, view, id) {
  const mine = chain(m, view.startsWith('d:') ? 'n:' + view.slice(2).split('|')[0] : view);
  const theirs = chain(m, id);
  for (let i = 0; i < theirs.length; i++) {
    if (mine.includes(theirs[i])) return i === 0 ? null : theirs[i - 1];
  }
  return theirs[theirs.length - 1] || null;
}

/** Cards and summed lines for one view. `kinds` is the set of line kinds that are switched on. */
export function boardOf(m, view, kinds, extra) {
  const members = extra ? extra.ids.slice() : membersOf(m, view);
  const set = new Set(members);
  const pair = new Map();
  const outside = new Map();      // id -> {left, right}
  const add = (a, b, l) => {
    const k = a + '\u0001' + b + '\u0001' + l.k;
    const e = pair.get(k) || pair.set(k, { a, b, k: l.k, w: 0, carries: new Map(), label: l.label || '' }).get(k);
    e.w += l.w || 1;
    if (l.k === 'http' && l.b.startsWith('r:')) { const r = m.routes.get(l.b); if (r) e.carries.set(r.m + ' ' + r.p, (e.carries.get(r.m + ' ' + r.p) || 0) + 1); }
  };
  const link = (l) => {
    if (!kinds.has(l.k)) return;
    // a line ends on a file or an endpoint; on a board it ends on whatever card holds that end
    let a = extra ? (set.has(l.a) ? l.a : null) : memberFor(m, view, l.a, set);
    let b = extra ? (set.has(l.b) ? l.b : null) : memberFor(m, view, l.b, set);
    if (extra) { if (a && b && a !== b) add(a, b, l); return; }
    if (a && b) { if (a !== b) add(a, b, l); return; }
    if (!a && !b) return;
    if (!view) return;
    const other = outsideFor(m, view, a ? l.b : l.a);
    if (!other || other === (a || b)) return;
    const o = outside.get(other) || outside.set(other, { left: 0, right: 0 }).get(other);
    if (a) { o.right += l.w || 1; add(a, other, l); } else { o.left += l.w || 1; add(other, b, l); }
  };
  const seen = new Set();
  for (const id of members) {
    if (!view.startsWith('f:')) for (const l of [...(m.out.get(id) || []), ...(m.inn.get(id) || [])]) { if (!seen.has(l)) { seen.add(l); link(l); } }
    if (id.startsWith('n:') || id.startsWith('d:')) {
      const files = id.startsWith('n:') ? allFiles(m, id) : folderFiles(m, id);
      for (const f of files) for (const l of [...(m.out.get(f) || []), ...(m.inn.get(f) || [])]) { if (!seen.has(l)) { seen.add(l); link(l); } }
      if (id.startsWith('n:')) for (const l of [...(m.out.get(id) || []), ...(m.inn.get(id) || [])]) { if (!seen.has(l)) { seen.add(l); link(l); } }
    }
    if (id.startsWith('f:')) for (const r of m.routeOf.get(id) || []) for (const l of m.inn.get(r) || []) { if (!seen.has(l)) { seen.add(l); link(l); } }
  }
  for (const l of m.symLinks?.get(view) || []) link(l);
  // in an endpoint view, who calls each endpoint is an outside item (the requests)
  const left = [], right = [];
  for (const [id, o] of outside) (o.left >= o.right ? left : right).push(id);
  const edges = [...pair.values()].filter((e) => (set.has(e.a) || outside.has(e.a)) && (set.has(e.b) || outside.has(e.b)));
  return { members, left, right, edges };
}
export function allFiles(m, nodeId) {
  const out = [...(m.own.get(nodeId) || [])];
  for (const c of m.kids.get(nodeId) || []) out.push(...allFiles(m, c));
  return out;
}
export const nodeFilesCount = (m, id) => m.nodes.get(id)?.stats?.files ?? 0;

/** Shortest chain of items from `from` to `to` over the lines (files, endpoints and outside parts), or null. */
export function shortestPath(m, from, to) {
  const lift = (id, mm) => (id.startsWith('d:') ? null : id.startsWith('n:') ? (mm.nodes.get(id)?.kind === 'external' ? id : null) : id);
  const start = id2seeds(m, from), goal = new Set(id2seeds(m, to));
  const prev = new Map(), q = [];
  for (const s of start) { prev.set(s, null); q.push(s); }
  while (q.length) {
    const cur = q.shift();
    if (goal.has(cur)) { const path = []; for (let c = cur; c; c = prev.get(c)) path.unshift(c); return path; }
    const nbs = [...(m.out.get(cur) || []).map((l) => l.b), ...(m.inn.get(cur) || []).map((l) => l.a)];
    // an endpoint is reached through its file
    if (cur.startsWith('r:')) nbs.push('f:' + m.routes.get(cur).f);
    if (cur.startsWith('f:')) {
      nbs.push(...(m.routeOf.get(cur) || []));
      for (const anc of chain(m, cur).slice(1)) nbs.push(...(m.out.get(anc) || []).map((l) => l.b), ...(m.inn.get(anc) || []).map((l) => l.a));   // lines drawn between whole parts
    }
    for (const n of nbs) if (!prev.has(n) && lift(n, m)) { prev.set(n, cur); q.push(n); }
  }
  return null;
}
function id2seeds(m, id) {
  if (id.startsWith('n:')) {
    if (m.nodes.get(id)?.kind === 'external') return [id];
    return allFiles(m, id);
  }
  if (id.startsWith('d:')) return folderFiles(m, id);
  return [id];
}
export function labelOf(m, id, technical) {
  if (id.startsWith('n:')) { const n = m.nodes.get(id); return n ? (technical ? n.id : n.label) : id; }
  if (id.startsWith('f:')) { const f = m.files.get(id); return f ? (technical ? f.p.split('/').pop() : f.name) : id; }
  if (id.startsWith('r:')) { const r = m.routes.get(id); return r ? (technical ? `${r.m} ${r.p}` : r.name) : id; }
  if (id.startsWith('d:')) return folderLabel(id);
  if (id.startsWith('s:')) return id.split('::')[1];
  return id;
}

/** What a card says about an item. */
export function describe(m, id, t) {
  if (id.startsWith('n:')) {
    const n = m.nodes.get(id);
    if (!n) return { title: id, dev: id, desc: '', icon: 'folder', type: 'node' };
    const st = n.stats || {}, kids = (m.kids.get(id) || []).length;
    const foot = n.kind === 'external' ? '' : kids ? t('fp.foot.parts', { n: kids }) : t('fp.foot.files', { n: st.files || 0 });
    return { title: n.label, dev: n.id, desc: n.summary, icon: n.kind, type: 'node', kind: n.kind, foot, path: (n.paths || [])[0] || '' };
  }
  if (id.startsWith('f:')) {
    const f = m.files.get(id), eps = (m.routeOf.get(id) || []).length;
    return { title: f.name, dev: f.p.split('/').pop(), desc: f.d, icon: 'file', type: 'file', foot: eps ? t('fp.foot.eps', { n: eps }) : t('fp.foot.lines', { n: f.loc }), path: f.p, line: 1, note: m.notes.get(id)?.note || '' };
  }
  if (id.startsWith('r:')) {
    const r = m.routes.get(id);
    return { title: r.name, dev: r.h || r.p, desc: r.d, icon: 'route', type: 'route', method: r.m, urlPath: r.p, path: r.f, line: r.l };
  }
  if (id.startsWith('d:')) {
    const files = folderFiles(m, id);
    return { title: folderLabel(id), dev: id.slice(2).split('|')[1], desc: '', icon: 'folder', type: 'folder', foot: t('fp.foot.files', { n: files.length }), path: '' };
  }
  if (id.startsWith('s:')) {
    const [file, name] = id.slice(2).split('::');
    const sym = (m.symInfo?.get(id)) || {};
    return { title: name.split('.').pop(), dev: name, desc: sym.doc || '', icon: 'symbol', type: 'symbol', foot: sym.kind ? t('cg.kind.' + sym.kind) : '', path: file, line: sym.line || 1 };
  }
  return { title: id, dev: id, desc: '', icon: 'file', type: 'file' };
}
