# EABK Studio

EABK のデータ層（要求定義書・カタログ・System Test の台帳・ID 台帳・実行履歴）を、Product Manager・Architect・Software Engineer の視点で見て回る、ローカル専用の Web アプリです。
EABK を使っている**どのリポジトリでも**動きます（このリポジトリに依存しません）。UI は日本語・英語を右上の `JA | EN` で切り替えます。

*A local-only web app that lets a product manager explore the EABK data layer (requirements, catalog, system-test ledger, ID registry, run history) of **any** repository that uses EABK. The UI switches between Japanese and English with the `JA | EN` button.*

> 初めての方は、役割に合うガイドから読んでください: [Product Manager](../users-guide/studio/05-product-manager.md)・[Architect](../users-guide/studio/06-architect.md)・[Software Engineer](../users-guide/studio/07-software-engineer.md)（索引は [users-guide/studio/README.md](../users-guide/studio/README.md)）。各画面が読むデータの一覧は [08-data-reference.md](../users-guide/studio/08-data-reference.md) です。`tools/install.py` で他のリポジトリへ入れると、これらのガイドも一緒に入ります。

## 起動 / Start

Python 3.9 以上だけで動きます（追加のインストールなし。3D 用の three.js は `web/vendor/` に同梱）。

```powershell
python EABK-Studio/studio.py --repo C:\path\to\your-repo      # ブラウザーが開きます
python EABK-Studio/studio.py --role architect                  # 役割に合う画面から始める
python EABK-Studio/studio.py --check                           # データ層が読めるかだけを確認（起動しない）
.\EABK-Studio\start.ps1 C:\path\to\your-repo -Role pm          # 同じ（Windows）。-Check / -NoOpen も可
./EABK-Studio/start.sh /path/to/your-repo 8765 --role swe      # 同じ（macOS / Linux）。第 3 引数以降は studio.py にそのまま渡す
```

| オプション | 意味 |
|---|---|
| `--repo PATH` | 対象リポジトリ（省略時は現在のフォルダー。親フォルダーへさかのぼって `docs/requirements-definition.md` か `docs/catalog.md` を探します） |
| `--port N` | 待ち受けポート（既定 8765。使用中なら次の番号） |
| `--no-open` | ブラウザーを自動で開かない |
| `--role pm\|architect\|swe` | 最初に開く画面（pm = ダッシュボード、architect = マップ（2D）、swe = 表）。画面右上のロールのボタンと同じ |
| `--check` | 管理データのファイルの有無と、解析できた件数・警告を表示して終了（データ層があれば 0、なければ 1）。サーバーは起動しません |

データ層がないフォルダーを `--repo` に指定すると、起動せずに案内を出して終了コード 1 で終わります。

画面右上のリポジトリ名を押すと、起動したまま別のリポジトリへ切り替えられます。データ層のファイルを更新すると、数秒以内に自動で読み直します。
ファイルの場所は、対象リポジトリの `scripts/ebak.config.json`（なければ `scripts/hve.config.json`）の `management_files` に従います。

## 画面 / Views

画面上部のナビゲーションは、「何のデータを閲覧できるか」の軸で 9 項目に整理しています。各項目の 1 行説明は、項目にポイントしたときのツールチップと、各画面の冒頭に同じ文で出ます（JA / EN）。分類の軸は、状況の集計（①②）、関係と構造（③④）、データと外部との接点（⑤⑥）、実装との対応（⑦）、元の行（⑧）、保守操作（⑨）です。

