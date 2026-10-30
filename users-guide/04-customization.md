**日本語** | [English](04-customization.en.md)

# 4. 設定とカスタマイズ

設定は `scripts/ebak.config.json` に集約しています。インストール・更新時には、利用者が設定した値は保持され、新しいキーだけが追加されます。

## 4.1 ビルド・静的解析・テストのコマンド（`verify.commands`）

`scripts/verify.py` は、管理データの検査（CHK-01〜27）の後に、ここに登録したコマンドを順に実行します。1 つでも失敗すると exit 1 になります。

```json
"verify": {
  "timeout_sec": 1800,
  "commands": [
    { "name": "install", "run": "npm ci" },
    { "name": "lint", "run": "npm run lint" },
    { "name": "build", "run": "npm run build" },
    { "name": "unit", "run": "npm test -- --run" },
    { "name": "e2e-smoke", "run": "npx playwright test --grep @canary", "slow": true, "timeout_sec": 900 }
  ]
}
```

| キー | 意味 |
|---|---|
| `name` | 表示名。ログのファイル名にも使います |
| `run` | リポジトリのルートで実行するシェルコマンド |
| `slow` | `true` にすると、作業役のゲート（`verify.py --quick`）ではスキップし、統合時と最終工程でだけ実行します |
| `timeout_sec` | このコマンドのタイムアウト（既定は `verify.timeout_sec`） |
| `cache_files` | 例: `["package.json", "package-lock.json"]`。これらが前回の成功時から変わっていなければ、このコマンドをスキップします（`npm ci` などの依存の導入向け。`--no-cache` で無効）。build と分けて登録します |

`verify.retry_on`（正規表現）に一致する環境起因の失敗（既定は vitest の `Timeout calling` や `ECONNRESET` など）は、1 回だけ自動で再実行します。無効にするには `verify.retry_flaky: false` にします。

`"commands": ["python -m pytest -q"]` のように文字列だけを書くこともできます。その場合、`name` はコマンドの先頭の語（例: `python`）になります。`run` のない要素や、文字列でもオブジェクトでもない要素は、`FAIL config` として verify を失敗させます。

技術スタック別の例:

| スタック | 例 |
|---|---|
| .NET | `dotnet build --nologo`、`dotnet test --nologo` |
| Python | `python -m ruff check .`、`python -m pytest -q` |
| Java (Gradle) | `./gradlew build` |
| Go | `go vet ./...`、`go test ./...` |

ログの全文は `/work/runs/<run-id>/logs/`（run がないときは `/work/logs/`）に保存され、コンソールには失敗の要約だけが出力されます。

## 4.2 モデルの選択

EABK はモデルを指定しません。conductor も作業役も、	ask の `model` 引数を付けずに呼び、選択は Copilot（Copilot Fusion など）に任せます。実際に使ったモデルは `work/runs/<run-id>/models.jsonl` に記録され、`kpi.py run` の「実際に使ったモデル」に出ます。特定のモデルに固定したいときは、各 `.github/agents/*.agent.md` の frontmatter に `model:` を書きます。

**項目の粒度**: `queue add` は、1 項目の AC が 12 個を超えると拒否します（`--allow-large` で例外）。実測では、作業時間が 200 分を超えた項目に手戻りが集中しました。

## 4.3 ゲートの調整（`gates`）

```json
"gates": {
  "enabled": true,
  "subagent_verify": {
    "implementer": ["--quick"],
    "test-designer": ["--docs-only"],
    "rd-author": ["--docs-only"]
  },
  "subagent_verify_max_blocks": 3,
  "agent_stop_max_blocks": 40,
  "enforce_conductor_edit_scope": true
}
```

