# 02. plan の提示内容と run の承認ゲート（FR-PROMPT-03 / 04 / 05）

## 目的

- `hve prompt plan` が提示する内容と、`hve prompt run` の **plan SHA-256 一致ゲート** を実測で検証する。
- 「自然言語上の『承認』だけで書き込みを開始しない」という Prompt 版の中核契約が守られているかを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-gate/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- リポジトリ直下で作業する。
- 作業ツリーの `git rev-parse HEAD` を記録しておく（plan hash に HEAD が含まれるため）。

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

各ケースで **子プロセスが 1 つも起動しないこと** を確認する。
確認方法は「`docs/` 等の成果物に差分が出ない」ことに加え、`work/run/` の新規ディレクトリが
増えないことでも代用できる。実測した確認手段を記録すること。

| # | 入力 | 期待 |
|---|---|---|
| C1 | `--expected-sha256` を省略 | argparse がエラー終了（必須引数） |
| C2 | `--expected-sha256 abc`（64 桁未満） | 拒否。子プロセス 0 件 |
| C3 | 64 桁だが hex でない文字を含む | 拒否。子プロセス 0 件 |
| C4 | 正しい形式だが plan と不一致 | `stale` として拒否。期待値と実際値の両方が表示される |
| C5 | `plan` 提示後に request を書き換えてから同じ hash で `run` | 拒否 |
| C6 | `plan` 提示後に GUI 設定（`hve/.settings.txt`）のモデルを変えてから同じ hash で `run` | 拒否 |
| C7 | `plan` 提示後に新しい commit を作ってから同じ hash で `run` | 拒否（HEAD が hash に含まれるため） |
| C8 | `plan` が提示した hash をそのまま指定 | 実行される |

C2 / C3 の拒否メッセージに、hex の転記は Agent の責務である旨が含まれることも確認する。

### D. hash の決定性

1. 同じ request・同じ設定・同じ HEAD で `plan` を 2 回実行し、**同じ SHA-256** になることを確認する。
2. `settings_overrides.model` だけを変えた request で hash が変わることを確認する。
3. `steps` の指定順だけを変えた request で hash がどうなるかを実測し、結果を記録する
   （期待値を先に決めつけず、実測結果を `hve/prompt_execution.py` の `canonical_plan_json` と突き合わせる）。

### E. 複数 Workflow の fail-fast

1. 2 つの Workflow を含む request で、1 つ目が失敗するように仕向ける
   （例: 存在しないリソースを要求する等、Azure を使わない範囲で）。
2. **2 つ目の Workflow が起動しないこと**を確認する。
3. 「成功済み Workflow を取り消した」と報告しないこと（rollback は実装されていない）。

## 記録すること

- 各ケースの実コマンド・終了コード・stdout / stderr の該当行
- `plan` 前後のファイル差分（成果物ディレクトリ / `work/run/` / 索引）
- hash が変わった / 変わらなかった条件の一覧

## 重要

- **捏造は絶対に禁止**です。「子プロセスが起動しなかった」は必ず実測根拠とセットで書くこと。
- **C8 以外で `run` が実行されてしまった場合は Critical** として報告する。
- テストを通すために `hve/prompt_execution.py` や `hve/__main__.py` を書き換えないこと。
- C1〜C7 は互いに独立なので並列実行してよい。各ケース完了後に敵対的レビューを行い、
  レビュー結果を反映してから次へ進むこと。
