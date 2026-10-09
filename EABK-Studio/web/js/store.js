// Shared state: model, graph indexes, selection / focus, search.
const norm = (s) => String(s ?? '').normalize('NFKC').toLowerCase();

class Store {
  constructor() {
    this.model = null;
    this.nodes = new Map();
    this.adj = new Map();
    this.edges = [];
    this.selected = null;
    this.hover = null;
    this.focus = null; // Set of ids chosen from search / matrix cells
    this.focusLabel = '';
    this._l = {};
    this._rel = new Map();
  }

  on(evt, fn) { (this._l[evt] ||= new Set()).add(fn); return () => this._l[evt].delete(fn); }
  emit(evt, arg) { for (const fn of [...(this._l[evt] || [])]) { try { fn(arg); } catch (e) { console.error(e); } } }

  load(model) {
    this.model = model;
    this.nodes = new Map();
    this.adj = new Map();
    this._rel.clear();
    for (const n of model.graph.nodes) {
      n._hay = norm([n.id, n.label, n.title, n.path, n.group, n.status].filter(Boolean).join(' '));
      this.nodes.set(n.id, n);
      this.adj.set(n.id, []);
    }
    this.edges = model.graph.edges;
    for (const e of this.edges) {
      this.adj.get(e.s)?.push({ id: e.t, rel: e.rel, out: true });
      this.adj.get(e.t)?.push({ id: e.s, rel: e.rel, out: false });
    }
    this.reqMap = new Map(model.reqs.map((r) => [r.id, r]));
    for (const r of model.reqs) {
      const n = this.nodes.get(r.id);
      if (n) n._hay += ' ' + norm(r.text + ' ' + r.acs.map((a) => a.text).join(' ') + ' ' + r.entities.join(' '));
    }
    if (this.selected && !this.nodes.has(this.selected)) this.selected = null;
    if (this.focus) this.focus = null;
    this.emit('model');
  }

  node(id) { return this.nodes.get(id); }
  neighbors(id, types) {
    const a = this.adj.get(id) || [];
    return types ? a.filter((x) => types.includes(this.nodes.get(x.id)?.type)) : a;
  }

  // Related nodes: direct neighbours, plus (depth 2) neighbours reached through non-hub nodes.
  related(id, depth = 2) {
    const key = id + ':' + depth;
    if (this._rel.has(key)) return this._rel.get(key);
    const out = new Set([id]);
    const first = this.adj.get(id) || [];
    for (const x of first) out.add(x.id);
    if (depth > 1) {
      const start = this.nodes.get(id);
      for (const x of first) {
        const via = this.nodes.get(x.id);
        if (!via || x.rel === 'ref' || via.type === 'component' || via.deg > 36) continue;
        if (start.type === 'file' && via.type === 'component') continue;
        for (const y of this.adj.get(x.id) || []) {
          if (y.rel === 'ref' || y.rel === 'member') continue;
          const tn = this.nodes.get(y.id);
          if (tn && (tn.type === 'param' || tn.type === 'req')) continue;
          out.add(y.id);
        }
      }
    }
    this._rel.set(key, out);
    return out;
  }

  activeSet() {
    if (this.focus && this.focus.size) return this.focus;
    if (this.selected) return this.related(this.selected, 2);
    return null;
  }

  select(id, opts = {}) {
    this.focus = null;
    this.focusLabel = '';
    this.selected = id;
    this.emit('select', { id, ...opts });
  }
  setFocus(ids, label = '', opts = {}) {
    this.selected = null;
    this.focus = new Set(ids);
    this.focusLabel = label;
    this.emit('select', { id: null, focus: true, ...opts });
  }
  clear() {
    this.selected = null; this.focus = null; this.focusLabel = '';
    this.emit('select', { id: null, cleared: true });
  }
  setHover(id) {
    if (this.hover === id) return;
    this.hover = id;
    this.emit('hover', id);
  }

  search(q, limit = 40) {
    const toks = norm(q).split(/\s+/).filter(Boolean);
    if (!toks.length) return { total: 0, hits: [], all: [], toks };
    const bias = { goal: 8, req: 6, ac: 3, part: 5, api: 5, table: 5, entity: 4, file: 3, case: 3, question: 2, component: 4, param: 2, persona: 2, external: 2 };
    const out = [];
    for (const n of this.nodes.values()) {
      let score = 0, ok = true;
      const id = norm(n.id), lab = norm(n.label), ttl = norm(n.title);
      for (const t of toks) {
        if (!n._hay.includes(t)) { ok = false; break; }
        score += id === t ? 200 : id.startsWith(t) ? 100 : lab.includes(t) ? 60 : ttl.includes(t) ? 40 : 10;
      }
      if (ok) out.push({ n, score: score + (bias[n.type] || 0) });
    }
    out.sort((a, b) => b.score - a.score || a.n.id.localeCompare(b.n.id));
    return { total: out.length, hits: out.slice(0, limit).map((x) => x.n), all: out.map((x) => x.n.id), toks };
  }
}

export const store = new Store();
export { norm };
