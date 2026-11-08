// FR-1062 AC-343 AC-344: 全画面で使う「種類 → 区分 → 領域 → 項目」の階層の共通部品（見出し・件数・開閉・未分類・JA/EN の名称・キーボード操作）。
// 階層の導出は eabk_model.py（model.hierarchy）が 1 か所で行い、ここは描画だけを受け持つ（割り当て表を持たない）。
// 層の識別: data-tier-level = kind|division|area、data-tier-path = JSON 配列（その層までの名前）、data-count = その層の項目件数。
// 色だけに頼らない: 開閉は ▸ / ▾ の記号と aria-expanded、件数は文字で示す。
import { lang, onLang, t } from './i18n.js';
import { el } from './ui.js';

export const LEVELS = ['kind', 'division', 'area'];
// i18n-data: the managed-data value for "not classified"
export const UNCLASSIFIED = '未分類';

// データ上の名称は日本語（正本）。表示する名称は辞書（tier.n.*）を通す。ここにない名称は、データに書かれたまま表示する。
// i18n-data-begin: the keys of this table are managed-data values (the names of the hierarchy), not display text
const TIER_KEY = {
  '未分類': 'unclassified',
  '目的': 'goals', '要求': 'reqs', '受入基準': 'acs', '試験ケース': 'cases', 'カタログ': 'catalog',
  'エンティティ': 'entities', '質問': 'questions', '出典': 'sources', 'パラメータ': 'params', '監査指摘': 'audit',
  '外部連携': 'integrations',
  '機能': 'functional', '非機能': 'nonfunctional', 'API・イベント': 'apis', 'テーブル': 'tables', '共通部品': 'shared',
  '連携カタログ': 'intcat', '状態遷移': 'states', 'その他': 'other',
};   // i18n-data-end
export function tierName(name, l = lang()) {
  const k = TIER_KEY[name];
  return k && l === lang() ? t('tier.n.' + k) : String(name ?? '');
}
export const tierLabel = (name, count, l = lang(), shown = count) =>
  `${tierName(name, l)} (${count})${shown !== count ? ', ' + t('tier.shown', { n: shown }) : ''}`;

/** model.hierarchy.items から 種類→区分→領域 の木を作る。順序は model.hierarchy.tiers（導出側の順）に従う。 */
export function buildTree(hier, filter) {
  const items = (hier?.items || []).filter((i) => !filter || filter(i));
  const byPath = new Map();
  for (const it of items) {
    const k = JSON.stringify([it.kind, it.division, it.area]);
    (byPath.get(k) || byPath.set(k, []).get(k)).push(it);
  }
  const order = (hier?.tiers || []).map((t) => JSON.stringify(t.path));
  // FR-1063 AC-350: 件数・名称・順序の正本は FR-1062 の導出（hier.tiers）。画面が項目を絞っても、層の件数（count）は導出の件数、表示している件数は shown に分ける。
  const derived = new Map();   // JSON(path 接頭辞) -> 導出の件数
  const derivedKinds = new Set();
  for (const t of hier?.tiers || []) {
    derivedKinds.add(t.path[0]);
    for (let n = 1; n <= t.path.length; n++) { const k = JSON.stringify(t.path.slice(0, n)); derived.set(k, (derived.get(k) || 0) + t.count); }
  }
  const root = { children: new Map(), count: 0, shown: 0 };
  const touch = (path) => {
    let cur = root;
    path.forEach((name, i) => {
      let ch = cur.children.get(name);
      if (!ch) cur.children.set(name, (ch = { name, level: LEVELS[i], children: new Map(), items: [], count: 0, shown: 0 }));
      cur = ch;
    });
    return cur;
  };
  // 画面が扱う種類（項目がある種類）では、導出の層をすべて並べる。絞り込みで 0 件になった層も、名称・順序・件数が他の画面と同じになる。
  const kindsHere = new Set(items.map((i) => i.kind));
  if (hier?.tiers) for (const t of hier.tiers) if (kindsHere.has(t.path[0])) touch(t.path);
  const keys = [...byPath.keys()].sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib);
  });
  // 項目が 0 件でも見出しを示したい層（hier.empty = [[種類, 区分, 領域], ...]）。件数 0 の見出しとして現れる（FR-1063: 空の画面でも層を明示）。
  for (const [kind, division, area] of hier?.empty || []) touch([kind, division, area]);
  for (const k of keys) {
    const path = JSON.parse(k);
    const n = byPath.get(k).length;
    root.shown += n;
    let cur = root;
    for (let i = 0; i < 3; i++) { cur = touch(path.slice(0, i + 1)); cur.shown += n; }
    cur.items.push(...byPath.get(k));
  }
  const fin = (node, path) => {
    for (const ch of node.children.values()) {
      const p = [...path, ch.name];
      fin(ch, p);
      ch.count = ch.children.size ? [...ch.children.values()].reduce((s, c) => s + c.count, 0) : (derived.has(JSON.stringify(p)) ? derived.get(JSON.stringify(p)) : ch.shown);
    }
  };
  fin(root, []);
  root.count = root.shown;
  return root;
}

