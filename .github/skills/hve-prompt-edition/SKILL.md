---
name: hve-prompt-edition
description: >
  Turn a natural-language Markdown prompt into a typed HVE request, show the
  dry-run plan, and only run existing workflows after explicit approval.
  USE FOR: run an HVE workflow from a written request, plan ard/aas/aad-web/
  asdw-web/adfd/adfdv/ada/aag/aagd/aar/akm/adi/adoc from prose, combine several
  workflows in dependency order, point a workflow at an input file whose name
  differs from the canonical path.
  DO NOT USE FOR: editing workflow_registry.py, adding a new workflow or step,
  GitHub Cloud Agent Orchestrator runs, arbitrary shell execution, changing
  output paths or I/O contracts.
  WHEN: the user describes work in prose and expects HVE to execute it, and the
  target workflow, steps and inputs can be named exactly without guessing.
metadata:
  origin: user
  version: 0.1.0
category: planning
---

# hve-prompt-edition

HVE の **第 4 の利用面**（Prompt 版）を扱う Skill。Cloud / GUI / CLI と並ぶ入口だが、
**新しい実行エンジンではない**。自然言語を型付き request へ変換し、既存の
`hve orchestrate` へ委譲するだけの薄い境界である。

対応面: HVE GUI 内の既存 **Copilot CLI** タブ / standalone **GitHub Copilot CLI** /
**VS Code Copilot Chat**。GitHub.com の Cloud Agent Orchestrator は本 Skill の対象外。

## 最短手順（すべて Agent が実行する）

下記は **Agent が内部で実行する手順**であり、利用者へ提示する手順ではない。
利用者は日本語で依頼と承認を伝えるだけでよい。

```sh
# 1. request を書き出す（UTF-8 JSON）
#    → work/run/<run-id>/.../artifacts/request.json

# 2. 計画だけを取得する（書き込みなし）
python -m hve prompt plan --request work/run/<run-id>/.../artifacts/request.json

# 3. 利用者が計画を読み、明示的に承認したときだけ実行する
#    hex は Agent が plan の出力から転記する
python -m hve prompt run --request work/run/<run-id>/.../artifacts/request.json \
  --expected-sha256 <plan が表示した 64 桁 hex>
```

`hve prompt plan` は全 Workflow を `orchestrate --dry-run` で実行し、実行予定の argv と
plan SHA-256 を表示する。成果物（`docs/` / `src/` / `knowledge/` / `qa/`）は生成・変更しないが、
`orchestrate` 既存の副作用として run ディレクトリ `work/run/<run-id>/` の作成と検索索引の更新は発生する。
`--dry-run` は上流成果物の不足を検出しないため、依存の満たし方は利用者へ確認すること。

`hve prompt run` は同じ計画を再計算し、SHA-256 が一致しない
場合は **子プロセスを 1 つも起動せずに停止** する。

## 利用者との対話（自然言語だけで完結させる）

**利用者はコマンドを一切入力しない。** CLI の起動、request の保存先パスの管理、
plan SHA-256 の転記はすべて Agent が代行する（FR-PROMPT-10）。

| 局面 | Agent がやること |
|---|---|
| 依頼を受けた | request を作り、`prompt plan` を実行し、**計画の要約（日本語）と plan 出力をそのまま**提示する |
| 計画を提示した | 「この内容で実行してよいか」を日本語で問う。hex の入力を求めない |
| 承認を得た | plan 出力の SHA-256 を `--expected-sha256` へ転記して `prompt run` を実行する |
| stale で停止した | 利用者へ再実行を指示せず、Agent が `prompt plan` をやり直して再提示し、承認を取り直す |

### 承認の受け取り方

承認語を網羅列挙しない。**この計画を実行する意思が明確か**だけで判定する。

- 承認とみなす例: 「実行してください」「この計画で進めてください」「承認します」
- 承認とみなさない例: 「いいね」「たぶん大丈夫」「問題なさそう」などの曖昧な同意
- 曖昧なときは実行せずに再確認する。
- 計画を提示する前の「先に全部やって」は承認として扱わない。

自然言語の承認だけでは実行されない。実際のゲートは `--expected-sha256` の一致であり
（FR-PROMPT-04）、これを緩和してはならない。

## 責務分界

| 担当 | やること | やらないこと |
|---|---|---|
| 本 Skill（LLM 側） | 自然言語の解釈、不足情報の質問、request の生成、CLI の起動、計画の要約提示、SHA-256 の転記 | Workflow の実行判断、shell 文字列の組み立て、利用者へのコマンド入力依頼 |
| HVE Python 側 | request の再検証（schema / registry / allowlist / path policy）、計画・hash、`orchestrate` 委譲 | 自然言語の解析 |

HVE Python は request を **信用しない**。Skill が誤った値を書いても、registry に無い
Workflow ID・Step ID・パラメータは実行前に拒否される。

## request v1

