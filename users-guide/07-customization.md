# 7. 設定とカスタマイズ

設定は `scripts/hve.config.json` に集めています。導入・更新のときは、利用者が書いた値は保たれ、新しい項目だけが足されます。

## 7.1 ビルド・静的検査・テストのコマンド（`verify.commands`）

`scripts/verify.py` は、管理データの検査（CHK-01〜23）のあとに、ここに登録したコマンドを順に実行します。1 つでも失敗すれば exit 1 です。

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
| `name` | 表示名・ログのファイル名 |
| `run` | リポジトリのルートで実行するシェルのコマンド |
| `slow` | `true` なら、作業役のゲート（`verify.py --quick`）では省き、統合時と最終だけで実行します |
| `timeout_sec` | このコマンドの時間上限（既定は `verify.timeout_sec`） |

技術スタック別の例:

| スタック | 例 |
|---|---|
| .NET | `dotnet build --nologo`、`dotnet test --nologo` |
| Python | `python -m ruff check .`、`python -m pytest -q` |
| Java (Gradle) | `./gradlew build` |
| Go | `go vet ./...`、`go test ./...` |

ログの全文は `/work/runs/<run-id>/logs/`（run がないときは `/work/logs/`）に保存され、画面には失敗の要約だけが出ます。

## 7.2 モデルの割り当て（`models`。§7.2、§11 T-3、§12 Phase 1）

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

conductor は subagent を呼ぶとき、この表のモデルを指定します。空なら既定のモデルです。各 `.github/agents/*.agent.md` の frontmatter に `model:` を書いて固定することもできます（コメントで推奨を書いてあります）。

方針（Phase 1 で較正します）:

| 役割 | 方針 |
|---|---|
| conductor、rd-author | 推論の強いモデル |
| rd-auditor | rd-author とは**別系統**のモデル（偏りの共有を避ける） |
| test-designer、reviewer | 中位のモデル |
| implementer | 低〜中位のモデル（仕様が明確なため） |
| implementer-escalation | 同じ項目が失敗を重ねたときに 1 回だけ使う強いモデル |

較正のしかた: 代表的な作業（要求 3 件分）を、モデルの組み合わせ 2〜3 通り × 2 回ずつ実行し、`docs/run-history.md` の AC pass 率・1 回目のゲート通過率・経過時間と、使用量の表示（AI クレジット）を比べて決めます。**最安のモデルが最安の結果になるとは限りません**（手戻りで逆転します。R-21）。

## 7.3 ゲートの調整（`gates`）

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
| `enabled` | `false` で hook のゲートをすべて無効にします（verify の検査は残ります）。原因の切り分けのときだけ使います |
| `subagent_verify` | 作業役が終わる前に実行する verify の引数（G-4）。ここにない作業役は検査しません |
| `subagent_verify_max_blocks` | 同じ作業役を差し戻す上限。超えたら結果に `GATE G-4` を付けて返し、conductor はその結果を統合しません |
| `agent_stop_max_blocks` | 完了条件を満たさない conductor の終了を差し戻す上限 |
| `enforce_conductor_edit_scope` | conductor が `work/` と `docs/run-history.md` 以外を編集するのを拒否します。subagent の検出が harness で動かない場合（[10-troubleshooting.md](10-troubleshooting.md)）だけ `false` にします |
| `deploy_patterns` | デプロイとみなすコマンドの正規表現。書くと既定値（`scripts/hvelib.py` の `DEFAULT_CONFIG`）を**置き換える**ので、既定値を写してから足します |

## 7.4 そのほか

| キー | 既定 | 意味 |
|---|---|---|
| `management_files` | `docs/requirements-definition.md` など | 管理データのパス。既存の構成に合わせて変えられます |
| `base_branch` | `main` | 取り込み先のブランチ。差分の検査（CHK-12/13）と、push の拒否（G-5）に使います |
| `work.retention_days` | 14 | `/work/runs/` の保持日数（A-5） |
| `checks.ambiguous_words` | 適切、迅速、直感的 など | 曖昧な語の一覧（CHK-13） |
| `checks.id_scan_exclude` | `docs/**` など | 要求 ID をコードから探すときに除くパス（CHK-17/19） |
| `checks.test_path_pattern` | tests/、*.test.* など | テストコードとみなすパス（CHK-09） |

## 7.5 エージェントと手順書を変える

- 役割の振る舞いは `.github/agents/*.agent.md`、詳しい手順は `.github/skills/*/SKILL.md` にあります。直接編集してかまいません。
- 導入スクリプトを再実行しても、ローカルで変更したファイルは上書きされません（`KEEP-LOCAL`）。toolkit の新しい版を取り込みたいときは、`--dry-run` で確認し、差分を手で取り込むか `--force`（バックアップを残す）を使います。
- skills の本文は、原本の 3 Prompt（RequirementDefinition作成・RD-FR_Prompt・SystemTest-Increment-Run）の全文です。先頭の「読み替え表」が、原本と無人実行の差を埋めています。原本を改訂したときは、本文を差し替え、読み替え表はそのまま残します。

## 7.6 CI

`.github/workflows/hve-verify.yml` は、pull request と main への push で `scripts/verify.sh --show-warnings` を実行します。アプリのビルドに必要なツールチェーン（`actions/setup-node` など）は、verify の前に足します。CodeQL や依存関係の確認を加える場合も、このワークフローに追記します。