const bootId = Date.now().toString(36);
let tierSeq = 0;

/**
 * 階層を DOM にする。
 * opts: { filter, itemNode(item) -> Node, open(path, level) -> bool, extra(node, path) -> Node|null（層ごとの付加情報。実装状態の内訳など）,
 *         onToggle(path, open) }
 * 返す要素は言語の切替で名称を更新する（要素が外れたら購読を解除する）。
 */
export function renderTiers(hier, opts = {}) {
  const tree = buildTree(hier, opts.filter);
  const wrap = el('div', { class: 'tiers', role: 'tree', 'aria-label': t('tier.tree') });
  const relabel = [];
  const group = (node, path, depth) => {
    const open = opts.open ? !!opts.open(path, node.level) : depth === 0;
    const bid = `tier-${bootId}-${tierSeq++}`;   // モジュール全体の連番（呼び出しをまたいでも重複しない）
    const body = el('div', { class: 'tier-body', id: bid, role: 'group' });
    const text = el('span', { class: 'tier-name' });
    const num = el('span', { class: 'tier-count' });
    const mark = el('span', { class: 'tier-mark', 'aria-hidden': 'true' });
    const btn = el('button', { type: 'button', class: 'tier-toggle', 'data-testid': 'tier-toggle', 'aria-expanded': String(open), 'aria-controls': bid }, mark, text, num);
    const head = el('div', { class: 'tier-head', role: 'heading', 'aria-level': String(depth + 2) }, btn);
    const g = el('div', {
      class: `tier-group tier-${node.level}${node.name === UNCLASSIFIED ? ' tier-unclassified' : ''}`, role: 'treeitem', 'aria-expanded': String(open),
      'data-testid': 'tier-group', 'data-tier-level': node.level, 'data-tier-path': JSON.stringify(path), 'data-count': String(node.count), 'data-shown': String(node.shown ?? node.count),
    }, head, body);
    const paint = (isOpen) => {
      btn.setAttribute('aria-expanded', String(isOpen));
      g.setAttribute('aria-expanded', String(isOpen));
      mark.textContent = isOpen ? '▾' : '▸';
      body.hidden = !isOpen;
    };
    const label = () => {
      const name = tierName(node.name);
      text.textContent = name;
      const sh = node.shown ?? node.count;
      num.textContent = sh !== node.count ? ` (${node.count}, ${t('tier.shown', { n: sh })})` : ` (${node.count})`;
      btn.setAttribute('aria-label', tierLabel(node.name, node.count, lang(), sh));
    };
    label();
    relabel.push(label);
    paint(open);
    btn.addEventListener('click', () => {
      const next = btn.getAttribute('aria-expanded') !== 'true';
      paint(next);
      if (opts.onToggle) opts.onToggle(path, next);
    });
    const extra = opts.extra && opts.extra(node, path);
    if (extra) body.append(extra);
    for (const ch of node.children.values()) body.append(group(ch, [...path, ch.name], depth + 1));
    for (const it of node.items) body.append(opts.itemNode ? opts.itemNode(it) : defaultItem(it));
    return g;
  };

  for (const ch of tree.children.values()) wrap.append(group(ch, [ch.name], 0));
  wrap.addEventListener('keydown', (e) => onKey(e, wrap));
  const off = onLang(() => {
    if (!wrap.isConnected) { off(); return; }
    wrap.setAttribute('aria-label', t('tier.tree'));
    relabel.forEach((f) => f());
  });
  wrap.dataset.total = String(tree.count);
  return wrap;
}

export function defaultItem(it) {
  return el('div', { class: 'tier-item', role: 'treeitem', 'data-testid': 'tier-item', 'data-id': it.id, tabindex: '-1' },
    el('span', { class: 'tier-item-id' }, it.id), it.title ? el('span', { class: 'tier-item-title' }, ` ${it.title}`) : null);
}

// キーボード: ↑↓ で見出しを移動、→ で開く、← で閉じる（開いていなければ親へ）、Home / End で先頭・末尾。Enter / Space はボタン本来の動作。
function onKey(e, wrap) {
  const t = e.target;
  if (!t.classList || !t.classList.contains('tier-toggle')) return;
  const all = [...wrap.querySelectorAll('.tier-toggle')].filter((b) => !b.closest('.tier-body[hidden]'));
  const i = all.indexOf(t);
  const go = (b) => { if (b) { e.preventDefault(); b.focus(); } };
  if (e.key === 'ArrowDown') go(all[i + 1]);
  else if (e.key === 'ArrowUp') go(all[i - 1]);
  else if (e.key === 'Home') go(all[0]);
  else if (e.key === 'End') go(all[all.length - 1]);
  else if (e.key === 'ArrowRight' && t.getAttribute('aria-expanded') === 'false') { e.preventDefault(); t.click(); }
  else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    if (t.getAttribute('aria-expanded') === 'true') t.click();
    else go(t.closest('.tier-body')?.parentElement?.querySelector(':scope > .tier-head .tier-toggle'));
  }
}
