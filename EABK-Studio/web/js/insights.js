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
  const runtime = store.model.analysis.runtime;
  const box = (item) => el('article', { class: 'runtime-node card' },
    el('h3', {}, item.name), el('p', {}, `実行場所: ${item.runsAt}`),
    el('p', {}, `データの所在: ${item.data}`), el('p', { class: 'mini mono' }, `根拠: ${item.source}`));
  return el('section', { class: 'visual-section' }, el('h1', {}, 'アプリ構成とデータ位置づけ'),
    el('p', { class: 'sub' }, '解析した管理データと実装登録に基づく実行環境・コード・格納位置・明示境界'),
    el('div', { class: 'runtime-flow' }, runtime.components.map(box)),
    el('div', { class: 'tw' }, el('table', { class: 't' },
      el('thead', {}, el('tr', {}, ['送信元', '送信先', '方向', '対象データ', '根拠'].map((x) => el('th', {}, x)))),
      el('tbody', {}, runtime.flows.map((flow) => el('tr', {},
        el('td', {}, flow.from), el('td', {}, flow.to), el('td', {}, flow.direction),
        el('td', {}, flow.data), el('td', { class: 'mono' }, flow.source)))))),
    el('div', { class: 'card boundary' }, el('h3', {}, '外部／クラウド境界'),
      runtime.boundaries.length
        ? runtime.boundaries.map((x) => el('p', {},
          el('b', {}, x.name), ` / 方式: ${x.method || '未記載'} / 方向: ${x.direction || '未記載'} / 正本: ${x.owner || '未記載'} / 外部送信`,
          el('span', { class: 'mono' }, ` / 根拠: ${x.source}`)))
        : el('p', {}, 'なし'),
      el('p', {}, `書込: なし　外部送信: ${runtime.externalSend.length ? '定義あり' : 'なし'}`)));
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
  const recordLabel = (record) => record.id || record['run-id'] || record.target || record.name || record.label || 'record';
  const sourceLabel = (record) => [record.file, record.line].filter(Boolean).join(':');
  const evidence = (title, groups) => {
    const count = groups.reduce((n, group) => n + group.records.length, 0);
    const open = () => {
      const drawer = document.getElementById('drawer');
      drawer.hidden = true;
      drawer.style.left = '8px';
      drawer.style.right = 'auto';
      drawer.style.width = 'min(440px, 35vw)';
      drawer.replaceChildren(el('h2', {}, `${title}の根拠レコード`),
        ...groups.map((group) => el('section', {},
          el('h3', {}, `${group.label} (${group.records.length})`),
          group.records.length
            ? el('ul', {}, group.records.map((record) => el('li', {},
              el('b', {}, recordLabel(record)), sourceLabel(record) ? ` — ${sourceLabel(record)}` : '',
              record.status ? ` — ${record.status}` : '')))
            : el('p', { class: 'empty' }, '該当レコードなし'))),
        el('button', { class: 'btn', onclick: () => (drawer.hidden = true) }, '閉じる'));
      drawer.hidden = false;
    };
    return el('figure', { class: 'card evidence-chart', 'aria-label': title },
      el('figcaption', {}, title),
      el('button', { role: 'button', class: 'chart-button', onclick: open },
        `${groups.length} 集計 / ${count} 件 — 根拠レコードを表示`),
      el('div', { class: 'dimension-list' }, groups.map((group) =>
        el('span', { class: 'badge' }, `${group.label}: ${group.records.length}`))));
  };
  const by = (records, key) => Object.entries(records.reduce((out, record) => {
    const label = key(record) || '未分類';
    (out[label] ||= []).push(record);
    return out;
  }, {})).map(([label, records]) => ({ label, records }));
  const goalGroups = by(m.reqs, (r) => r.goal);
  const typeGroups = by([...store.nodes.values()], (n) => n.type);
  return el('section', { class: 'visual-section' }, el('h2', {}, '設計・開発履歴と進捗'),
    el('p', { class: 'sub' }, `測定時点: ${m.meta.generatedAt} · 時系列 / 状態別`),
    el('div', { class: 'dimension-list' },
      el('span', { class: 'badge' }, `決定記録 ${m.decisions.length}`),
      el('span', { class: 'badge' }, `実行履歴 ${m.runs.length}`),
      ...by(m.reqs, (r) => `要求状態 ${r.statusKind}`).map((x) => el('span', { class: 'badge' }, `${x.label} ${x.records.length}`)),
      el('span', { class: 'badge' }, `実装登録 ${m.catalog.features.filter((f) => f.impl.length).length}`),
      ...by(m.cases, (c) => `System Test ${c.status || '未設定'}`).map((x) => el('span', { class: 'badge' }, `${x.label} ${x.records.length}`))),
    el('div', { class: 'progress-summary' }, el('span', {}, 'System Test 合格 '),
      el('strong', { 'data-testid': 'system-test-pass-count' }, String(pass)),
      el('span', {}, ` / ${m.cases.length}（not_run は合格に含めない）`)),
    el('div', { class: 'grid cols2' },
      evidence('目的', goalGroups),
      evidence('データ種別', typeGroups)));
}

export function mountStructure(host) {
  const analysis = store.model.analysis.structure;
  const page = el('div', { class: 'page' }, el('h1', {}, '全データ層の現状対理想構造'),
    el('p', { class: 'sub' }, '解析済みの現状構造 と 構造判定表から導いた理想構造を層ごとに比較'),
    el('div', { class: 'grid cols2 layer-list' }, analysis.layers.map((layer) =>
      el('article', { class: 'card' }, el('h2', {}, layer.name),
        el('p', {}, `現状: ${layer.actual}`), el('p', {}, `理想: ${layer.ideal}`),
        el('p', { class: 'mini mono' }, `根拠: ${layer.source}`)))),
    el('div', { class: 'tw' }, el('table', { class: 't' },
      el('thead', {}, el('tr', {}, ['データ層', '差分種別', '対象 ID / 位置', '現状', '理想', '適用規則', '判定理由', '根拠'].map((x) => el('th', {}, x)))),
      el('tbody', {}, analysis.differences.map((diff) => el('tr', {},
        el('td', {}, diff.layer), el('td', {}, diff.kind), el('td', {}, diff.target),
        el('td', {}, diff.actual), el('td', {}, diff.ideal), el('td', {}, diff.rule),
        el('td', {}, diff.reason), el('td', { class: 'mono' }, diff.source)))))));
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
