// UI language (Japanese / English). Data from the repository is shown as written.
const STORE_KEY = 'eabk-studio.lang';
let current = localStorage.getItem(STORE_KEY) || ((navigator.language || 'ja').toLowerCase().startsWith('ja') ? 'ja' : 'en');
const listeners = new Set();

const D = {
  ja: {
    'nav.dashboard': 'ダッシュボード', 'nav.map2d': '2D マップ', 'nav.map3d': '3D マップ', 'nav.diagrams': '図式', 'nav.placement': '配置', 'nav.source': 'ソース対応', 'nav.tables': '表',
    'search.ph': 'ID・題名・ファイル・用語を検索…', 'repo.change': '対象リポジトリを切り替える', 'repo.prompt': 'EABK を使っているリポジトリのフォルダーのパスを入力してください',         'repo.nodata': 'data layer がそのフォルダーには見つかりません（docs/requirements-definition.md など）。', 'repo.bad': 'not found: フォルダーが見つかりません。',
    'update.avail': 'データが更新されました。再読み込みします…', 'loading': 'データ層を読み込み中…', 'none': '（なし）',
    'err.nodata': 'このリポジトリには EABK のデータ層が見つかりませんでした。右上のリポジトリ名から別のリポジトリを指定できます。',
    'type.goal': '目的', 'type.req': '機能要求', 'type.nfr': '非機能要求', 'type.ac': '受入基準', 'type.part': '共通部品', 'type.api': 'API', 'type.table': 'テーブル', 'type.entity': 'エンティティ(データ)', 'type.file': 'ソースファイル', 'type.test': 'テストファイル',
    'type.component': 'コンポーネント', 'type.case': '試験ケース', 'type.param': 'パラメータ', 'type.question': '質問', 'type.persona': 'ペルソナ', 'type.external': '外部連携',
    'status.approved': '承認済み', 'status.proposed': 'AI提案', 'status.hold': '保留', 'status.rejected': '却下', 'status.retired': '廃止', 'status.unknown': '不明',
    'impl.done': '実装あり', 'impl.none': '未実装', 'impl.unlisted': 'カタログ外',
    'map.layers': 'レイヤー', 'map.bird': '鳥観図', 'map.zoomsel': '選択に寄る', 'map.tour': 'ツアー', 'map.color.type': '種別色', 'map.color.status': '決定状態', 'map.color.impl': '実装状況',
    'map.hint': 'ドラッグ:移動 / ホイール:ズーム / クリック:選択して関連を強調 / ダブルクリック:全体',
    'map3d.side': '側面', 'map3d.top': '真上', 'map3d.auto': '自動回転', 'map3d.hint': 'ドラッグ:回転 / 右ドラッグ・Shift:平行移動 / ホイール:ズーム / クリック:選択',
    'focus.set': '強調表示', 'focus.count': '{n} 件を強調', 'focus.clear': '解除',
    'dash.title': 'プロダクト・ダッシュボード', 'dash.generated': '読み込み', 'dash.total': '合計', 'dash.reqs': '要求', 'dash.approved': '承認済み', 'dash.impl': '実装登録', 'dash.acs': '受入基準', 'dash.pass': '試験合格', 'dash.openq': '未回答の質問', 'dash.blocked': 'BLOCKED の要求', 'dash.files': 'ファイル', 'dash.comps': 'コンポーネント',
    'dash.status': '決定状態', 'dash.priority': '優先度', 'dash.goals': '目的ごとの実装進捗', 'dash.groups': '境界(要求ファイル)ごとの実装', 'dash.levels': '受入基準の検証レベル', 'dash.cases': 'System Test(台帳)と ID 台帳', 'dash.runs': '実行履歴',
    'dgm.ctx': 'コンテキスト図', 'dgm.goals': '目的ツリー', 'dgm.states': '状態遷移図', 'dgm.entities': 'データ関連図', 'dgm.components': 'コンポーネント図',
    'dgm.ctx.note': 'ペルソナ(4.1)・外部連携(8)・目的(1.2)から作る、システムと外部との境界の図です。クリックで関連を強調します。',
    'dgm.goals.note': '目的(G)に属する要求を 1 つの四角で示す目標分析図です。色は実装登録または決定状態、枠の青緑は非機能要求です。',
    'dgm.states.note': '要求定義書の「状態」の表から作る、エンティティごとの状態遷移図です(二重枠は終端)。',
    'dgm.entities.note': '要求の「対象エンティティ」の同時出現から作るデータの関連図です。線の太さは共有する要求の数、紫の丸は状態数です。',
    'dgm.components.note': 'カタログのファイルパスから作るコンポーネント図です。線は同じ要求を共有していること(共同実装)を示します。',
    'ctx.system': '(対象システム)', 'goals.none': '(目的なし)', 'states.none': '要求定義書に「状態」の表がありません。', 'states.states': '状態', 'states.trans': '遷移', 'states.reqs': '関係する要求:',
    'ent.threshold': '線を出す最小の共有要求数', 'ent.links': '本', 'comp.shared': '件の要求を共有', 'comp.note': '箱:コンポーネント(ファイルの配置先)。内側:モジュールとファイル数。下の小さな枠:そこに置かれた共通部品・API・テーブル。',
    'tbl.sub': 'データ層の全レコードです。行を選ぶと図面で強調され、検索や図の選択はここでも強調されます。', 'tbl.filter': 'この表を絞り込む…', 'tbl.only': '選択に関連する行だけ', 'tbl.all': 'すべて',
    'tab.reqs': '要求', 'tab.acs': '受入基準', 'tab.cases': '試験ケース', 'tab.parts': '共通部品', 'tab.apis': 'API・テーブル', 'tab.files': 'ファイル', 'tab.params': 'パラメータ', 'tab.questions': '質問票', 'tab.terms': '用語', 'tab.personas': 'ペルソナ', 'tab.integrations': '外部連携', 'tab.decisions': '決定記録', 'tab.audits': '監査指摘', 'tab.sources': '出典', 'tab.runs': '実行履歴',
    'col.id': 'ID', 'col.title': '題名', 'col.status': '決定状態', 'col.priority': '優先度', 'col.goal': '目的', 'col.impl': '実装', 'col.acs': '受入基準', 'col.blocked': 'BLOCKED', 'col.group': '境界', 'col.req': '要求', 'col.level': '検証レベル', 'col.text': '内容', 'col.reqs': '要求', 'col.layer': '層', 'col.last_run_at': '最終実行', 'col.lastrun': '最終実行',
    'col.name': '名前', 'col.purpose': '用途', 'col.files': 'ファイル', 'col.kind': '種別', 'col.owner': '正本', 'col.path': 'パス', 'col.comp': 'コンポーネント', 'col.module': 'モジュール', 'col.role': '役割', 'col.value': '値', 'col.unit': '単位', 'col.basis': '根拠', 'col.severity': '重要度', 'col.question': '質問', 'col.state': '状態', 'col.answer': '回答',
    'col.term': '用語', 'col.definition': '定義', 'col.forbidden': '禁止同義語', 'col.work': '業務', 'col.decision': '主要な判断', 'col.data': '使うデータ', 'col.method': '方式', 'col.meaning': '意味', 'col.date': '日付', 'col.target': '対象', 'col.run': 'run', 'col.category': 'カテゴリ', 'col.where': '位置', 'col.summary': '要約', 'col.version': '版', 'col.origin': '出自', 'col.sources': '出典', 'col.assets': '関連する既存資産', 'col.metric': '成功指標', 'col.options': '選択肢', 'col.recommend': '推奨',
    'place.sub': '事業(ビジネス)層の要求が、どのアプリケーションのコンポーネントに、どのデータ・API・部品として置かれているかを、カタログの対応から示します。セルを選ぶと地図で強調されます。',
    'place.tab.biz': 'ビジネス層 × コンポーネント', 'place.tab.data': 'データ × コンポーネント', 'place.tab.items': '共通部品・API・テーブルの置き場', 'place.tests': 'テストの置き場も含める', 'place.rows': '行の単位:', 'place.row.goal': '目的', 'place.row.group': '境界(要求ファイル)', 'place.row.cat': '種別(FR/NFR区分)', 'place.biz': 'ビジネス層',
    'place.pick': 'セルを選ぶと、その要求とファイルの一覧を表示します。', 'place.to2d': '2D 地図で見る', 'place.to3d': '3D 地図で見る', 'place.data.note': 'エンティティ(要求の「対象エンティティ」)を実装する要求が、どのコンポーネントにあるかを示します。', 'place.noapi': 'カタログの「API・イベント」「テーブル」に登録がありません。',
    'src.sub': 'カタログ(機能・共通部品・API・テーブルの表)に書かれたパスだけを使い、ソースコードは読みません。面積は結び付く要求の数です。', 'src.filter': 'パスで絞り込む…', 'src.tests': 'テストを含める', 'src.legend': '青:実装 / 緑:テスト、濃いほど多くの要求に結び付く', 'src.none': 'カタログにファイルの対応がありません。',
    'd.text': '要求本文', 'd.acs': '受入基準', 'd.info': '情報', 'd.impl': '実装ファイル', 'd.tests': 'テスト', 'd.refs': '本文で参照している要求', 'd.src': '定義の位置', 'd.raw': '要求定義書の原文を表示', 'd.open': 'VS Code で開く', 'd.copy': 'IDをコピー', 'd.copied': 'コピーしました',
  },
  en: {
    'nav.dashboard': 'Dashboard', 'nav.map2d': '2D Map', 'nav.map3d': '3D Map', 'nav.diagrams': 'Diagrams', 'nav.placement': 'Placement', 'nav.source': 'Source Map', 'nav.tables': 'Tables',
    'search.ph': 'Search IDs, titles, files, terms…', 'repo.change': 'Switch the target repository', 'repo.prompt': 'Enter the folder path of a repository that uses EABK', 'repo.nodata': 'No EABK data layer (docs/requirements-definition.md etc.) was found in that folder.', 'repo.bad': 'Folder not found.',
    'update.avail': 'Data changed. Reloading…', 'loading': 'Loading the data layer…', 'none': '(none)',
    'err.nodata': 'No EABK data layer was found in this repository. Use the repository button at the top right to pick another one.',
    'type.goal': 'Goal', 'type.req': 'Functional req.', 'type.nfr': 'Non-functional req.', 'type.ac': 'Acceptance criteria', 'type.part': 'Common part', 'type.api': 'API', 'type.table': 'Table', 'type.entity': 'Entity (data)', 'type.file': 'Source file', 'type.test': 'Test file',
    'type.component': 'Component', 'type.case': 'Test case', 'type.param': 'Parameter', 'type.question': 'Question', 'type.persona': 'Persona', 'type.external': 'External system',
    'status.approved': 'Approved', 'status.proposed': 'AI proposed', 'status.hold': 'On hold', 'status.rejected': 'Rejected', 'status.retired': 'Retired', 'status.unknown': 'Unknown',
    'impl.done': 'Implemented', 'impl.none': 'Not implemented', 'impl.unlisted': 'Not in catalog',
    'map.layers': 'Layers', 'map.bird': 'Bird\'s-eye', 'map.zoomsel': 'Zoom to selection', 'map.tour': 'Tour', 'map.color.type': 'By type', 'map.color.status': 'By status', 'map.color.impl': 'By implementation',
    'map.hint': 'Drag: pan / Wheel: zoom / Click: select & highlight relations / Double-click: overview',
    'map3d.side': 'Side', 'map3d.top': 'Top', 'map3d.auto': 'Auto-orbit', 'map3d.hint': 'Drag: orbit / Right-drag or Shift: pan / Wheel: zoom / Click: select',
    'focus.set': 'Highlight', 'focus.count': '{n} highlighted', 'focus.clear': 'Clear',
    'dash.title': 'Product dashboard', 'dash.generated': 'loaded', 'dash.total': 'total', 'dash.reqs': 'Requirements', 'dash.approved': 'Approved', 'dash.impl': 'Implementation registered', 'dash.acs': 'Acceptance criteria', 'dash.pass': 'Tests passing', 'dash.openq': 'Open questions', 'dash.blocked': 'BLOCKED requirements', 'dash.files': 'Files', 'dash.comps': 'components',
    'dash.status': 'Decision status', 'dash.priority': 'Priority', 'dash.goals': 'Implementation per goal', 'dash.groups': 'Implementation per boundary (requirement file)', 'dash.levels': 'Verification level of acceptance criteria', 'dash.cases': 'System Test ledger & ID registry', 'dash.runs': 'Run history',
    'dgm.ctx': 'Context diagram', 'dgm.goals': 'Goal tree', 'dgm.states': 'State diagrams', 'dgm.entities': 'Data relation diagram', 'dgm.components': 'Component diagram',
    'dgm.ctx.note': 'The boundary between the system and the outside, from personas (4.1), integrations (8) and goals (1.2). Click to highlight relations.',
    'dgm.goals.note': 'A goal-analysis diagram: each square is a requirement under a goal (G). Colour shows implementation or decision status; a teal frame marks non-functional requirements.',
    'dgm.states.note': 'State-transition diagrams per entity, from the "states" table of the requirements document (double frame = terminal).',
    'dgm.entities.note': 'Data relations from the co-occurrence of "target entities" in requirements. Line width = shared requirements; purple badge = number of states.',
    'dgm.components.note': 'A component diagram built from the file paths in the catalog. Lines mean two components share requirements (co-implementation).',
    'ctx.system': '(system under description)', 'goals.none': '(no goal)', 'states.none': 'The requirements document has no "states" table.', 'states.states': 'states', 'states.trans': 'transitions', 'states.reqs': 'Related requirements:',
    'ent.threshold': 'Minimum shared requirements per link', 'ent.links': 'links', 'comp.shared': 'shared requirements', 'comp.note': 'Box: component (where files live). Inside: modules with file counts. Small frames: common parts / APIs / tables placed there.',
    'tbl.sub': 'Every record of the data layer. Selecting a row highlights it on the maps; search and diagram selections highlight here too.', 'tbl.filter': 'Filter this table…', 'tbl.only': 'Only rows related to the selection', 'tbl.all': 'all',
    'tab.reqs': 'Requirements', 'tab.acs': 'Acceptance criteria', 'tab.cases': 'Test cases', 'tab.parts': 'Common parts', 'tab.apis': 'APIs & tables', 'tab.files': 'Files', 'tab.params': 'Parameters', 'tab.questions': 'Questions', 'tab.terms': 'Terms', 'tab.personas': 'Personas', 'tab.integrations': 'Integrations', 'tab.decisions': 'Decisions', 'tab.audits': 'Audit findings', 'tab.sources': 'Sources', 'tab.runs': 'Run history',
    'col.id': 'ID', 'col.title': 'Title', 'col.status': 'Status', 'col.priority': 'Priority', 'col.goal': 'Goal', 'col.impl': 'Impl.', 'col.acs': 'AC', 'col.blocked': 'BLOCKED', 'col.group': 'Boundary', 'col.req': 'Requirement', 'col.level': 'Level', 'col.text': 'Text', 'col.reqs': 'Reqs', 'col.layer': 'Layer', 'col.last_run_at': 'Last run', 'col.lastrun': 'Last run',
    'col.name': 'Name', 'col.purpose': 'Purpose', 'col.files': 'Files', 'col.kind': 'Kind', 'col.owner': 'Owner', 'col.path': 'Path', 'col.comp': 'Component', 'col.module': 'Module', 'col.role': 'Role', 'col.value': 'Value', 'col.unit': 'Unit', 'col.basis': 'Basis', 'col.severity': 'Severity', 'col.question': 'Question', 'col.state': 'State', 'col.answer': 'Answer',
    'col.term': 'Term', 'col.definition': 'Definition', 'col.forbidden': 'Forbidden synonyms', 'col.work': 'Work', 'col.decision': 'Key decision', 'col.data': 'Data used', 'col.method': 'Method', 'col.meaning': 'Meaning', 'col.date': 'Date', 'col.target': 'Target', 'col.run': 'run', 'col.category': 'Category', 'col.where': 'Where', 'col.summary': 'Summary', 'col.version': 'Version', 'col.origin': 'Origin', 'col.sources': 'Sources', 'col.assets': 'Existing assets', 'col.metric': 'Success metric', 'col.options': 'Options', 'col.recommend': 'Recommendation',
    'place.sub': 'Shows, from the catalog mapping, in which application components the business-layer requirements, data, APIs and parts are placed. Selecting a cell highlights it on the maps.',
    'place.tab.biz': 'Business layer × components', 'place.tab.data': 'Data × components', 'place.tab.items': 'Where parts, APIs and tables live', 'place.tests': 'Include test locations', 'place.rows': 'Rows by:', 'place.row.goal': 'Goal', 'place.row.group': 'Boundary (requirement file)', 'place.row.cat': 'Kind (FR / NFR category)', 'place.biz': 'Business layer',
    'place.pick': 'Select a cell to list its requirements and files.', 'place.to2d': 'Show on 2D map', 'place.to3d': 'Show on 3D map', 'place.data.note': 'Shows in which components the requirements that handle each entity ("target entity") are implemented.', 'place.noapi': 'No entries in the catalog "API / events" or "tables".',
    'src.sub': 'Uses only the paths written in the catalog (features, common parts, APIs, tables); source code is never read. Area = number of linked requirements.', 'src.filter': 'Filter by path…', 'src.tests': 'Include tests', 'src.legend': 'Blue: implementation / Green: tests; darker = more requirements', 'src.none': 'The catalog has no file mapping.',
    'd.text': 'Requirement text', 'd.acs': 'Acceptance criteria', 'd.info': 'Info', 'd.impl': 'Implementation files', 'd.tests': 'Tests', 'd.refs': 'Referenced in the text', 'd.src': 'Defined at', 'd.raw': 'Show original markdown', 'd.open': 'Open in VS Code', 'd.copy': 'Copy ID', 'd.copied': 'Copied',
  },
};

export const lang = () => current;
export function t(key, vars) {
  let s = D[current][key] ?? D.en[key] ?? key.split('.').pop();
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}
export function onLang(fn) { listeners.add(fn); return () => listeners.delete(fn); }
export function setLang(l) {
  current = l; localStorage.setItem(STORE_KEY, l);
  document.documentElement.lang = l;
  applyI18n(document);
  for (const fn of [...listeners]) { try { fn(l); } catch (e) { console.error(e); } }
}
export function applyI18n(root) {
  root.querySelectorAll('[data-i18n-ph]').forEach((e) => (e.placeholder = t(e.dataset.i18nPh)));
  root.querySelectorAll('[data-i18n-title]').forEach((e) => (e.title = t(e.dataset.i18nTitle)));
  root.querySelectorAll('[data-i18n]').forEach((e) => (e.textContent = t(e.dataset.i18n)));
}
document.documentElement.lang = current;
