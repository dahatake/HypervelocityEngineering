# 02. plan の提示内容と run の承認ゲート（FR-PROMPT-03 / 04 / 05）

## GitHub Copilot に貼り付ける Prompt

以下のコードブロック全体をコピーして貼り付けてください。

````markdown
このリポジトリで、HVE Prompt 版統合テスト「02. plan の提示内容と run の承認ゲート
（FR-PROMPT-03 / 04 / 05）」を実施してください。必要なコマンドとファイル操作はすべてあなたが実行し、
利用者にコマンド、request の保存先、plan SHA-256 の入力を求めないでください。実測していない結果を
作らず、以下の目的、前提、実施項目、記録すること、重要をすべて満たしてください。
開始前に `tests/prompt-version/README.md` の全 Prompt 共通の前提・禁止事項・既知の未修正事項を確認してください。

## 目的

- `hve prompt plan` が提示する内容と、`hve prompt run` の **plan SHA-256 一致ゲート** を実測で検証する。
- 「自然言語上の『承認』だけで書き込みを開始しない」という Prompt 版の中核契約が守られているかを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-gate/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- リポジトリ直下で作業する。
- 作業ツリーの `git rev-parse HEAD` を記録しておく（plan hash に HEAD が含まれるため）。
- `C8` は共通前提どおり、対象 revision から作った **専用の隔離 worktree** で実施する。共有作業ツリーでは実行しない。
- 全ケースで次の固定 request を使う。`settings_overrides.model` は指定しない（C6 で保存設定の変更を hash に反映させるため）。

```json
{
   "schema_version": 1,
   "goal": "Prompt 承認ゲートの非 Azure 検証",
   "workflows": [
      {
         "workflow_id": "ard",
         "steps": ["1"],
         "params": {"company_name": "Prompt Gate Test"}
      }
   ],
   "settings_overrides": {
      "auto_qa": false,
      "auto_contents_review": false
   }
}
```

- `ard` Step `1` は registry 上の `Arch-ARD-BusinessAnalysis-Untargeted` で、canonical output は `docs/company-business-recommendation.md`、Azure 書き込み・remote CI/CD・Wave 承認は不要であることを実行直前にも確認する。
- C8 の前に、隔離 worktree 内の `docs/company-business-recommendation.md` が存在する場合だけ削除し、この run が空でない canonical output を新規生成したことを確認できる状態にする。

## 実施項目

### A. `plan` の提示内容

1. 1 Workflow の request で `python -m hve prompt plan --request <path>` を実行し、
   出力に次がすべて含まれることを確認する。
   - `HEAD:` 行
   - `実行順:` 行
   - Workflow ごとの `Step:` 行
   - Workflow ごとの `argv:` ブロック
   - `plan SHA-256:` 行（64 桁 hex）
2. 表示された argv が **`orchestrate` で始まり `--dry-run` を含まない**ことを確認する。
3. 出力末尾の承認案内が **利用者へコマンド入力を求めていない**ことを確認する（FR-PROMPT-03）。
   - `hve prompt run ...` を手実行せよという指示が含まれていない
   - 「利用者へコマンドの入力を求めてはならない」旨の記述がある
   - argv の注記が「利用者が手で打つ必要はありません」となっている

### B. `plan` の副作用（**実態を測ること**）

要件は「**成果物**（`docs/` / `src/` / `knowledge/` / `qa/`）を生成・変更しない」であり、
「一切書き込まない」ではない。実測して差分を記録する。

1. 実行前に `git status --porcelain` と `docs/` `src/` `knowledge/` `qa/` のファイル一覧＋mtime を取得する。
2. `hve prompt plan` を実行する。
3. 実行後に同じ情報を取得し、**成果物ディレクトリに差分が無いこと**を確認する。
4. 併せて次の既知の副作用が発生するかを実測し、そのまま記録する（不具合として報告しない）。
   - `work/run/<run-id>/` ディレクトリの新規作成
   - `.mdq/` / `.cq/` の索引ファイル更新

### C. `run` の承認ゲート（最重要）

C1〜C6 では **子 `orchestrate` が 1 つも起動しないこと** を確認する。HEAD 取得用の
`git rev-parse` は許容されるため、「任意の子プロセスが 0 件」と記録してはならない。
成果物差分や `work/run/` の増減は補助証跡にしかならず、非起動の代用にはしない。
次の既存 unit test の recorder が `orchestrate` 呼び出し 0 件を確認することを機械証跡とする。

