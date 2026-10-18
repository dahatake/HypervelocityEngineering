// FR-1063 AC-348 AC-349: 一覧・表・実装状態・ダッシュボードなどの画面で、行・項目を FR-1062 の上位層（種類→区分→領域）の見出しの下にまとめる薄い橋渡し。
// 階層の導出は model.hierarchy（eabk_model.py 1 か所）、見出し・件数・開閉・キーボード・JA/EN は hier.js の renderTiers に任せ、ここでは再実装しない。
// 開閉の状態は一覧系の画面のあいだで共有し、画面を切り替えても保たれる（NFR-UX-006）。
import { renderTiers, UNCLASSIFIED } from './hier.js';
import { store } from './store.js';
import { tierState } from './maptiers.js';   // 開閉の状態は、マップ（2D・3D・RPG 風）とも共有する（NFR-UX-006）

const keyOf = (path) => JSON.stringify(path);

/** 現在のモデルの階層（なければ空）。 */
export const hierarchy = () => store.model?.hierarchy || { items: [], tiers: [], unclassified: UNCLASSIFIED };

/**
 * 行を階層の項目に対応づける。spec(row) -> { kind, id, division? }（FR-1062 の (種類, ID) と、必要なら区分）。
 * 階層に見つからない行は fallbackKind の下の「未分類」に置く（隠さず・他の領域に混ぜない: AC-351）。
 */
export function placeRows(rows, spec, fallbackKind) {
  const idx = new Map();
  for (const it of hierarchy().items) {
    const k = `${it.kind}\u0000${it.id}`;
    (idx.get(k) || idx.set(k, []).get(k)).push(it);
  }
  return rows.map((row) => {
    const s = spec(row) || {};
    const hits = idx.get(`${s.kind}\u0000${s.id}`) || [];
    const hit = (s.division && hits.find((h) => h.division === s.division)) || hits[0];
    if (hit) return { kind: hit.kind, division: hit.division, area: hit.area, id: hit.id, row };
    // fallbackKind は文字列、または row -> [種類, 区分, 領域]。階層に載らないデータは明示の「未分類」に置く。
    const [kind, division, area] = typeof fallbackKind === 'function' ? fallbackKind(row) : [fallbackKind, UNCLASSIFIED, UNCLASSIFIED];
    return { kind, division: division || UNCLASSIFIED, area: area || UNCLASSIFIED, id: String(s.id ?? ''), row };
  });
}

/**
 * items（kind・division・area を持つ項目）を、見出し・件数つきの開閉できる階層にする。
 * opts: { itemNode, extra, openAreas（領域を既定で開くか）, label }。
 */
export function listTiers(items, opts = {}) {
  const h = hierarchy();
  const w = renderTiers({ items, tiers: h.tiers, empty: opts.empty }, {
    itemNode: opts.itemNode || (() => document.createDocumentFragment()),
    extra: opts.extra,
    open: (path, level) => (tierState.has(path) ? tierState.get(path) : (opts.openPaths && opts.openPaths.has(keyOf(path))) || level !== 'area' || !!opts.openAreas),
    onToggle: (path, open) => tierState.setOpen(path, open, 'list'),
  });
  w.classList.add('tiers-list');
  // FR-1051 の種別グループ（role=group、画面内の数を検査される）と混ざらないよう、上位層の本体は role=group にしない。
  // 開閉は見出しのボタンの aria-expanded / aria-controls と、層の treeitem の aria-expanded で伝わる。
  w.querySelectorAll('.tier-body[role="group"]').forEach((b) => b.removeAttribute('role'));
  return w;
}
