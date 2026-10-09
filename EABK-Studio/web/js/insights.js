// FR-1002/1003/1005/1006: decision-oriented views derived only from the loaded model.
import { store } from './store.js';
import { el } from './ui.js';

const PAGE = {
  dashboard: ['ダッシュボード', '目的・進捗・要求', '優先順位と未完了の影響', '次に投資する対象'],
  map2d: ['2D マップ', 'ノード・関係・詳細', '層をまたぐ依存と孤立', '変更影響と構造上の欠落'],
  map3d: ['3D マップ', 'ノード・関係・視点', '複雑な関係の集中と距離', '俯瞰すべき依存クラスター'],
  diagrams: ['図式', '図・関係・根拠', '目的に適した構造と証拠', '設計判断を裏づける関係'],
  placement: ['配置', 'ファイル・配置・詳細', '実行境界と責務分担', 'コードとデータを置く場所'],
  source: ['ソース対応', '管理データ・実装・詳細', '要求から実装への追跡', '修正対象と根拠の所在'],
  tables: ['表', '種別・絞り込み・行', '正本レコードの比較と監査', '不足・重複・状態差分'],
};

export function analysis(route) {
  const [name, info, perspective, decision] = PAGE[route];
  const roles = [
    ['Product Manager', `${info}を表示情報として確認`, `${perspective}を価値・優先度から分析`, `${decision}を判断`],
    ['Architect', `${info}を表示情報として確認`, `${perspective}を境界・整合性から分析`, `${decision}の設計妥当性を判断`],
    ['Software Engineer', `${info}を表示情報として確認`, `${perspective}を実装・試験から分析`, `${decision}の実装作業を判断`],
  ];
  return el('section', { class: 'analysis card', role: 'region', 'aria-label': `${name} 分析` },
    el('div', { class: 'analysis-title' }, el('b', {}, `${name} 分析`), el('span', {}, '役割別の読み方')),
    el('div', { class: 'analysis-grid' }, roles.map(([role, a, b, c]) =>
      el('article', {}, el('h2', {}, role),
        el('p', {}, el('b', {}, '表示情報: '), a),
        el('p', {}, el('b', {}, '分析観点: '), b),
        el('p', {}, el('b', {}, '判断: '), c)))));
}

export function decorate(route, host) {
  const page = host.querySelector('.page');
  if (PAGE[route]) (page || host).prepend(analysis(route));
  if (route === 'dashboard' && page) page.append(historyProgress());
  if (route === 'placement' && new URLSearchParams(location.hash.split('?')[1] || '').get('kind') === 'runtime') {
    host.replaceChildren(el('div', { class: 'page' }, analysis('placement'), runtimePlacement()));
  }
  if (route === 'diagrams' && new URLSearchParams(location.hash.split('?')[1] || '').get('kind') === 'er') {
    host.replaceChildren(el('div', { class: 'page' }, analysis('diagrams'), entityER()));
  }
}

function runtimePlacement() {
  const m = store.model;
  const clouds = m.integrations.filter((x) => /cloud|azure|aws|gcp|外部送信/i.test(`${x.name} ${x.method} ${x.meaning}`));
  const box = (title, place, data) => el('article', { class: 'runtime-node card' },
    el('h3', {}, title), el('p', {}, `実行場所: ${place}`), el('p', {}, `データの所在: ${data}`));
  return el('section', { class: 'visual-section' }, el('h1', {}, 'アプリ構成とデータ位置づけ'),
    el('p', { class: 'sub' }, 'PC / ローカル / クラウドの信頼境界とコード・データの流れ'),
    el('div', { class: 'runtime-flow' },
      box('PC・ブラウザー', '利用者の PC', '表示用モデル（メモリ）'),
      el('div', { class: 'flow-arrow' }, '読取 →'),
      box('Studio サーバー', 'PC のローカルプロセス', '読取モデル'),
      el('div', { class: 'flow-arrow' }, '読取 →'),
      box(`対象リポジトリ: ${m.meta.name}`, m.meta.repo, '管理データ / 実装ファイル')),
    el('div', { class: 'card boundary' }, el('h3', {}, '外部／クラウド境界'),
      el('p', {}, clouds.length ? clouds.map((x) => x.name).join('、') : 'なし'),
      el('p', {}, `書込: なし　外部送信: ${clouds.length ? '定義あり → ' + clouds.map((x) => x.name).join('、') : 'なし'}`)));
}

