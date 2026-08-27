# 08. E2E スモーク（自然言語 → request → plan → 承認 → run）

## GitHub Copilot に貼り付ける Prompt

以下のコードブロック全体をコピーして貼り付けてください。

````markdown
このリポジトリで、HVE Prompt 版統合テスト「08. E2E スモーク（自然言語 → request → plan → 承認 → run）」を
実施してください。必要なコマンドとファイル操作はすべてあなたが実行し、利用者にコマンド、
request の保存先、plan SHA-256 の入力を求めないでください。実測していない結果を作らず、
以下の目的、前提、実施項目、記録すること、重要をすべて満たしてください。
Step 4 の実行は、あなたの判断ではなく利用者の明示承認を得てから行ってください。
開始前に `tests/prompt-version/README.md` の全 Prompt 共通の前提・禁止事項・既知の未修正事項を確認してください。

## 目的

- Prompt 版の **一気通貫** の流れを、実際の成果物生成まで含めて 1 回だけ通す。
- 「新しい実行エンジンを持たず、既存 `hve orchestrate` へ委譲している」ことを実行経路で確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-e2e/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- **Azure リソースの作成・変更は行わない。** デプロイ Step を含む Workflow / Step を選ばないこと。
- Copilot のトークンを消費するため、**実行前に対象 Workflow と Step 範囲を決めて記録**する。
- 対象 revision から作った **専用の隔離 worktree** で実施する。共有作業ツリーや未コミット差分のある checkout では実行しない。
- 結果レポートは隔離 worktree の外にある run-scoped パスへ保存し、cleanup 後も残るようにする。

## 実施項目

### Step 1. 対象の決定

1. 固定 fixture として **Workflow `ard` の Step `1`** を使い、`params.company_name=Prompt E2E Test` を指定する。別の Workflow / Step へ置き換えない。
2. `hve.workflow_registry.get_workflow("ard").get_step("1")` を使い、Custom Agent が `Arch-ARD-BusinessAnalysis-Untargeted`、canonical output が `docs/company-business-recommendation.md`、remote CI/CD と approval gate が無効であることを実行直前に確認する。argv だけを Azure 安全性の根拠にしない。
3. 隔離 worktree 内の `docs/company-business-recommendation.md` を削除し、この run が空でない成果物を新規生成したことを確認できる状態にする。共有作業ツリーの同名ファイルは変更しない。
4. 選んだ固定 fixture と、その検証結果を記録する。

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
   - 実行順が `ard` だけ
   - Step が `1` だけ
   - registry で確認した Custom Agent / output / gate が Step 1 の固定 fixture と一致する
   - `plan SHA-256` が表示されている
3. 実行前の `docs/` `src/` `knowledge/` `qa/` に差分が無いことを確認する。

### Step 4. 承認と実行

1. Step 3 の計画に問題がなく、利用者の**実行直前の明示承認**が得られたら、表示された SHA-256 を使って実行する。

```sh
python -m hve prompt run --request <path> --expected-sha256 <hash>
```

   - Copilot が利用者へ SHA-256 やコマンドの再入力を求めず、提示済み hash を転記していることを確認する。
   - controller が `docs/` `src/` `knowledge/` `qa/` を直接編集せず、まず `hve prompt run --request <path> --expected-sha256 <hash>` に委譲していることを確認する。

2. 実行中に **子プロセスとして `orchestrate` が起動している**ことを確認する
   （プロセス一覧、または出力に `Copilot SDK Orchestrator:` の見出しが現れること）。
3. 実行時間・終了コードを記録する。

### Step 5. 成果物の確認

1. 実行前後の `git status --porcelain` と `docs/company-business-recommendation.md` の実在・サイズ・SHA-256 を比較する。
2. 選択した非 Azure Step が `plan.md` / `subissues.md` だけで終了していないことを確認する。
3. 生成先が **canonical な出力パス**であることを確認する（別名で出力先が変わっていないこと）。
4. 成果物の内容が空でないこと、明らかな捏造（存在しない ID・URL・数値）が無いことを確認する。

### Step 6. 委譲であることの確認

1. `hve/prompt_execution.py` に `run_workflow` / `DAGExecutor` / `StepRunner` の再実装が
   無いことをコードで確認する。
2. 実行が `sys.executable -m hve orchestrate ...` の argv 配列かつ `shell=False` で
   起動されていることを確認する。

### Step 7. 後片付け

1. 結果レポートが隔離 worktree 外の run-scoped パスへ保存済みであることを確認する。
2. 隔離 worktree の外（元リポジトリ）へ移動し、`git -C <元リポジトリ> worktree remove --force <隔離パス>` で隔離 worktree を削除する。共有作業ツリーの生成物を個別削除したり、`git checkout` / `git reset` / `git stash` で戻したりしない。

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
````
