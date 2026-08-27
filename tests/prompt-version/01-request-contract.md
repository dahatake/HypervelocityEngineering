# 01. request v1 契約の統合テスト（FR-PROMPT-02）

## GitHub Copilot に貼り付ける Prompt

以下のコードブロック全体をコピーして貼り付けてください。

````markdown
このリポジトリで、HVE Prompt 版統合テスト「01. request v1 契約の統合テスト（FR-PROMPT-02）」を
実施してください。必要なコマンドとファイル操作はすべてあなたが実行し、利用者にコマンド、
request の保存先、plan SHA-256 の入力を求めないでください。実測していない結果を作らず、
以下の目的、前提、実施項目、記録すること、重要をすべて満たしてください。
開始前に `tests/prompt-version/README.md` の全 Prompt 共通の前提・禁止事項・既知の未修正事項を確認してください。

## 目的

- `hve` の **Prompt 版** が受け取る `request v1`（UTF-8 JSON）の **受理条件と拒否条件** を実測で検証する。
- HVE Python が「自然言語生成物を信用せず、schema・registry・allowlist で再検証する」契約
  （`hve-dev/requirement-definition.md` §5.20 FR-PROMPT-02）が実装と一致しているかを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-request/Issue-prompt-version-integration-test/README.md` に
  Markdown で保存する。`artifacts/` 配下に使用した request ファイルと実出力を残す。

## 前提

- リポジトリ直下で作業する。
- `python -m hve prompt plan --help` が動作すること。
- 正本は次の 2 つ。テスト中に変更しないこと。
  - `hve/prompt_request.py`（`SCHEMA_VERSION` / `ALLOWED_SETTINGS_OVERRIDES`）
  - `hve/workflow_registry.py`（Workflow ID / Step ID / Workflow 固有パラメータ）

## 実施項目

### A. 正常系（受理されること）

1. 最小 request（`schema_version` / `goal` / `workflows` のみ）で `hve prompt plan` が計画を提示する。
2. `steps` に **registry に実在する Step ID** を指定した request が受理される。
   - Step ID は推測せず、`python -c "from hve.workflow_registry import get_workflow; w=get_workflow('<id>'); print([s.id for s in w.steps])"` で取得する。
3. `params` に **当該 Workflow が宣言しているパラメータ名のみ** を含む request が受理される。
   - 宣言一覧は `python -c "from hve.workflow_registry import get_workflow; print(list(get_workflow('<id>').params))"` で取得する。
4. `settings_overrides` に `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` のキーだけを含む request が受理される。

### B. 異常系（実行前に拒否されること）

各ケースで **終了コードが 0 以外** であり、**子プロセスが 1 つも起動しない** ことを確認する。

| # | 入力 | 期待 |
|---|---|---|
| B1 | `schema_version` が `2` / `"1"` / `true` / 欠落 | 拒否 |
| B2 | トップレベルに未知フィールド（例 `"extra": 1`） | 拒否 |
| B3 | `workflows` が空配列 / 配列でない | 拒否 |
| B4 | 同じ Workflow を 2 回指定 | 拒否 |
| B5 | JSON に重複キー | 拒否 |
| B6 | `workflow_id` が registry に無い（例 `"nope"`） | 拒否 |
| B7 | `steps` に当該 Workflow へ存在しない Step ID | 拒否 |
| B8 | `params` に当該 Workflow が宣言していないキー | 拒否 |
| B9 | `params` の値が文字列でない（数値 / bool / null） | 拒否 |
| B10 | `settings_overrides` に allowlist 外のキー（例 `token` / `cli_path` / `mcp_config` / `repo_root`） | 拒否 |
| B11 | `settings_overrides` に `dry_run` / `workbench` / `workflow` / `steps` | 拒否（Prompt CLI が所有する値のため） |
| B12 | `input_aliases` の要素に `canonical` または `actual` が無い / 空文字 | 拒否 |
| B13 | request ファイルが存在しない / UTF-8 でない / JSON として不正 | 拒否 |

### C. 境界の確認（**捏造しないこと**）

1. `params` は request 段階では registry の宣言名だけを検査する。
   `OrchestrateArgs` に対応フィールドが無いパラメータ（`include_kpi_okr` / `tdd_max_retries` /
   `create_remote_mcp_server`）は **計画組み立て時**に拒否される。
   どの段階で拒否されたかをエラーメッセージ本文で区別して記録する。
2. `params` の値は文字列だが、`OrchestrateArgs` のフィールド型（list / 3 状態 bool / int）へ
   変換されて argv になる。以下を実測し、argv を記録する。
   - `akm` の `target_files=qa/a.md,qa/b.md` → `--target-files qa/a.md qa/b.md`（1 文字ずつ分解されないこと）
   - `akm` の `force_refresh=true` / `false` → `--force-refresh` / `--no-force-refresh`
   - `adoc` の `max_file_lines=500` → `--max-file-lines 500`
   - `adoc` の `max_file_lines=たくさん` → 拒否

## 記録すること

- 各ケースの **実際のコマンド・終了コード・stderr 本文**（要約せず引用する）
- 拒否理由が **actionable**（何を直せばよいか分かる）かどうかの評価
- 期待と実装が食い違った場合は、`hve-dev/requirement-definition.md` §5.20 のどの条文に反するかを明示

## 重要

- **捏造は絶対に禁止**です。実行していないケースを「合格」と書いてはいけません。
- Workflow ID・Step ID・パラメータ名を **推測で書かない**こと。必ず registry から取得する。
- テストを通すために `hve/prompt_request.py` や `hve/workflow_registry.py` を書き換えないこと。
- 並列で実行できるケース（B1〜B13 は互いに独立）は並列実行してよい。
  各ケース完了後に敵対的レビューを行い、レビュー結果を反映してから次へ進むこと。
````