| 項目 | 閲覧できるデータ |
|---|---|
| ① ダッシュボード | 目的ごとの進捗・指標・履歴・未解決の件数の集計。要求数・承認率・実装登録率・試験合格率・未回答の質問・BLOCKED、境界ごとの実装。グラフをクリックすると、該当する要求をマップで強調します |
| ② 実装状態 | 承認済みの要求ごとの未着手・実装登録済み・試験 pass 済み（目的別・優先度別・かんばん・一覧表） |
| ③ マップ | 目的 → 要求 → データ・共通部品・API・テーブル → ソースファイル → 試験ケースのつながりをたどる関係のグラフ。**2D / 3D を切替アイコンで選べます**（2D: 鳥観図からズーム、ツアー、ミニマップ、色の切替。3D: 層にした立体図、ドラッグで回転、ホイールでズーム、ツアー、自動回転）。旧「2D マップ」「3D マップ」で、`#/map2d`・`#/map3d` は別名として残ります |
| ④ 図式 | コンテキスト図・目的ツリー・状態遷移図・データ関連図・コンポーネント図・実装配置図（層 × コンポーネント、データ × コンポーネント、置き場、実行環境の見方を含む）。**どの図も 2D / 3D を切替アイコンで選べます**（`#/diagrams?kind=<ctx\|goals\|states\|entities\|components\|layers>&dim=<2d\|3d>`）。旧「配置」の `#/placement` は別名として残り、実装配置図へ移動します |
| ⑤ エンティティ | `#/entities`。行をエンティティ、列を要求と利用シナリオにした対応表（作成・参照・更新・削除を記号と語で表示。絞り込み・並べ替え・CSV・テキスト表示）。見出しを選ぶと `#/entities?entity=<名前>` の詳細（説明・状態と遷移の条件・使う要求・利用シナリオ・管理テーブル・使うコンポーネント／API／共通部品・出典の位置）。エンティティが 0 件のリポジトリでは「エンティティなし」と案内します。導出は `scripts/entities.py` を再利用します。下部の「関係と列（意味的ズーム）」とマップ（関係か列があるとき最初に表示）で、倍率に応じてクラスター → エンティティと関係線 → 列の一覧（型・キー・参照先）に切り替わります（`semzoom.js`・`sz2d.js`・`sz3d.js`。可視範囲だけを描画。`window.eabkView.setScale / getState` を公開） |
| ⑥ 外部連携 | 外部のアプリ・データとの連携（連携先・方向・方式・データ分類）の一覧と詳細。一覧と詳細の表示は FR-1042 で実装します（現在は項目の居場所と案内だけです） |
| ⑦ ソース対応 | カタログに書かれたパスのツリーマップ。ファイルを選ぶと結び付く要求・部品・テスト |
| ⑧ 表 | 全レコード（要求・受入基準・試験ケース・共通部品・API・テーブル・ファイル・PARAM・質問票・用語・ペルソナ・外部連携・決定記録・監査指摘・出典・実行履歴）の元の行。並べ替え・絞り込み・CSV |
| ⑨ 整合性保守 | 要求正本と違うカタログの題名・決定状態を、プレビュー後に更新（下記）。書込みはここだけ |

`#/structure`（7 つのデータ層の現状と理想の差）と `#/consistency`（要求 → AC → 試験 → カタログ → 実装ファイルの欠け）は、URL で開く ⑨ の補助画面です。

### 管理データの種別と主な閲覧場所

「主な閲覧場所」は、その種別の意味づけ・関係・詳細を見る項目で、各種別についてちょうど 1 項目です。⑧ 表は、全種別を生データの行で横断して閲覧・並べ替え・CSV 出力できる副次の閲覧場所で、主な閲覧場所には数えません。ほかの項目には、主な閲覧場所へのリンクとして現れます。

| 種別 | 主な閲覧場所 | 副次 |
|---|---|---|
| 目的 | ダッシュボード | 表 |
| 要求 | 実装状態 | 表 |
| 受入基準 | 実装状態 | 表 |
| 試験ケース | 実装状態 | 表 |
| 共通部品 | 図式（コンポーネント図） | 表 |
| API | 図式（実装配置図） | 表 |
| テーブル | 図式（データ関連図） | 表 |
| ファイル | ソース対応 | 表 |
| PARAM | マップ | 表 |
| 質問 | ダッシュボード | 表 |
| 用語 | エンティティ | 表 |
| ペルソナ | 図式（コンテキスト図） | 表 |
| エンティティ | エンティティ | 表 |
| 外部連携 | 外部連携 | 表 |
| 決定記録 | ダッシュボード | 表 |
| 監査指摘 | ダッシュボード | 表 |
| 出典 | マップ | 表 |
| 実行履歴 | ダッシュボード | 表 |