```json
{
  "schema_version": 1,
  "goal": "実施したい内容を 1〜3 文で",
  "workflows": [
    {
      "workflow_id": "aad-web",
      "steps": ["1", "2.1"],
      "params": { "app_ids": "APP-009" },
      "input_aliases": [
        {
          "canonical": "docs/catalog/app-catalog.md",
          "actual": "inputs/my-app-catalog.md"
        }
      ]
    }
  ],
  "settings_overrides": { "model": "<GUI で選択済みのモデル>" }
}
```

| フィールド | 規則 |
|---|---|
| `schema_version` | 整数 `1` のみ。未知の値・未知のフィールドは fail-closed。 |
| `goal` | 既存 `--additional-prompt` へ渡る文字列。shell として解釈されない。 |
| `workflow_id` | `hve/workflow_registry.py` の canonical ID（`python -m hve orchestrate --help` ではなく registry が正本）。 |
| `steps` | 当該 Workflow に実在する Step ID のみ。省略時は既定の選択。 |
| `params` | 当該 Workflow が宣言したパラメータのみ。値は文字列。 |
| `settings_overrides` | `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` のキーのみ。token / password / 任意 env / 任意コマンドは拒否。 |
| `input_aliases` | 下記「入力別名」の制約に従う。 |

`dry_run` / plan hash / 実行順 / `workbench` は Prompt CLI が所有し、request から上書きできない。

### 設定値の解決順（FR-LOCAL-SURFACE-01）

Prompt 版は GUI が保存した設定を基準値として引き継ぐ。優先順位は次のとおり。

1. request の `settings_overrides`（その run 限り）
2. GUI が保存した設定（`hve/.settings.txt`）
3. 既定値

`settings_overrides` に置けるのは「3 面共有設定」だけで、Workflow 固有の値は `workflows[].params` に置く。両者を取り違えると fail-closed で停止する。

| 種別 | 置き場所 | 例 |
|---|---|---|
| 3 面共有設定 | `settings_overrides` | `model` / `strict` / `enable_tool_search` / Agentic Retrieval 6 項目 / `cloud_session_branch` |
| Workflow 固有 | `workflows[].params` | `app_ids` / `resource_group` / `create_remote_mcp_server` / `tdd_max_retries` |

正本は `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` と `hve/workflow_registry.py` の `WorkflowDef.params`。ここへ件数や一覧を固定記述せず、必ず正本を確認する。

## 入力別名（canonical → actual）

その run に限って canonical 入力を **リポジトリ内の実ファイル** へ読み替える。
ファイルはコピーせず、出力契約（`StepDef.output_paths` / `.github/io-contracts/`）も変更しない。

- `canonical` は選択した Step の `required_input_paths` に**リテラルで一致**するものだけ。
- v1 は glob（`*` `?` `[`）、placeholder（`{` `}`）、ディレクトリ入力を受理しない。
- `actual` はリポジトリ内の相対パスの通常ファイル。絶対パス・`..`・symlink・不存在は拒否。
- 同じ canonical への重複指定、選択済み上流 Step が生成する出力の差し替えは拒否。

## 質問するとき / 止まるとき

次のいずれかが自然言語から**一意に定まらない**場合は、request を作らずに利用者へ質問する。

- どの Workflow か（例:「設計」だけでは `aad-web` / `adfd` / `aag` を選べない）
- どの Step まで進めるか（Azure への deploy を含むか）
- APP-ID / リソースグループ / 対象ディレクトリなど、registry が要求するパラメータ
- 入力ファイルの実パス（canonical と異なる名前を使う場合）

**推測で値を埋めてはならない。** 存在しない Workflow ID・Step ID・ファイルパス・APP-ID を
生成した場合、HVE 側で拒否されるか、意図しない対象へ実行される。不明な項目は
`TBD（要確認）` として質問へ回す。

## 禁止事項

- `hve prompt plan` を飛ばして `hve prompt run` を実行すること。
- 利用者の明示的な承認なしに `run` を実行すること。「たぶん良いだろう」は承認ではない。
- 計画と plan SHA-256 を提示しないまま `run` すること。（提示と承認の後で hex を転記するのは Agent の責務であり、利用者に hex を入力させてはならない）
- 利用者へコマンド・request のファイルパス・SHA-256 の入力やコピーを依頼すること。
- Markdown Prompt 本文から shell 文字列を組み立てて直接実行すること。
- request にトークン・パスワード・接続文字列を書くこと。認証は既存経路のみを使う。
- `docs-original/` の変更を依頼すること（読み取り専用）。

## 利用者向け文書

- [users-guide/hve-prompt-getting-started.md](../../../users-guide/hve-prompt-getting-started.md) — Quick Start
- [users-guide/prompts/README.md](../../../users-guide/prompts/README.md) — Workflow 別の貼り付け用 Prompt 索引

## 関連実装

- `hve/prompt_request.py` — request v1 の型・検証
- `hve/prompt_execution.py` — 計画組み立て・canonical JSON・SHA-256・委譲実行
- `hve/input_aliases.py` — 入力別名の安全性検証
- `hve/workflow_order.py` — `get_meta_dependencies()` に基づく安定ソート