| キー | 意味 |
|---|---|
| `enabled` | `false` にすると hook のゲートをすべて無効にします（verify の検査は残ります）。原因の切り分けのときだけ使います |
| `subagent_verify` | 作業役の終了前に実行する verify の引数（G-4）。ここにない作業役は検査しません |
| `subagent_verify_max_blocks` | 同じ作業役を差し戻す回数の上限。超えると結果に `GATE G-4` を付けて返し、conductor はその結果を統合しません |
| `agent_stop_max_blocks` | 完了条件を満たしていない conductor の終了を差し戻す回数の上限 |
| `enforce_conductor_edit_scope` | conductor が `work/` と `docs/run-history.md` 以外を編集するのを拒否します。harness で subagent の検出が動かない場合（[07-troubleshooting.md](07-troubleshooting.md)）だけ `false` にします |
| `allow_hook_edit` | 既定 `false`。run 中に作業役が `scripts/hooks/`・`.github/hooks/`（ゲート自身）を編集するのを拒否します（G-5）。hooks を保守するリポジトリーだけ `true` にします。ほかのゲートは変わりません |
| `deploy_patterns` | デプロイとみなすコマンドの正規表現。指定すると既定値（`scripts/ebaklib.py` の `DEFAULT_CONFIG`）を**置き換える**ので、既定値をコピーしてから追加します |
| `external_write_verbs` | MCP Server・plugin・拡張機能のツールのうち、名前にこの動詞（`create`・`update`・`delete`・`send`・`do_action` など）を含むものを「外部のシステムの変更」とみなします（G-5。[4.4](#44-mcp-serverplugin拡張機能を使う)）。指定すると既定値を**置き換えます** |
| `external_deploy_verbs` | 同じく、名前にこの動詞（`deploy`・`provision`・`publish`・`release`）を含むものを「デプロイ・公開」とみなし、`deploy` の値で判定します |
| `external_tool_allow` | 外部のシステムの変更とみなさないツール名の正規表現（例: `"^mcp_myindex_update_index$"`）。名前に動詞を含むが、ローカルにしか作用しないツールを許可するときに使います |

## 4.3b 時間・依存の共有・クレジットの設定（`limits` / `worktree_share` / `credits`）

```json
"limits": { "max_hours_default": 2.5, "max_hours_cap": 3, "reserve_minutes": 30 },
"worktree_share": { "enabled": true, "dirs": ["node_modules"] },
"credits": { "default_multiplier": 1, "model_multipliers": { "claude-sonnet-5.5": 1, "gpt-6.1-sol": 3 } }
```

| キー | 意味 |
|---|---|
| `limits.max_hours_default` | run_options に `max_hours` がないときの時間（時間単位） |
| `limits.max_hours_cap` | `max_hours` の上限。これを超える指定は切り詰めます。夜間に長く回すときは、この値（と run_options の `max_hours`）を引き上げます（例: `8`）。既定は 3 時間 |
| `limits.reserve_minutes` | 工程 6（最終）のために残す時間。残りがこれを切る（または 85% を超える）と、新しい項目を始めません |
| `worktree_share.enabled` / `dirs` | 作業用 worktree の依存ディレクトリ（`node_modules` など）を、導入済みの主の作業ツリーの実体へのリンク（Windows は junction）にして、worktree ごとの `npm ci` をなくします。`package.json` と `package-lock.json` が共有元と同じときだけ共有します。共有元がなければ、`integrate.py prepare` が `NOTE:` を出すので、主の作業ツリーで 1 回だけ導入してください。`false` で無効にできます |
| `credits.model_multipliers` | `run-state.py finish` が `--credits` なしのとき、作業役（task）の呼び出しをモデルの倍率で数えた「推定」を run-history の AI クレジット欄に記録します。進行役自身の呼び出しは含みません。作業役ごとの所要時間は `work/runs/<run-id>/subagents.jsonl` に記録されます |

hook は、読み取り専用・記録だけのツール（`view`・`grep`・`sql`・`report_intent` など）を、設定やリポジトリを読まずに即座に許可します。

## 4.4 MCP Server・plugin・拡張機能を使う

利用者が GitHub Copilot に設定した MCP Server・plugin・拡張機能のツールと skill は、追加の設定なしで、conductor とすべての作業役が使えます。例は Work IQ（社内のメール・会議・チャット・ドキュメント）、Microsoft Learn、Azure MCP Server、Copilot Studio・Microsoft 365 Agents Toolkit の plugin です。

- **仕組み**: `.github/agents/*.agent.md` の frontmatter に `tools:` を書いていません。Copilot CLI と GitHub では、`tools` を省略すると、構成済みの MCP Server を含むすべてのツールが有効になります。VS Code では、ツールピッカーで有効にしているツールが使われます。`tools:` を書くと、列挙していないツール（MCP Server のツールを含む）は使えなくなります。役割ごとに制限したい場合は、組み込みのツールに加えて `<サーバー名>/*` の形で必要な MCP Server を列挙します。
- **設定する場所**: MCP Server と plugin は、利用者ごと（VS Code のユーザー設定・`~/.copilot/` の設定・`copilot plugin install`・GitHub Copilot app の **カスタマイズ** → **MCP** / **プラグイン**）か、リポジトリ（`.vscode/mcp.json`、GitHub のリポジトリ設定）に登録します。GitHub Copilot app は Copilot CLI 用の設定（`~/.copilot/`）とリポジトリの設定を自動で使います。認証情報が必要なものは、リポジトリに秘密値を置かず、各利用者のサインインや環境変数で渡します。toolkit は MCP Server の設定を配布しません。
- **使い方**: 依頼に「Work IQ で関連する会議とメールを調べる」のようにツールを書く必要はありません。skill（requirement-definition・implement-fr）が、社内の情報・公式ドキュメント・対象の技術の MCP Server と skill を、使えるときに使うよう指示しています。社内の情報から得た事実は、出典台帳（SRC-ID）に出典付きで記録されます。そのため、同じツールを持たない後続の人やエージェントも、要求定義書だけで同じ情報をたどれます。
- **ツールがない環境**: 特定のツールがある前提にはしていません。使えない場合は、通常の検索と `<references>` の資料で進め、「社内情報未確認」などと記録します。
- **外部のシステムの変更**: 参照（検索・取得・質問）はいつでも行えます。メール送信、チケットの作成、クラウドのリソースや Copilot Studio のエージェントの作成・更新・削除のような外部への変更は、run 中は run_options の `external_write: する` のときだけ行えます。デプロイ・公開は `deploy: する` のときだけです。どちらも hook が強制します（G-5）。rd-auditor と reviewer は、run_options に関係なく参照だけです。GitHub Copilot app の組み込みツールのうち、アプリの中だけに作用する `rename_session`・`send_session_message` は外部の変更とみなしません。セッションのブランチ名を変える `rename_branch` は、統合ブランチが変わってしまうため run 中だけ拒否します。
- **ツール数の上限**: VS Code では、1 回のリクエストで有効にできるツールは 128 個までです。MCP Server を多く登録して上限を超える場合は、ツールピッカーで使わないサーバーを無効にします。

## 4.5 そのほかの設定

| キー | 既定値 | 意味 |
|---|---|---|
| `management_files` | `docs/requirements-definition.md` など | 管理データのパス。既存のディレクトリ構成に合わせて変更できます |
| `enterprise_data_catalog` | なし（未設定） | 任意。企業データカタログの参照元。`{"source": "<ファイルのパスまたは http(s) の URL>", "name_column": "<名前の列・項目（省略可）>", "format": "auto|csv|json|markdown|html（省略可）"}`。`scripts/entities.py check` / `todo` が読み取りだけで照合します。URL に認証情報を埋め込めません（その場合は「照合不能」）。取得の待ち時間は PARAM-016、揺れ候補の類似度は PARAM-015 です |
| `base_branch` | `main` | マージ先のブランチ。差分の検査（CHK-12/13）と、push の拒否（G-5）に使います |
| `work.retention_days` | 14 | `/work/runs/` の保持日数 |
| `checks.ambiguous_words` | 適切、迅速、直感的 など | 曖昧な語のリスト（CHK-13） |
| `checks.id_scan_exclude` | `docs/**`、`EABK-Studio/**` など | コードから要求 ID を検索するときに除外するパス（CHK-17/19） |
| `checks.test_path_pattern` | tests/、*.test.* など | テストコードとみなすパス（CHK-09） |

## 4.6 画面の見た目（デザインシステム）

要求定義書は「何を満たすか」だけを書き、配色・装飾・UI ライブラリは指定しません。見た目は implementer が、skill `implement-fr` の「画面の見た目（UI デザインの基盤）」に従って決めます。

- **既定**: 対象プラットフォームの最新の公式デザインシステムと公式のコンポーネントを使います。Web は Microsoft Fluent 2（Fluent UI）、Windows は WinUI 3、Apple のプラットフォームは Human Interface Guidelines と SwiftUI の標準コンポーネント、Android は Material 3 です。リポジトリに既存のデザインシステムがあれば、それを優先します。
- **一貫性**: 最初に画面を作る項目で、テーマ（ライト・ダーク・ハイコントラスト）、デザイントークン、アプリの外枠を「デザイン基盤」としてカタログの共通部品に載せます。conductor はほかの画面の項目をこの項目のあとに並べ、reviewer は画面の差分を規則と照合します。
- **指定したい場合**: 依頼に「デザインシステムは Fluent 2 を使う」「社内のブランドガイド（添付）に従う」のように書くか、`<references>` に指針を渡します。rd-author が既定制約として要求定義書に記録し、implementer はそれを最優先にします。
- **既存のアプリの見た目を直したい場合**: 「既存の画面をデザイン基盤に移行する」と依頼します。手順書だけを更新しても、既に作られた画面は変わりません。

## 4.7 エージェントと手順書を変更する

- 役割ごとの振る舞いは `.github/agents/*.agent.md`、詳しい手順は `.github/skills/*/SKILL.md` に定義しています。直接編集してかまいません。
- インストールスクリプトを再実行しても、ローカルで変更したファイルは上書きされません（`KEEP-LOCAL`）。toolkit の新しいバージョンを取り込みたい場合は、`--dry-run` で確認してから、差分を手でマージするか、`--force`（バックアップを残します）を使います。
- skills の本文は、元になった 3 つの Prompt（RequirementDefinition作成・RD-FR_Prompt・SystemTest-Increment-Run）の全文です。先頭の「読み替え表」が、元の Prompt と無人実行との差分を吸収しています。元の Prompt を改訂した場合は、本文を差し替え、読み替え表はそのまま残します。

## 4.8 CI

`.github/workflows/ebak-verify.yml` は、pull request と main への push をトリガーに `scripts/verify.sh --show-warnings` を実行します。アプリのビルドに必要なツールチェーン（`actions/setup-node` など）は、verify の前にステップとして追加します。CodeQL や依存関係のスキャンを加える場合も、このワークフローに追記します。

### データ層ワークフロー（ebak-data-layer）

`.github/workflows/ebak-data-layer.yml`（ebak-data-layer）は、プルリクエスト、main への push、手動実行（workflow_dispatch）、週 1 回の定期実行（schedule）で `python scripts/verify.py --docs-only` を実行し、データ層を検査します。

- 不合格のとき、共通の入口 `python scripts/rdfix.py --full --apply` で自動修復して再検査します（インストーラ・手動実行と同じ入口。独自の書き換え手順は持ちません。終了コード 0/1/2 は [05](05-scripts-reference.md)）。インストーラは既定で導入後に同じ入口を 1 回呼び、`--no-repair` で検査と計画だけ（書き込まない）、`--skip-verify` で検査も修復もしません。自動修復で要求定義書は変更しない設計です（`docs/requirements-definition.md` は修復後に元へ戻します）。合格した場合だけ修復を commit します。同一リポジトリのプルリクエストでは当該 PR のブランチへ、main への push と定期実行では修復用ブランチ `eabk/data-layer-fix` へ push して PR を作成します（既にあれば追加しません）。
- 修復後も直らないときは、ラベル `eabk-data-layer` つきで、失敗の要約と実行へのリンクを含む Issue を作成します。同じ内容の未解決 Issue があれば、コメントを追加します。
- 権限は contents・pull-requests・issues の write だけです。fork からのプルリクエストでは検査だけを行い、書き込みはしません。bot の修復 commit では再修復しません。
- 無効化するには、このファイルを削除するか、GitHub の Actions 画面でこのワークフローを Disable します。インストール時に入れたくない場合は `--no-ci` を指定します。

## 4.9 計算資源とクラウド

**並列度は CPU とメモリに合わせます。**
- `parallel_workers: auto`（既定）は、2 コアと 6 GB につき implementer を 1 体、最大 8 体にします。`run-state.py start` が解決した数を `meta.json` に残します。
- 各 worker には CPU スレッドを「コア数 × 1.5 ÷ worker 数」で渡します（`HVE_CPUS`。20 コア・8 体なら 4）。同時に、主なテストランナーの設定の環境変数も渡します（`VITEST_MAX_WORKERS`・`VITEST_MAX_THREADS`・`VITEST_MAX_FORKS`・`PYTEST_XDIST_AUTO_NUM_WORKERS`・`CARGO_BUILD_JOBS`・`GOMAXPROCS`・`CMAKE_BUILD_PARALLEL_LEVEL`・`MAKEFLAGS`）。利用者が設定済みの値は上書きしません。
- 実測（プロジェクトの vitest を 20 コアで 8 並列）: 全コアを使わせると 361 秒で、テストの timeout が 1 件出ました。2 スレッドずつに絞ると 404 秒（遅い）、4 スレッドずつだと 371 秒で timeout なしでした。そのため、少し多めの配分にしています。前回の run の `Timeout calling "onTaskUpdate"` は、並列度 5 の worker にブラウザーなどの負荷が重なった状況で、unit のログの約 10% に出ました。Playwright など環境変数を読まないツールは、設定ファイルで `workers: Number(process.env.HVE_CPUS) || undefined` のように読みます。

**検査を同時に動かします。**
- `verify.commands` で、連続する工程に `"parallel": true` を付けると同時に実行します（例: lint・型検査・単体テスト）。build のように前の工程が必要なものには付けません。
- System Test は、`ledger.py run --jobs N|auto`（または設定の `system_test.jobs`）で同時に実行します。既定は `auto`（CPU 数 ÷ 4、2〜6）です。ケースに `"serial": true` を付ける、または command が `system_test.serial_patterns`（既定は `default_port`）の文字列を含むと、並列の実行が終わってから単独で動きます。同じ command のケースは 1 回だけ実行し、結果を共有します。さらに、同じ pytest ファイルを指す command（`python -m pytest <file>[::node] [-k 式] [-q]` の形）が 2 つ以上あるときは、1 つの pytest プロセスにまとめて実行し（`-k` は pytest と同じ文法で JUnit の結果から各ケースに振り分けます）、失敗したケースとどのテストにも当たらなかったケースだけを単独で再実行します（判定とログは従来どおり）。実測（GUI を含む 45 ケース）で 320 秒 → 281 秒でした。止めるには `ledger.py run --no-batch` か `system_test.batch_pytest: false`。canary・serial のケースはまとめません。GUI のサーバー起動をテストごとに行う fixture（function scope）を module scope にすると、さらに短くなります（テストの状態の分離を確認してから）。canary は常に先に単独で動きます。

**Azure は、既定では使いません。** 次の条件が揃ったときだけ、利用者が選びます（実行時のオプションとしては実装していません）。
1. 手元のマシンが小さい（コア数が 8 未満、またはメモリが 32 GB 未満）。
2. `kpi.py run` で、実効の並列度が `parallel_workers` に届かず、その原因が CPU の不足（verify・System Test の所要時間が支配的）である。
3. モデルの応答待ち（LLM の時間）が支配的でないこと。クラウドの VM を増やしても、LLM の待ち時間は短くなりません。

前回の実測では、LLM 以外の時間の大半は、統合の直列区間・検査の重複・テストランナーの過剰な並列でした。これらは上の設定とキャッシュで解消でき、VM は不要でした。検査だけを Azure の VM（例: 32 コアの Dev/Test）で動かす場合は、VM 上に作業ツリーを置いて `parallel_workers` を VM のコア数に合わせ、料金（paid_services）を run のオプションで許可してください。
