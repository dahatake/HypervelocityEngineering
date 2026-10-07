# 4. 設定とカスタマイズ

設定は `scripts/hve.config.json` に集約しています。インストール・更新時には、利用者が設定した値は保持され、新しいキーだけが追加されます。

## 4.1 ビルド・静的解析・テストのコマンド（`verify.commands`）

`scripts/verify.py` は、管理データの検査（CHK-01〜23）の後に、ここに登録したコマンドを順に実行します。1 つでも失敗すると exit 1 になります。

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

技術スタック別の例:

| スタック | 例 |
|---|---|
| .NET | `dotnet build --nologo`、`dotnet test --nologo` |
| Python | `python -m ruff check .`、`python -m pytest -q` |
| Java (Gradle) | `./gradlew build` |
| Go | `go vet ./...`、`go test ./...` |

ログの全文は `/work/runs/<run-id>/logs/`（run がないときは `/work/logs/`）に保存され、コンソールには失敗の要約だけが出力されます。

## 4.2 モデルの割り当て（`models`）

```json
"models": {
  "conductor": "",
  "rd-author": "",
  "rd-auditor": "",
  "test-designer": "",
  "implementer": "",
  "implementer-escalation": "",
  "reviewer": ""
}
```

conductor は subagent を呼び出すとき、この表のモデルを指定します。空なら既定のモデルを使います。各 `.github/agents/*.agent.md` の frontmatter に `model:` を書いて固定することもできます（推奨値はコメントに書いてあります）。

割り当ての方針（Phase 1 で調整します）:

| 役割 | 方針 |
|---|---|
| conductor、rd-author | 推論能力の高いモデル |
| rd-auditor | rd-author とは**別系統**のモデル（同じバイアスを共有しないため） |
| test-designer、reviewer | 中位のモデル |
| implementer | 低〜中位のモデル（仕様が明確なため） |
| implementer-escalation | 同じ項目で失敗が続いたときに 1 回だけ使う上位モデル |

調整の方法: 代表的な作業（要求 3 件分）を、モデルの組み合わせ 2〜3 通り × 2 回ずつ実行します。`docs/run-history.md` の AC pass 率・1 回目のゲート通過率・経過時間と、使用量の表示（AI クレジット）を比較して決めます。**最も安いモデルが、最も安い結果になるとは限りません**（手戻りでコストが逆転します）。

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
| `deploy_patterns` | デプロイとみなすコマンドの正規表現。指定すると既定値（`scripts/hvelib.py` の `DEFAULT_CONFIG`）を**置き換える**ので、既定値をコピーしてから追加します |
| `external_write_verbs` | MCP Server・plugin・拡張機能のツールのうち、名前にこの動詞（`create`・`update`・`delete`・`send`・`do_action` など）を含むものを「外部のシステムの変更」とみなします（G-5。[4.4](#44-mcp-serverplugin拡張機能を使う)）。指定すると既定値を**置き換えます** |
| `external_deploy_verbs` | 同じく、名前にこの動詞（`deploy`・`provision`・`publish`・`release`）を含むものを「デプロイ・公開」とみなし、`deploy` の値で判定します |
| `external_tool_allow` | 外部のシステムの変更とみなさないツール名の正規表現（例: `"^mcp_myindex_update_index$"`）。名前に動詞を含むが、ローカルにしか作用しないツールを許可するときに使います |

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
| `base_branch` | `main` | マージ先のブランチ。差分の検査（CHK-12/13）と、push の拒否（G-5）に使います |
| `work.retention_days` | 14 | `/work/runs/` の保持日数 |
| `checks.ambiguous_words` | 適切、迅速、直感的 など | 曖昧な語のリスト（CHK-13） |
| `checks.id_scan_exclude` | `docs/**` など | コードから要求 ID を検索するときに除外するパス（CHK-17/19） |
| `checks.test_path_pattern` | tests/、*.test.* など | テストコードとみなすパス（CHK-09） |

## 4.6 エージェントと手順書を変更する

- 役割ごとの振る舞いは `.github/agents/*.agent.md`、詳しい手順は `.github/skills/*/SKILL.md` に定義しています。直接編集してかまいません。
- インストールスクリプトを再実行しても、ローカルで変更したファイルは上書きされません（`KEEP-LOCAL`）。toolkit の新しいバージョンを取り込みたい場合は、`--dry-run` で確認してから、差分を手でマージするか、`--force`（バックアップを残します）を使います。
- skills の本文は、元になった 3 つの Prompt（RequirementDefinition作成・RD-FR_Prompt・SystemTest-Increment-Run）の全文です。先頭の「読み替え表」が、元の Prompt と無人実行との差分を吸収しています。元の Prompt を改訂した場合は、本文を差し替え、読み替え表はそのまま残します。

## 4.7 CI

`.github/workflows/hve-verify.yml` は、pull request と main への push をトリガーに `scripts/verify.sh --show-warnings` を実行します。アプリのビルドに必要なツールチェーン（`actions/setup-node` など）は、verify の前にステップとして追加します。CodeQL や依存関係のスキャンを加える場合も、このワークフローに追記します。
