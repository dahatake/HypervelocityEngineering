// FR-1091 / FR-1092: the tabs of the Source screen — [See how functions relate] and [Source map].
// Every screen of the Source item shows the same tabs; the current one is marked by shape (underline, bold) as well as colour.
import { t } from './i18n.js';
import { el } from './ui.js';

export function sourceTabs(active) {
  const tab = (id, href, label) => el('a', { role: 'tab', href, class: 'src-tab' + (active === id ? ' on' : ''), 'aria-selected': String(active === id), 'data-testid': 'src-tab-' + id }, label);
  return el('nav', { class: 'src-tabs', role: 'tablist', 'aria-label': t('src.tabs') },
    tab('functions', '#/floorplan', t('src.tab.functions')), tab('map', '#/source', t('src.tab.map')));
}
