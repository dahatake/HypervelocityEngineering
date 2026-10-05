通常run/入力fields参照時のみ; 実行前gate/承認はroot

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
      ],
      "step_inputs": [
        {
          "step_id": "2.1",
          "role": "additional",
          "source": "inputs/supplement.pdf"
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
| `goal` | 既存 `--additional-prompt` へ渡る文字列。shell として解釈されない。省略可（省略時は `""` で、`--additional-prompt` を付けない）。`null` などの非文字列は拒否される。 |
| `workflow_id` | `hve/workflow_registry.py` の canonical ID（`python -m hve orchestrate --help` ではなく registry が正本）。 |
| `steps` | 当該 Workflow に実在する Step ID のみ。省略時は既定の選択。 |
| `params` | 当該 Workflow が宣言したパラメータのみ。値は文字列。 |
| `settings_overrides` | `hve/prompt_request.py` の `ALLOWED_SETTINGS_OVERRIDES` のキーのみ。token / password / 任意 env / 任意コマンドは拒否。 |
| `input_aliases` | 下記「入力別名」の制約に従う。 |
| `step_inputs` | 実行Stepへ追加・代替するrun-scoped文書の順序付き配列。下記「Step入力」の制約に従う。 |
| `execution_policy` | 任意（FR-PROMPT-13）。`{"unattended": true, "pre_approved_operations": ["azure_deploy"], "allow_public_exposure": false, "budget_note": "..."}` の形で、利用者が宣言した事前承認の範囲だけを置く。操作は `azure_deploy` だけ。`azure_deploy` には `resource_group` を持つ Workflow の `params.resource_group` が必要。`budget_note` は 200 文字以内で改行を含まない記録用メモ（上限の強制ではない）。省略時は従来どおり。値は子 `orchestrate` の非公開引数と plan SHA-256 に入る。 |

`dry_run` / plan hash / 実行順 / `workbench` は Prompt CLI が所有し、request から上書きできない。

### 実行計画に表示される完了条件（FR-DOD-03）

`hve prompt plan` が提示する実行計画には、Workflow ごとに `- 完了条件（宣言 output_paths）:` が表示される。値は `hve/workflow_registry.py` の選択済み Step が宣言する `output_paths` であり、宣言が 0 件の場合は `(宣言なし)` と表示する。値を推測・補完してはならない。

この表示は plan hash の入力（`canonical_plan_json`）に含まれないため、承認 SHA-256 は本表示の有無で変化しない。request v1 に完了条件用の field は無く、追加もしない。

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

## Step入力（追加資料 / 欠損文書の代替）

`workflows[].step_inputs`は、そのrunの特定Stepだけへ任意文書を渡す。宣言順を維持し、原本やcanonical pathを変更・上書きしない。

- `step_id`は選択範囲内のnon-container Step。containerを選択した場合は登録済みの子実行Stepを指定する。
- `role`は`additional`または`substitute`。`substitute`では`canonical`が必須で、canonical文書が欠損し、かつI/O contract上で変換可能な文書入力の場合だけ受理する。
- `source`はlocalで実在する文書パス。PDF / Office等は既存Microsoft MarkItDown経路でrun-scoped Markdownへ変換する。
- 同じcanonicalを`input_aliases`と重複指定しない。
- request作成前にWorkflow / Step、sourceの存在、代替対象canonicalをread-onlyで確認し、推測でpathを作らない。
- plan SHA-256にはbundleの内容・順序・role・canonical / actual対応・digestが含まれる。変更時は再plan・再提示・再承認する。

利用者向けの4面共通手順は[users-guide/step-inputs.md](../../../../users-guide/step-inputs.md)を参照する。

## 入力別名（canonical → actual）

その run に限って canonical 入力を **リポジトリ内の実ファイル** へ読み替える。
ファイルはコピーせず、出力契約（`StepDef.output_paths` / `.github/io-contracts/`）も変更しない。

- `canonical` は選択した Step の `required_input_paths` に**リテラルで一致**するものだけ。
- v1 は glob（`*` `?` `[`）、placeholder（`{` `}`）、ディレクトリ入力を受理しない。
- `actual` はリポジトリ内の相対パスの通常ファイル。絶対パス・`..`・symlink・不存在は拒否。
- 同じ canonical への重複指定、選択済み上流 Step が生成する出力の差し替えは拒否。