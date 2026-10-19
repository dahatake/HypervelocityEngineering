// FR-1063 AC-345 AC-346 AC-347: マップ（2D・3D・RPG 風）に出す上位層（種類→区分→領域→項目）の表示。
// 導出は model.hierarchy（FR-1062）で、描画は hier.js の renderTiers を使う。ここは地図用の置き場（パネル・会話ウィンドウ内）と、項目の選択への接続だけを持つ。
// 開閉状態は画面（2D・3D・RPG 風）をまたいで保つ（NFR-UX-006）。
import { lang, onLang } from './i18n.js';
import { store } from './store.js';
import { el } from './ui.js';
import { xrefLink } from './xref.js';
import { renderTiers, tierName } from './hier.js';

const opened = new Map();   // JSON(path) -> bool（利用者が開閉した状態。画面を切り替えても保つ）
const defaultOpen = () => true;   // 地図本体の既定（領域を開いて点を並べる）と同じにする
const isOpen = (path, level) => (opened.has(JSON.stringify(path)) ? opened.get(JSON.stringify(path)) : defaultOpen(path, level));

// 地図本体（2D・3D の層ごとの列・円盤）とパネルが同じ開閉状態を使う。地図は、利用者が畳むまで領域を開いて点を並べる。
const subs = new Set();
export const tierState = {
  has: (path) => opened.has(JSON.stringify(path)),
  get: (path) => opened.get(JSON.stringify(path)),
  mapOpen: (path) => (opened.has(JSON.stringify(path)) ? opened.get(JSON.stringify(path)) : true),
  setOpen(path, open, src) { opened.set(JSON.stringify(path), !!open); for (const f of [...subs]) f(path, !!open, src); },
  toggle(path, src) { this.setOpen(path, !this.mapOpen(path), src); },
  on(fn) { subs.add(fn); return () => subs.delete(fn); },
};

// 地図の点（ノード）→ 階層の項目（FR-1062 の導出。ここでは割り当てを持たない）
const idx = new WeakMap();
const KIND_OF_TYPE = { req: '要求', ac: '受入基準', case: '試験ケース', goal: '目的', param: 'パラメータ', question: '質問', entity: 'エンティティ' };
function indexOf(hier) {
  let m = idx.get(hier);
  if (!m) {
    const byId = new Map();
    for (const i of hier.items) (byId.get(i.id) || byId.set(i.id, []).get(i.id)).push(i);   // 同じ ID が複数の種類に現れる（要求とカタログの行など）
    m = { byId, order: new Map((hier.tiers || []).map((t, i) => [JSON.stringify(t.path), i])) };
    idx.set(hier, m);
  }
  return m;
}
/** 点の上位層の経路 [種類, 区分, 領域]。階層に項目がない点（部品・API・テーブルなど）は null。 */
export function tierPathOf(n) {
  const hier = store.model?.hierarchy;
  if (!hier?.items?.length || !n) return null;
  const { byId } = indexOf(hier);
  const list = byId.get(n.id) || byId.get(String(n.id).replace(/^(ent|file):/, ''));
  if (!list) return null;
  const want = KIND_OF_TYPE[n.type];
  const it = (want && list.find((i) => i.kind === want)) || (want ? null : list[0]);
  return it ? [it.kind, it.division, it.area] : null;
}
/** 導出側の順序（tiers の並び）での位置。ない経路は大きい値。 */
export function tierRank(path) {
  const hier = store.model?.hierarchy;
  if (!hier?.tiers || !path) return 1e9;
  const r = indexOf(hier).order.get(JSON.stringify(path));
  return r == null ? 1e9 : r;
}
export const tierKey = (path) => 'T:' + JSON.stringify(path);
export const tierOfKey = (key) => (typeof key === 'string' && key.startsWith('T:') ? JSON.parse(key.slice(2)) : null);
/** 地図の見出し用の名称（種類 › 区分 › 領域。区分が種類と同じなら省く）。 */
export function tierPathLabel(path) {
  const [kind, division, area] = path;
  return [kind, division !== kind ? division : null, area].filter(Boolean).map((x) => tierName(x)).join(' › ');
}
/** 地図の見出し用の短い名称（区分 › 領域）。3D のラベル用。 */
export function tierShortLabel(path) {
  const [kind, division, area] = path;
  return [division !== kind ? division : null, area].filter(Boolean).map((x) => tierName(x)).join(' › ');
}

