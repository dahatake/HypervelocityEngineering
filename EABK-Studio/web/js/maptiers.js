// FR-1063 AC-345 AC-346 AC-347: マップ（2D・3D・RPG 風）に出す上位層（種類→区分→領域→項目）の表示。
// 導出は model.hierarchy（FR-1062）で、描画は hier.js の renderTiers を使う。ここは地図用の置き場（パネル・会話ウィンドウ内）と、項目の選択への接続だけを持つ。
// 開閉状態は画面（2D・3D・RPG 風）をまたいで保つ（NFR-UX-006）。
import { lang, onLang } from './i18n.js';
import { store } from './store.js';
import { el } from './ui.js';
import { renderTiers, tierName } from './hier.js';

const opened = new Map();   // JSON(path) -> bool（利用者が開閉した状態。画面を切り替えても保つ）
const defaultOpen = (path, level) => (level === 'area' ? false : true);
const isOpen = (path, level) => (opened.has(JSON.stringify(path)) ? opened.get(JSON.stringify(path)) : defaultOpen(path, level));

const TXT = {
  ja: { title: '上位層（種類→区分→領域）', items: '項目', none: '上位層のデータがありません。', close: '閉じる', dlg: '項目の上位層（種類→区分→領域→項目）' },
  en: { title: 'Tiers (kind → division → area)', items: 'items', none: 'No tier data.', close: 'Close', dlg: 'Item tiers (kind → division → area → item)' },
};
const tx = (k) => (TXT[lang()] || TXT.ja)[k];

/** 項目 1 件の表示: ID と題名のボタン。マップに点があれば、その点を選択する（なければ表示のみ）。 */
function itemNode(it) {
  const label = [el('span', { class: 'tier-item-id' }, it.id), it.title ? el('span', { class: 'tier-item-title' }, ` ${it.title}`) : null];
  const can = !!store.node?.(it.id);
  const b = el('button', { type: 'button', class: 'maptier-item', 'data-testid': 'tier-item', 'data-id': it.id, role: 'treeitem', disabled: can ? null : true,
    onclick: () => { if (can) store.select(it.id); } }, ...label);
  return b;
}

/** 上位層の木（renderTiers）を地図用の設定で作る。 */
export function mapTiers() {
  const hier = store.model?.hierarchy;
  if (!hier?.items?.length) return null;
  return renderTiers(hier, { open: isOpen, onToggle: (path, open) => opened.set(JSON.stringify(path), open), itemNode });
}

/** 2D・3D のパネル。host（地図の親要素）の隅に置く。同じ構成を 2D と 3D の両方で出す。 */
export function mountMapTiers(host, mode) {
  const body = el('div', { class: 'maptiers-body' });
  const sum = el('summary', { class: 'maptiers-sum' });
  const box = el('details', { class: 'maptiers', 'data-testid': 'map-tiers', 'data-mode': mode, open: true }, sum, body);
  const total = () => store.model?.hierarchy?.items?.length || 0;
  const paint = () => { sum.textContent = `${tx('title')} · ${total()} ${tx('items')}`; };
  const build = () => {
    paint();
    const tree = mapTiers();
    body.replaceChildren(tree || el('p', { class: 'mini' }, tx('none')));
  };
  build();
  const off = [onLang(paint), store.on('model', build)];
  host.append(box);
  return { destroy() { off.forEach((f) => f && f()); box.remove(); } };
}

/** RPG 風の会話ウィンドウ用。城・街・住人とは別に、項目の上位層だけを見せる（件数は城・街・住人に加えない）。 */
export function tierDialogBody(onClose) {
  const head = el('div', { class: 'rpg-name' }, tx('dlg'));
  const tree = mapTiers() || el('p', { class: 'mini' }, tx('none'));
  const close = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'rpg-tiers-close', onclick: onClose }, tx('close'));
  const box = el('div', { class: 'rpg-tiers', 'data-testid': 'rpg-tiers' }, head, tree, close);
  const off = onLang(() => { if (!box.isConnected) { off(); return; } head.textContent = tx('dlg'); close.textContent = tx('close'); });
  return box;
}

export { tierName };