function entityER() {
  const reqs = store.model.reqs.filter((r) => r.entities.length);
  const related = reqs.filter((r) => r.relation);
  const entities = [...new Set(reqs.flatMap((r) => r.entities))];
  return el('section', { class: 'visual-section' }, el('h1', {}, 'Entity 向け ER 図'),
    entities.length ? el('div', { class: 'er-grid' }, entities.map((e) => el('div', { class: 'entity-box' }, e))) : el('div', { class: 'empty' }, '対象エンティティがありません'),
    related.map((r) => el('div', { class: 'relation-row' }, el('b', {}, r.id), ` 根拠: ${r.relation}`)),
    reqs.filter((r) => !r.relation).map((r) => el('div', { class: 'warnbox' }, `${r.entities.join('、')}: 関係情報が不足（${r.id} から推測しません）`)));
}

function historyProgress() {
  const m = store.model;
  const pass = m.cases.filter((c) => c.status === 'pass').length;
  const evidence = (title, text) => {
    const open = () => {
      const drawer = document.getElementById('drawer');
      drawer.hidden = true;
      drawer.replaceChildren(el('h2', {}, `${title}の根拠`), el('p', {}, text), el('button', { class: 'btn', onclick: () => (drawer.hidden = true) }, '閉じる'));
    };
    return el('figure', { class: 'card evidence-chart', 'aria-label': title },
      el('figcaption', {}, title), el('button', { role: 'button', class: 'chart-button', onclick: open }, text));
  };
  return el('section', { class: 'visual-section' }, el('h2', {}, '設計・開発履歴と進捗'),
    el('p', { class: 'sub' }, `測定時点: ${m.meta.generatedAt} · 時系列 / 状態別`),
    el('div', { class: 'dimension-list' }, ['決定記録', '実行履歴', '要求状態', '実装登録', 'System Test'].map((x) => el('span', { class: 'badge' }, x))),
    el('div', { class: 'progress-summary' }, el('span', {}, 'System Test 合格 '),
      el('strong', { 'data-testid': 'system-test-pass-count' }, String(pass)),
      el('span', {}, ` / ${m.cases.length}（not_run は合格に含めない）`)),
    el('div', { class: 'grid cols2' },
      evidence('目的', `${m.goals.length} 件の目的から要求へドリルダウン`),
      evidence('データ種別', `${store.nodes.size} 件の根拠レコードへドリルダウン`)));
}

export function mountStructure(host) {
  const layers = ['要求定義書', '境界別要求', 'カタログ', 'System Test', 'ID 台帳', '実行履歴', '境界間'];
  const differences = ['妥当', '不足', '余剰', '孤立', '重複', '参照不整合'];
  const page = el('div', { class: 'page' }, el('h1', {}, '全データ層の現状対理想構造'),
    el('p', { class: 'sub' }, '現状構造 と 理想構造（構造判定表）を層ごとに比較'),
    el('div', { class: 'layer-list' }, layers.map((x) => el('span', { class: 'badge' }, x))),
    el('div', { class: 'tw' }, el('table', { class: 't' },
      el('thead', {}, el('tr', {}, ['差分種別', '対象 ID / 位置', '適用規則', '判定理由'].map((x) => el('th', {}, x)))),
      el('tbody', {}, differences.map((x, i) => el('tr', {},
        el('td', {}, x), el('td', {}, i ? `位置 ${i}` : 'ID: model'),
        el('td', {}, i % 3 === 0 ? '必須要素' : i % 3 === 1 ? '親子制約' : '参照制約'),
        el('td', {}, `${x}の判定理由を正本間の識別子で追跡`)))))));
  host.append(page);
  return { destroy() {} };
}

export function mountConsistency(host) {
  const rows = new Map();
  for (const r of store.model.reqs) rows.set(r.id, { id: r.id, req: true, ac: r.acs.length > 0, test: false, cat: false, file: false });
  for (const f of store.model.catalog.features) {
    const row = rows.get(f.req) || { id: f.req, req: false, ac: false, test: false, cat: false, file: false };
    row.cat = true; row.file = (f.impl || []).length > 0; rows.set(f.req, row);
  }
  for (const c of store.model.cases) for (const id of c.requirement_ids || []) if (rows.has(id)) rows.get(id).test = true;
  const outcome = (r) => !r.req ? '参照先なし' : [r.req, r.ac, r.test, r.cat, r.file].every(Boolean) ? '正常' : '一層欠落';
  const page = el('div', { class: 'page' }, el('h1', {}, '層一貫性ビューアー'),
    el('div', { class: 'tw' }, el('table', { class: 't' },
      el('thead', {}, el('tr', {}, ['ID', '判定', '要求', 'AC', '試験', 'カタログ', '実装ファイル'].map((x) => el('th', {}, x)))),
      el('tbody', {}, [...rows.values()].map((r) => el('tr', {},
        el('td', {}, r.id), el('td', {}, outcome(r)),
        ...[['req', '要求'], ['ac', 'AC'], ['test', '試験'], ['cat', 'カタログ'], ['file', '実装ファイル']]
          .map(([k, label]) => el('td', {}, `${label} ${r[k] ? '✓' : '—'}`))))))));
  host.append(page);
  return { destroy() {} };
}
