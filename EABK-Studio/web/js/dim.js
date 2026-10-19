// FR-1040: 2D / 3D switch shared by the diagrams and the map.
// The icons come from the bundled icon set, so nothing is fetched from outside (AC-222).
import { t } from './i18n.js';
import { el, icon } from './ui.js';

// The chosen dimension is kept only while the page is open (FR-1040 [ASSUMPTION]: not persisted, Q-003).
export const dimState = { map: '2d', diagrams: '2d' };

// The command box ("> 2D/3D") calls the handler of the page that is open.
let handler = null;
export function registerDim(fn) { handler = fn; return () => { if (handler === fn) handler = null; }; }
export const hasDimHandler = () => !!handler;
export function runDim(d) { if (handler) handler(d); }

// FR-1066: the header switch reads one shared state that the open screen publishes (dims it supports, what is shown, what was chosen).
// `selected` differs from `current` only when 3D was chosen but could not be drawn and 2D is shown instead (AC-370).
export const headerDim = { dims: ['2d'], current: '2d', selected: '2d' };
const headerListeners = new Set();
export const onHeaderDim = (fn) => { headerListeners.add(fn); return () => headerListeners.delete(fn); };
export function publishDim(p) {
  const next = { ...headerDim, ...p };
  if (!p.selected) next.selected = next.current;
  Object.assign(headerDim, next);
  for (const f of [...headerListeners]) f(headerDim);
}
export const ALL_DIMS = ['2d', '3d', 'rpg'];
// The header switch (FR-1066): all three buttons always exist; the ones this screen does not support are disabled with a reason.
export function headerDimToggle() {
  const { dims, current, selected } = headerDim;
  const reasonOf = (d) => t(d === 'rpg' ? 'hdim.reason.rpg' : 'hdim.reason.3d');
  const live = el('span', { class: 'sr-only', role: 'status', 'aria-live': 'polite' }, t('dim.now', { d: current.toUpperCase() }));
  const btn = (d) => {
    const on = d === current, off = !dims.includes(d);
    const label = off ? `${d.toUpperCase()}: ${reasonOf(d)}` : on ? t('dim.now', { d: d.toUpperCase() }) : t('dim.to', { d: d.toUpperCase() });
    return el('button', { type: 'button', class: 'dim-btn' + (on ? ' on' : ''), 'data-dim': d, 'aria-pressed': on ? 'true' : 'false', disabled: off ? true : null,
      'aria-label': label, title: label, 'data-reason': off ? reasonOf(d) : null,
      onclick: () => { if (!off && !on) runDim(d); } }, dimIcon(d), el('span', { class: 'dim-word' }, d.toUpperCase()));
  };
  const off = ALL_DIMS.filter((d) => !dims.includes(d));
  return el('div', { class: 'dim-toggle hdr-dim', role: 'group', 'aria-label': t('dim.group'), 'data-testid': 'header-dim-toggle', 'data-current': current, 'data-selected': selected },
    ...ALL_DIMS.map(btn), el('span', { class: 'mini hdr-dim-reason', 'data-testid': 'header-dim-reason' }, off.length ? off.map((d) => `${d.toUpperCase()}: ${reasonOf(d)}`).join(' / ') : ''), live);
}

// 切替アイコンは同梱の 1 セット（ui.js の icon）の線画で、20px・currentColor（FR-1048 AC-268）。2D は面（平らな表）、3D は立方体。
export function dimIcon(dim) {
  const svg = icon(dim === 'rpg' ? 'rpg' : dim === '2d' ? 'tables' : 'map3d', { size: 20 });
  svg.setAttribute('class', 'icon dim-ico dim-ico-' + dim);
  return svg;
}
// <div data-testid="dim-toggle" data-current="2d|3d|rpg"> with <button data-dim="2d|3d|rpg">. The map offers RPG as a third mode (FR-1053).
export function dimToggle({ current, onPick, dims = ['2d', '3d'] }) {
  const cur = dims.includes(current) ? current : '2d';
  const live = el('span', { class: 'sr-only', role: 'status', 'aria-live': 'polite' }, t('dim.now', { d: cur.toUpperCase() }));
  const btn = (d) => {
    const on = d === cur;
    return el('button', { type: 'button', class: 'dim-btn' + (on ? ' on' : ''), 'data-dim': d, 'aria-pressed': on ? 'true' : 'false',
      'aria-label': on ? t('dim.now', { d: d.toUpperCase() }) : t('dim.to', { d: d.toUpperCase() }),
      title: on ? t('dim.now', { d: d.toUpperCase() }) : t('dim.to', { d: d.toUpperCase() }),
      onclick: () => { if (!on) onPick(d); } }, dimIcon(d), el('span', { class: 'dim-word' }, d.toUpperCase()));
  };
  return el('div', { class: 'dim-toggle', role: 'group', 'aria-label': t('dim.group'), 'data-testid': 'dim-toggle', 'data-current': cur }, ...dims.map(btn), live);
}
