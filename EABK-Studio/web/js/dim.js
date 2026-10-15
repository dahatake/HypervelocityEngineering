// FR-1040: 2D / 3D switch shared by the diagrams and the map.
// The icons are drawn inline (anime-style faces on a flat sheet / a cube), so nothing is fetched from outside (AC-222).
import { t } from './i18n.js';
import { el, svgEl } from './ui.js';

// The chosen dimension is kept only while the page is open (FR-1040 [ASSUMPTION]: not persisted, Q-003).
export const dimState = { map: '2d', diagrams: '2d' };

// The command box ("> 2D/3D") calls the handler of the page that is open.
let handler = null;
export function registerDim(fn) { handler = fn; return () => { if (handler === fn) handler = null; }; }
export const hasDimHandler = () => !!handler;
export function runDim(d) { if (handler) handler(d); }

const FACE = (x, y) => [
  svgEl('circle', { cx: x - 5, cy: y, r: 1.9, fill: '#1b2440' }), svgEl('circle', { cx: x + 5, cy: y, r: 1.9, fill: '#1b2440' }),
  svgEl('circle', { cx: x - 5.8, cy: y - 0.7, r: 0.6, fill: '#fff' }), svgEl('circle', { cx: x + 4.2, cy: y - 0.7, r: 0.6, fill: '#fff' }),
  svgEl('ellipse', { cx: x - 9, cy: y + 4, rx: 2.4, ry: 1.4, fill: '#ff9db8', 'fill-opacity': 0.8 }), svgEl('ellipse', { cx: x + 9, cy: y + 4, rx: 2.4, ry: 1.4, fill: '#ff9db8', 'fill-opacity': 0.8 }),
  svgEl('path', { d: `M${x - 3} ${y + 4}q3 3 6 0`, fill: 'none', stroke: '#1b2440', 'stroke-width': 1.4, 'stroke-linecap': 'round' }),
];

export function dimIcon(dim) {
  const svg = svgEl('svg', { viewBox: '0 0 40 40', width: 28, height: 28, class: 'dim-ico dim-ico-' + dim, 'aria-hidden': 'true', focusable: 'false' });
  if (dim === '2d') {
    svg.append(svgEl('rect', { x: 5, y: 7, width: 30, height: 26, rx: 7, fill: '#8be9ff', stroke: '#1b2440', 'stroke-width': 1.6 }), ...FACE(20, 19));
  } else {
    svg.append(
      svgEl('path', { d: 'M20 4 35 12v16L20 36 5 28V12z', fill: '#c9b8ff', stroke: '#1b2440', 'stroke-width': 1.6, 'stroke-linejoin': 'round' }),
      svgEl('path', { d: 'M5 12 20 20 35 12', fill: 'none', stroke: '#1b2440', 'stroke-width': 1.4, 'stroke-linejoin': 'round' }),
      svgEl('path', { d: 'M20 20v16', stroke: '#1b2440', 'stroke-width': 1.4 }),
      svgEl('path', { d: 'M20 4 35 12 20 20 5 12z', fill: '#e6dcff', 'fill-opacity': 0.9 }),
      svgEl('g', { transform: 'translate(20 29) scale(.62) translate(-20 -29)' }, ...FACE(20, 29)));
  }
  return svg;
}

// <div data-testid="dim-toggle" data-current="2d|3d"> with <button data-dim="2d|3d">.
export function dimToggle({ current, onPick }) {
  const cur = current === '3d' ? '3d' : '2d';
  const live = el('span', { class: 'sr-only', role: 'status', 'aria-live': 'polite' }, t('dim.now', { d: cur.toUpperCase() }));
  const btn = (d) => {
    const on = d === cur;
    return el('button', { type: 'button', class: 'dim-btn' + (on ? ' on' : ''), 'data-dim': d, 'aria-pressed': on ? 'true' : 'false',
      'aria-label': on ? t('dim.now', { d: d.toUpperCase() }) : t('dim.to', { d: d.toUpperCase() }),
      title: on ? t('dim.now', { d: d.toUpperCase() }) : t('dim.to', { d: d.toUpperCase() }),
      onclick: () => { if (!on) onPick(d); } }, dimIcon(d), el('span', { class: 'dim-word' }, d.toUpperCase()));
  };
  return el('div', { class: 'dim-toggle', role: 'group', 'aria-label': t('dim.group'), 'data-testid': 'dim-toggle', 'data-current': cur }, btn('2d'), btn('3d'), live);
}
