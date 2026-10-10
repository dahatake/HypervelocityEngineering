# EABK Studio

EABK のデータ層（要求定義書・カタログ・System Test の台帳・ID 台帳・実行履歴）を、Product Manager・Architect・Software Engineer の視点で見て回る、ローカル専用の Web アプリです。
EABK を使っている**どのリポジトリでも**動きます（このリポジトリに依存しません）。UI は日本語・英語を右上の `JA | EN` で切り替えます。

*A local-only web app that lets a product manager explore the EABK data layer (requirements, catalog, system-test ledger, ID registry, run history) of **any** repository that uses EABK. The UI switches between Japanese and English with the `JA | EN` button.*

> 初めての方は、役割に合うガイドから読んでください: [Product Manager](users-guide/05-product-manager.md)・[Architect](users-guide/06-architect.md)・[Software Engineer](users-guide/07-software-engineer.md)（索引は [users-guide/README.md](users-guide/README.md)）。各画面が読むデータの一覧は [08-data-reference.md](users-guide/08-data-reference.md) です。`tools/install.py` で他のリポジトリへ入れると、これらのガイドも一緒に入ります。

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
| `--role pm\|architect\|swe` | 最初に開く画面（pm = ダッシュボード、architect = 2D マップ、swe = 表）。画面右上のロールのボタンと同じ |
| `--check` | 管理データのファイルの有無と、解析できた件数・警告を表示して終了（データ層があれば 0、なければ 1）。サーバーは起動しません |

データ層がないフォルダーを `--repo` に指定すると、起動せずに案内を出して終了コード 1 で終わります。

画面右上のリポジトリ名を押すと、起動したまま別のリポジトリへ切り替えられます。データ層のファイルを更新すると、数秒以内に自動で読み直します。
ファイルの場所は、対象リポジトリの `scripts/ebak.config.json`（なければ `scripts/hve.config.json`）の `management_files` に従います。

## 画面 / Views

| 画面 | 内容 |
|---|---|
| ダッシュボード | 要求数・承認率・実装登録率・試験合格率・未回答の質問・BLOCKED、目的ごとの進捗、境界ごとの実装。グラフをクリックすると、該当する要求を地図で強調します |
| 2D マップ | 目的 → 要求 → データ・共通部品・API・テーブル → ソースファイル → 試験ケース。鳥観図からズームで詳細へ。ツアー、ミニマップ、色の切替（種別・決定状態・実装状況） |
| 3D マップ | 同じ関係を層にした立体図。ドラッグで回転、ホイールでズーム。選択するとカメラが寄り、関係が光って流れます。ツアー、側面・真上、自動回転 |
| 図式 | コンテキスト図、目的ツリー、状態遷移図、データ関連図、コンポーネント図 |
| 配置 | ビジネス層（目的・境界・種別）× コンポーネント、データ（エンティティ）× コンポーネント、共通部品・API・テーブルの置き場 |
| ソース対応 | カタログに書かれたパスのツリーマップ。ファイルを選ぶと結び付く要求・部品・テスト |
| 表 | 全レコード（要求・受入基準・試験ケース・共通部品・API・テーブル・ファイル・PARAM・質問票・用語・ペルソナ・外部連携・決定記録・監査指摘・出典・実行履歴）。並べ替え・絞り込み・CSV |
| 配置（実行環境） | `#/placement?kind=runtime`。Studio が読むファイル・書く先・外部送信の位置づけ |
| 構造・一貫性 | `#/structure`（7 つのデータ層の現状と理想の差）、`#/consistency`（要求 → AC → 試験 → カタログ → 実装ファイルの欠け）。URL で開く |
| 整合性保守 | 要求正本と違うカタログの題名・決定状態を、プレビュー後に更新（下記） |

- **検索**: `/` または `Ctrl+K`。結果を選ぶ（Enter）と、開いている図面で関連が強調されます。`Shift+Enter` は結果すべてを強調します。
- **関連の強調**: 図の点にポイントすると直接の関連、クリックすると 2 段先までの関連が強調され、右に詳細が出ます。`Esc` で解除します。
- **リンク**: `http://127.0.0.1:8765/#/map2d?q=<要求ID>`、`#/tables?tab=cases`、`#/diagrams?kind=states`、`#/placement?kind=runtime` のように画面と検索・タブ・種類を URL で指定できます。`?select=<ID>` は撮影用の表示（メニューを隠す）になります。

## 何を読むか / What is read

| 読むもの | 使い道 |
|---|---|
| `docs/requirements-definition.md`（と `docs/requirements/*.md`） | 目的・要求・受入基準・PARAM・用語・状態・ペルソナ・外部連携・質問票・決定記録・監査指摘・出典 |
| `docs/catalog.md` | 機能・共通部品・API・テーブルと、実装ファイル・テストのパス（ソースへの対応はこれだけから作ります） |
| `tests/system/ledger.json` | System Test のケースと結果 |
| `docs/id-registry.md`, `docs/run-history.md` | ID 台帳の集計、実行履歴 |

ソースコードは**開きません**。カタログに書かれたパスの名前だけを使います。どの画面がどのファイルのどの節・列を読み、どう計算するかは [08-data-reference.md](users-guide/08-data-reference.md) にあります。サーバーは `127.0.0.1` だけで待ち受け、通常の閲覧・検索・CSV出力・リポジトリ切替では書き込みません。

例外は「整合性保守」画面で利用者が差分をプレビューし、`確認して実行` を押した場合だけです。この操作は `docs/catalog.md` の選択した要求行について、`題名` と `決定状態` の2列だけを要求正本へ合わせます。プレビュー後の競合、対象外ファイルへの影響、書込み失敗、`python scripts/verify.py --docs-only` の失敗を検出すると、変更をバイト単位で復元して明示的にエラーを表示します。

## 保守 / Maintenance

- テスト: `python -m pytest EABK-Studio/tests -q`
- 整合性保守: `整合性保守 / Maintenance` → 対象要求 → プレビュー → `確認して実行`
- 構成: `studio.py`（サーバー）、`eabk_model.py`（データ層の読み取りとグラフ化）、`web/`（画面。ビルド不要の ES モジュール。`web/vendor/three.module.min.js` は three.js・MIT）
- 画面の文言は `web/js/i18n.js` の `ja` / `en` に追加します。
