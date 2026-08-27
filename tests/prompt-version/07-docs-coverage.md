# 07. 全 Workflow の貼り付け用 Prompt が実際に計画できるか（FR-PROMPT-10）

## 目的

- [users-guide/prompts/](../../users-guide/prompts/README.md) に置いた **貼り付け用 Prompt 例** が、
  文書として存在するだけでなく **実際に `hve prompt plan` まで到達できる**ことを検証する。
- 例に書かれた Workflow ID / Step ID / パラメータ名が registry と一致していることを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-docs/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- 対象 Workflow の一覧は **registry を正本** とする。文書の件数記述を使わないこと。

```sh
python -c "from hve.workflow_registry import list_workflows; [print(w.id) for w in list_workflows()]"
```

## 実施項目

### A. Workflow の網羅

1. registry の全 Workflow ID を取得する。
2. `users-guide/prompts/` 配下のスニペットに、各 ID の貼り付け用 Prompt が
   **最低 1 件ずつ**あることを確認する。
3. 不足があれば、どの ID が欠けているかを列挙する。

### B. 例の記述が registry と一致するか

各スニペットに現れる値を registry と突き合わせる。

| 検査対象 | 突き合わせ先 |
|---|---|
| `Workflow: <id>` | `list_workflows()` の canonical ID |
| `Step: <ids>` | `get_workflow(<id>).steps` の実 Step ID |
| `パラメータ: <name>=<value>` | `get_workflow(<id>).params` の宣言名 |
| 期待する成果物のパス | 当該 Workflow の `output_paths`（`docs/` 等の実在確認は不要） |

**不一致を見つけた場合は、文書側の誤りか registry 側の変更かを判定して記録すること。**

### C. 実際に計画できるか

各スニペットの依頼文から request を作り、`hve prompt plan` が計画を提示できることを確認する。
`APP-NNN` / `<resource-group>` / `<UC-ID>` 等のプレースホルダは、実在する値または
テスト用の値へ置き換える。置き換えた値を記録すること。

| # | ファイル | 対象 |
|---|---|---|
| C1 | `requirements-architecture.md` | `ard` / `aas` / `ada` |
| C2 | `web-application.md` | `aad-web` / `asdw-web` |
| C3 | `dataflow.md` | `adfd` / `adfdv` |
| C4 | `ai-agent.md` | `aag` / `aagd` / `aar` |
| C5 | `knowledge-management.md` | `akm` |
| C6 | `design-doc-ingestion.md` | `adi` |
| C7 | `source-code-documentation.md` | `adoc` |
| C8 | `cross-workflow.md` | 複数 Workflow の組合せ |
| C9 | `custom-inputs.md` | 入力別名 |

> `plan` は成果物を生成しないため、**上流成果物が未整備でも計画自体は提示されます**。
> 「計画が提示できたこと」と「実際に実行できること」を混同せずに記録してください。

### D. 文書の整合性

1. 各スニペットに「plan を先に提示し、承認するまで run しない」旨の記載があることを確認する
   （Step を絞る差分だけを示す断片例は対象外）。
2. `users-guide/prompts/README.md` の索引から全ファイルへリンクが張られていることを確認する。
3. 相対リンクがすべて解決することを確認する。
4. Prompt 件数などの **変動値が固定記述されていない**ことを確認する。

### E. 静的契約テストとの二重チェック

1. 次を実行し、GREEN であることを確認する。

```sh
python -m pytest hve/tests/test_prompt_edition_docs_contract.py -q
```

2. **静的テストが GREEN でも C の実行で失敗する箇所**があれば、
   それは静的テストの検査不足である。どの検査が足りないかを記録する。

## 記録すること

- A の 1 で取得した **Workflow ID の実測一覧**
- B の突き合わせ結果（不一致があれば該当箇所と正しい値）
- C の各ケースで使ったプレースホルダ置換値と `plan` の実出力（実行順・Step・argv）
- E の 2 で見つかった検査不足

## 重要

- **捏造は絶対に禁止**です。「全 Workflow を確認した」は実測一覧とセットで書くこと。
- Workflow ID の総数を文書から引用しない。必ず `list_workflows()` の出力を使う。
- テストを通すために `users-guide/prompts/` の例を書き換えるのは、
  **registry との不一致を修正する場合のみ**。実行しやすくするための改変はしないこと。
- C1〜C9 は互いに独立なので並列実行してよい。各ケース完了後に敵対的レビューを行い、
  レビュー結果を反映してから次へ進むこと。