const TXT = {
  ja: { title: '上位層（種類→区分→領域）', items: '項目', none: '上位層のデータがありません。', close: '閉じる', dlg: '項目の上位層（種類→区分→領域→項目）' },
  en: { title: 'Tiers (kind → division → area)', items: 'items', none: 'No tier data.', close: 'Close', dlg: 'Item tiers (kind → division → area → item)' },
};
const tx = (k) => (TXT[lang()] || TXT.ja)[k];

/** 項目 1 件の表示: ID と題名のボタン。マップに点があれば、その点を選択する（なければ表示のみ）。 */
function itemNode(it) {
  // 題名はデータ由来の文字列（試験ケースの題名など）。画面の文言と区別するため、見た目は data-title の疑似要素で出し、支援技術には aria-label で ID と題名を伝える。
  // FR-1031 AC-188: 実在する ID はリンク（xrefLink）。押すとその点を選択し、詳細へ移る（リンクの移動先と同じ対象）。
  const can = !!store.node?.(it.id);
  const idEl = can ? xrefLink(it.id, it.id) : el('span', { class: 'tier-item-id' }, it.id);
  const b = el('div', { class: 'maptier-item', 'data-testid': 'tier-item', 'data-id': it.id, 'data-title': it.title ? ` ${it.title}` : null, role: 'treeitem' }, idEl);
  if (can) b.addEventListener('click', (e) => { if (e.target.closest('a')) { e.preventDefault(); } store.select(it.id); });
  return b;
}

/** 上位層の木（renderTiers）を地図用の設定で作る。 */
export function mapTiers(filter) {
  const hier = store.model?.hierarchy;
  if (!hier?.items?.length) return null;
  return renderTiers(hier, { filter, open: isOpen, onToggle: (path, open) => tierState.setOpen(path, open, 'panel'), itemNode });
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
  // 地図本体の見出し・塊で開閉されたら、パネルの開閉も追従する（パネルでの操作では作り直さない）
  const off = [onLang(paint), store.on('model', build), tierState.on((p, o, src) => { if (src !== 'panel') build(); })];
  host.append(box);
  // NFR-UX-016: 地図の表示面はパネルの高さを避ける（CSS 変数 --mt-h）。パネルの開閉・幅の変化に追従する
  const syncH = () => host.style.setProperty('--mt-h', `${Math.ceil(box.getBoundingClientRect().height)}px`);
  const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(syncH) : null;
  if (ro) ro.observe(box); syncH();
  return { destroy() { off.forEach((f) => f && f()); if (ro) ro.disconnect(); host.style.removeProperty('--mt-h'); box.remove(); } };
}

/** RPG 風の会話ウィンドウ用。城・街・住人とは別に、項目の上位層だけを見せる（件数は城・街・住人に加えない）。
 *  ids を渡すと、その項目（街・住人・城に関連する要求など）だけの上位層にする。 */
export function tierDialogBody(onClose, ids, title) {
  const head = el('div', { class: 'rpg-name' }, title || tx('dlg'));
  const set = ids ? new Set(ids) : null;
  const tree = mapTiers(set ? (it) => set.has(it.id) : null) || el('p', { class: 'mini' }, tx('none'));
  const close = el('button', { type: 'button', class: 'btn ghost', 'data-testid': 'rpg-tiers-close', onclick: onClose }, tx('close'));
  const box = el('div', { class: 'rpg-tiers', 'data-testid': 'rpg-tiers' }, head, tree, close);
  const off = onLang(() => { if (!box.isConnected) { off(); return; } head.textContent = title || tx('dlg'); close.textContent = tx('close'); });
  return box;
}

export { tierName };