### 2D / 3D の切替

マップと図式の各表示には、切替アイコン（アニメ調の顔つきの「平面」と「立体」の図柄と、「2D」「3D」の語）があります。既定は 2D で、選んだ次元は画面を開いている間だけ保たれます。切替では、選択中の対象・絞り込み・図式の種類・検索の文字が保たれます。キーボード（Tab → Enter）と、検索欄の `> 2D` のコマンドからも切り替えられます。動きの軽減（OS の設定）では、アイコンの動きが止まります。3D を描画できない環境では 2D を表示し、理由と同じ内容の表を示します。アイコンは画面に内蔵した図で、外部から取得しません。

- **検索**: `/` または `Ctrl+K`。結果を選ぶ（Enter）と、開いている図面で関連が強調されます。`Shift+Enter` は結果すべてを強調します。`>` に続けて項目名を入れると、その項目へ移動するコマンドになります。
- **関連の強調**: 図の点にポイントすると直接の関連、クリックすると 2 段先までの関連が強調され、右に詳細が出ます。`Esc` で解除します。
- **リンク**: `http://127.0.0.1:8765/#/map2d?q=<要求ID>`、`#/tables?tab=cases`、`#/diagrams?kind=states&dim=3d`、`#/diagrams?kind=layers&view=runtime` のように画面と検索・タブ・種類・次元を URL で指定できます。旧 URL（`#/map2d`・`#/map3d`・`#/placement?kind=runtime`）も使えます。`?select=<ID>` は撮影用の表示（メニューを隠す）になります。

## 何を読むか / What is read

| 読むもの | 使い道 |
|---|---|
| `docs/requirements-definition.md`（と `docs/requirements/*.md`） | 目的・要求・受入基準・PARAM・用語・状態・ペルソナ・外部連携・質問票・決定記録・監査指摘・出典 |
| `docs/catalog.md` | 機能・共通部品・API・テーブルと、実装ファイル・テストのパス（ソースへの対応はこれだけから作ります） |
| `tests/system/ledger.json` | System Test のケースと結果 |
| `docs/id-registry.md`, `docs/run-history.md` | ID 台帳の集計、実行履歴 |

ソースコードは**開きません**。カタログに書かれたパスの名前だけを使います。どの画面がどのファイルのどの節・列を読み、どう計算するかは [08-data-reference.md](../users-guide/studio/08-data-reference.md) にあります。サーバーは `127.0.0.1` だけで待ち受け、通常の閲覧・検索・CSV出力・リポジトリ切替では書き込みません。

例外は「整合性保守」画面で利用者が差分をプレビューし、`確認して実行` を押した場合だけです。この操作は `docs/catalog.md` の選択した要求行について、`題名` と `決定状態` の2列だけを要求正本へ合わせます。プレビュー後の競合、対象外ファイルへの影響、書込み失敗、`python scripts/verify.py --docs-only` の失敗を検出すると、変更をバイト単位で復元して明示的にエラーを表示します。

## 保守 / Maintenance

- テスト: `python -m pytest EABK-Studio/tests -q`
- 整合性保守: `整合性保守 / Maintenance` → 対象要求 → プレビュー → `確認して実行`
- 構成: `studio.py`（サーバー）、`eabk_model.py`（データ層の読み取りとグラフ化）、`web/`（画面。ビルド不要の ES モジュール。`web/vendor/three.module.min.js` は three.js・MIT）
- 画面の文言は `web/js/i18n.js` の `ja` / `en` に追加します。
