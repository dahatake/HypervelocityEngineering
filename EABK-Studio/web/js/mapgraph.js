// FR-1079 AC-426: the map in Graph mode — goal → requirement → acceptance criteria → System Test, left to right (layered layout).
import { t, onLang } from './i18n.js';
import { store } from './store.js';
import { el, typeLabel } from './ui.js';
import { graphView } from './graph.js';

const TRACE_TYPES = new Set(['goal', 'req', 'ac', 'case']);
const TRACE_RELS = new Set(['goal-req', 'req-ac', 'ac-case', 'req-case']);

export function traceGraph() {
  const nodes = [], ids = new Set();
  for (const n of store.nodes.values()) {
    if (!TRACE_TYPES.has(n.type)) continue;
    ids.add(n.id);
    nodes.push({ id: n.id, label: n.label, title: n.title || '', type: n.type === 'req' && n.kind === 'NFR' ? 'nfr' : n.type, word: typeLabel(n) });
  }
  const edges = store.edges.filter((e) => TRACE_RELS.has(e.rel) && ids.has(e.s) && ids.has(e.t)).map((e) => ({ from: e.s, to: e.t }));
  return { nodes, edges };
}

export function mount(host) {
  const page = el('div', { class: 'page gv-page' });
  host.append(page);
  let gv = null;
  const render = () => {
    gv?.destroy();
    const g = traceGraph();
    gv = graphView({ name: 'map', nodes: g.nodes, edges: g.edges, layout: 'layered', note: t('graph.note.map') });
    page.replaceChildren(el('h1', {}, t('graph.map.title')), gv.el);
  };
  const view = { mode: 'map-graph', getState: () => ({ dim: 'graph', graph: traceGraph() }) };
  window.eabkView = view;
  render();
  const offs = [onLang(render), store.on('model', render)];
  return { destroy() { offs.forEach((f) => f()); gv?.destroy(); if (window.eabkView === view) window.eabkView = undefined; } };
}