```text
hve/tests/test_prompt_cli.py::TestPromptRunApprovalGate::test_mismatched_hash_starts_no_orchestrate_subprocess
hve/tests/test_prompt_cli.py::TestPromptRunApprovalGate::test_malformed_hash_starts_no_orchestrate_subprocess
```

実 CLI では終了コード・stderr と `Copilot SDK Orchestrator:` 見出しの不在も併記する。

| # | 入力 | 期待 |
|---|---|---|
| C1 | `--expected-sha256` を省略 | argparse がエラー終了（必須引数） |
| C2 | `--expected-sha256 abc`（64 桁未満） | 拒否。子 `orchestrate` 0 件 |
| C3 | 64 桁だが hex でない文字を含む | 拒否。子 `orchestrate` 0 件 |
| C4 | 正しい形式だが plan と不一致 | `stale` として拒否。期待値と実際値の両方が表示される |
| C5 | `plan` 提示後に request の `goal` だけを `Prompt 承認ゲートの変更後検証` へ変え、同じ hash で `run` | 拒否。変更後 request が schema-valid であることも確認 |
| C6 | 隔離 worktree の `hve/.settings.txt` だけで、保存設定 `strict` を `false` から `true` へ変えてから同じ hash で `run` | 拒否。request が `strict` を override していないことと、再計算 hash が変わったことも確認 |
| C7 | `hve/tests/test_prompt_execution.py::TestSha256::test_head_change_changes_hash` | PASS。共有・隔離を問わず、この確認だけのために新しい commit を作らない |
| C8 | `plan` が提示した hash をそのまま指定 | 実行され、子 `orchestrate` への委譲を観測できる |

C2 / C3 の拒否メッセージに、hex の転記は Agent の責務である旨が含まれることも確認する。

- `C8` は、plan を利用者へ提示して一度停止し、利用者が**別ターンで明示承認した後**にだけ実行する。この統合テストの開始依頼を C8 の事前承認として扱わない。
- `C8` では、`hve prompt run --expected-sha256 <正しい hash>` の実行後に、出力の `Copilot SDK Orchestrator:` 見出しから子 `orchestrate` の起動を確認する。
- `C8` では、選択した非 Azure Step が `plan.md` / `subissues.md` だけで終了せず、canonical `output_paths` に空でない成果物を生成することを確認する。

### D. hash の決定性

1. 同じ request・同じ設定・同じ HEAD で `plan` を 2 回実行し、**同じ SHA-256** になることを確認する。
2. `settings_overrides.model` だけを変えた request で hash が変わることを確認する。
3. `steps` の指定順だけを変えた request で hash がどうなるかを実測し、結果を記録する
   （期待値を先に決めつけず、実測結果を `hve/prompt_execution.py` の `canonical_plan_json` と突き合わせる）。

### E. 複数 Workflow の fail-fast（最初の失敗で停止）

失敗条件を実 Workflow や外部リソースへ依存させず、次の既存 recorder テストを実行する。

```text
hve/tests/test_prompt_cli.py::TestPromptRunApprovalGate::test_fail_fast_between_workflows
hve/tests/test_prompt_execution.py::TestRunPlan::test_fail_fast_stops_subsequent_workflows
```

両テストが、第 1 Workflow の非 0 終了後に第 2 Workflow の `orchestrate` を起動しないことを確認する。
このケースには成功済み Workflow が存在しないため、rollback の有無を検証したとは報告しない。

## 記録すること

- 各ケースの実コマンド・終了コード・stdout / stderr の該当行
- `plan` 前後のファイル差分（成果物ディレクトリ / `work/run/` / 索引）
- hash が変わった / 変わらなかった条件の一覧

## 重要

- **捏造は絶対に禁止**です。「子プロセスが起動しなかった」は必ず実測根拠とセットで書くこと。
- **C8 以外で `run` が実行されてしまった場合は Critical** として報告する。
- `C1`〜`C7` で確認した拒否 gate が維持され、**正しい hash の `C8` でだけ** 実行へ進むことを記録する。
- テストを通すために `hve/prompt_execution.py` や `hve/__main__.py` を書き換えないこと。
- C1〜C4 は独立したプロセスまたは worktree なら並列実行してよい。request・保存設定・HEAD を変更する C5〜C7 と、成果物を生成する C8 は直列に実施する。各ケース完了後に敵対的レビューを行い、レビュー結果を反映してから次へ進むこと。
````
