// FR-1062 AC-343 AC-344: 全画面で使う「種類 → 区分 → 領域 → 項目」の階層の共通部品（見出し・件数・開閉・未分類・JA/EN の名称・キーボード操作）。
// 階層の導出は eabk_model.py（model.hierarchy）が 1 か所で行い、ここは描画だけを受け持つ（割り当て表を持たない）。
// 層の識別: data-tier-level = kind|division|area、data-tier-path = JSON 配列（その層までの名前）、data-count = その層の項目件数。
// 色だけに頼らない: 開閉は ▸ / ▾ の記号と aria-expanded、件数は文字で示す。
import { lang, onLang } from './i18n.js';
import { el } from './ui.js';

export const LEVELS = ['kind', 'division', 'area'];
export const UNCLASSIFIED = '未分類';

// データ上の名称は日本語（正本）。英語表示では、ここにある名称だけを訳し、ほかはデータに書かれたまま表示する。
const EN = {
  '未分類': 'Unclassified',
  '目的': 'Goals', '要求': 'Requirements', '受入基準': 'Acceptance criteria', '試験ケース': 'Test cases', 'カタログ': 'Catalog',
  'エンティティ': 'Entities', '質問': 'Questions', '出典': 'Sources', 'パラメータ': 'Parameters', '監査指摘': 'Audit findings',
  '外部連携': 'External integrations', 'users-guide': 'users-guide', 'scripts': 'scripts',
  '機能': 'Functional', '非機能': 'Non-functional', 'API・イベント': 'APIs and events', 'テーブル': 'Tables', '共通部品': 'Shared parts',
  '連携カタログ': 'Integration catalog', '状態遷移': 'State machines', 'その他': 'Other',
};
export function tierName(name, l = lang()) {
  return l === 'en' && EN[name] ? EN[name] : String(name ?? '');
}
export const tierLabel = (name, count, l = lang()) => `${tierName(name, l)} (${count})`;

/** model.hierarchy.items から 種類→区分→領域 の木を作る。順序は model.hierarchy.tiers（導出側の順）に従う。 */
export function buildTree(hier, filter) {
  const items = (hier?.items || []).filter((i) => !filter || filter(i));
  const byPath = new Map();
  for (const it of items) {
    const k = JSON.stringify([it.kind, it.division, it.area]);
    (byPath.get(k) || byPath.set(k, []).get(k)).push(it);
  }
  const order = (hier?.tiers || []).map((t) => JSON.stringify(t.path));
  const keys = [...byPath.keys()].sort((a, b) => {
    const ia = order.indexOf(a), ib = order.indexOf(b);
    return (ia < 0 ? 1e9 : ia) - (ib < 0 ? 1e9 : ib);
  });
  const root = { children: new Map(), count: 0 };
  // 項目が 0 件でも見出しを示したい層（hier.empty = [[種類, 区分, 領域], ...]）。件数 0 の見出しとして現れる（FR-1063: 空の画面でも層を明示）。
  for (const [kind, division, area] of hier?.empty || []) {
    let cur = root;
    for (const [name, level] of [[kind, 'kind'], [division, 'division'], [area, 'area']]) {
      let ch = cur.children.get(name);
      if (!ch) cur.children.set(name, (ch = { name, level, children: new Map(), items: [], count: 0 }));
      cur = ch;
    }
  }
  for (const k of keys) {
    const [kind, division, area] = JSON.parse(k);
    let cur = root;
    cur.count += byPath.get(k).length;
    for (const [name, level] of [[kind, 'kind'], [division, 'division'], [area, 'area']]) {
      let ch = cur.children.get(name);
      if (!ch) cur.children.set(name, (ch = { name, level, children: new Map(), items: [], count: 0 }));
      ch.count += byPath.get(k).length;
      cur = ch;
    }
    cur.items.push(...byPath.get(k));
  }
  return root;
}

/**
 * 階層を DOM にする。
 * opts: { filter, itemNode(item) -> Node, open(path, level) -> bool, extra(node, path) -> Node|null（層ごとの付加情報。実装状態の内訳など）,
 *         onToggle(path, open) }
 * 返す要素は言語の切替で名称を更新する（要素が外れたら購読を解除する）。
 */
export function renderTiers(hier, opts = {}) {
  const tree = buildTree(hier, opts.filter);
  const wrap = el('div', { class: 'tiers', role: 'tree', 'aria-label': lang() === 'en' ? 'Data hierarchy' : 'データの階層' });
  const relabel = [];
  let seq = 0;

  const group = (node, path, depth) => {
    const open = opts.open ? !!opts.open(path, node.level) : depth === 0;
    const bid = `tier-${Date.now().toString(36)}-${seq++}`;
    const body = el('div', { class: 'tier-body', id: bid, role: 'group' });
    const text = el('span', { class: 'tier-name' });
    const num = el('span', { class: 'tier-count' });
    const mark = el('span', { class: 'tier-mark', 'aria-hidden': 'true' });
    const btn = el('button', { type: 'button', class: 'tier-toggle', 'data-testid': 'tier-toggle', 'aria-expanded': String(open), 'aria-controls': bid }, mark, text, num);
    const head = el('div', { class: 'tier-head', role: 'heading', 'aria-level': String(depth + 2) }, btn);
    const g = el('div', {
      class: `tier-group tier-${node.level}${node.name === UNCLASSIFIED ? ' tier-unclassified' : ''}`, role: 'treeitem', 'aria-expanded': String(open),
      'data-testid': 'tier-group', 'data-tier-level': node.level, 'data-tier-path': JSON.stringify(path), 'data-count': String(node.count),
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
      num.textContent = ` (${node.count})`;
      btn.setAttribute('aria-label', tierLabel(node.name, node.count));
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
    wrap.setAttribute('aria-label', lang() === 'en' ? 'Data hierarchy' : 'データの階層');
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
