# 08. E2E スモーク（自然言語 → request → plan → 承認 → run）

## 目的

- Prompt 版の **一気通貫** の流れを、実際の成果物生成まで含めて 1 回だけ通す。
- 「新しい実行エンジンを持たず、既存 `hve orchestrate` へ委譲している」ことを実行経路で確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-e2e/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- **Azure リソースの作成・変更は行わない。** デプロイ Step を含む Workflow / Step を選ばないこと。
- Copilot のトークンを消費するため、**実行前に対象 Workflow と Step 範囲を決めて記録**する。
- 作業ツリーの状態を `git status --porcelain` で保存しておく（差分の切り分けに使う）。

## 実施項目

### Step 1. 対象の決定

1. `python -c "from hve.workflow_registry import list_workflows; [print(w.id, w.name, [s.id for s in w.steps]) for w in list_workflows()]"` で候補を確認する。
2. 次の条件を満たす **設計系の 1 Workflow・少数 Step** を選ぶ。
   - Azure への書き込みを伴わない
   - 上流成果物が現リポジトリに揃っている（`hve prompt plan` が通っても実行時に不足する場合があるため、
     入力ファイルの実在を先に確認する）
3. 選んだ Workflow / Step と、その理由を記録する。

### Step 2. 自然言語からの request 生成

1. Copilot（GUI 内の Copilot CLI タブ / GitHub Copilot CLI / VS Code Copilot Chat）へ、
   Step 1 で決めた内容を **日本語の依頼文** として貼り付ける。
2. 依頼文には必ず次を含める。

```text
まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

3. 生成された request の内容を記録する。
4. **この間、利用者がコマンドやファイルパスを入力させられていない**ことを記録する（FR-PROMPT-10）。

### Step 3. 計画の確認

1. `python -m hve prompt plan --request <path>` の出力を記録する。
2. 次を目視で確認する。
   - 実行順が意図どおり
   - Step が Step 1 で決めた範囲だけ
   - argv に **デプロイ系のオプションが含まれていない**
   - `plan SHA-256` が表示されている
3. 実行前の `docs/` `src/` `knowledge/` `qa/` に差分が無いことを確認する。

### Step 4. 承認と実行

1. Step 3 の計画に問題がなければ、表示された SHA-256 を使って実行する。

```sh
python -m hve prompt run --request <path> --expected-sha256 <hash>
```

2. 実行中に **子プロセスとして `orchestrate` が起動している**ことを確認する
   （プロセス一覧、または出力に `Copilot SDK Orchestrator:` の見出しが現れること）。
3. 実行時間・終了コードを記録する。

### Step 5. 成果物の確認

1. `git status --porcelain` で生成・変更されたファイルを取得する。
2. 生成先が **canonical な出力パス**であることを確認する（別名で出力先が変わっていないこと）。
3. 成果物の内容が空でないこと、明らかな捏造（存在しない ID・URL・数値）が無いことを確認する。

### Step 6. 委譲であることの確認

1. `hve/prompt_execution.py` に `run_workflow` / `DAGExecutor` / `StepRunner` の再実装が
   無いことをコードで確認する。
2. 実行が `sys.executable -m hve orchestrate ...` の argv 配列かつ `shell=False` で
   起動されていることを確認する。

### Step 7. 後片付け

1. 生成された成果物を残すか戻すかを判断し、判断内容を記録する。
2. **`git checkout` / `git reset` / `git stash` は使わない**（他の作業の差分を巻き込むため）。
   戻す場合は生成されたファイルを個別に削除する。

## 記録すること

- 選んだ Workflow / Step と選定理由
- 依頼文・生成された request・`plan` の全出力・`run` の終了コード
- 生成された成果物の一覧と、canonical パスであることの確認
- 実行時間、および観測できた範囲での Token 消費量

## 重要

- **捏造は絶対に禁止**です。実行していない Step を「成功」と書いてはいけません。
- **Azure へは書き込まない。** デプロイ Step を含む計画が提示された場合は承認せず、Step を絞り直す。
- **承認前に `run` を実行しない。** Step 3 の確認を飛ばさないこと。
- 失敗した場合は、失敗箇所が **Prompt 版の境界**（request 検証 / 計画 / 承認 / 委譲）か、
  **既存 `orchestrate` 側**かを切り分けて記録する。切り分けできない場合は「切り分け不能」と書く。
- Step 1〜7 は直列実行です。並列化しないこと。各 Step 完了後に敵対的レビューを行い、
  レビュー結果を反映してから次の Step へ進むこと。
