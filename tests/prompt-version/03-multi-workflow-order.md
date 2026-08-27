# 03. 複数 Workflow の依存順と暗黙追加の禁止（FR-PROMPT-06）

## GitHub Copilot に貼り付ける Prompt

以下のコードブロック全体をコピーして貼り付けてください。

````markdown
このリポジトリで、HVE Prompt 版統合テスト「03. 複数 Workflow の依存順と暗黙追加の禁止
（FR-PROMPT-06）」を実施してください。必要なコマンドとファイル操作はすべてあなたが実行し、
利用者にコマンド、request の保存先、plan SHA-256 の入力を求めないでください。実測していない結果を
作らず、以下の目的、前提、実施項目、記録すること、重要をすべて満たしてください。
開始前に `tests/prompt-version/README.md` の全 Prompt 共通の前提・禁止事項・既知の未修正事項を確認してください。

## 目的

- 複数 Workflow を 1 つの request に書いたときの **実行順** が
  `hve/workflow_registry.py` の `get_meta_dependencies()` に基づく安定ソートになっているかを検証する。
- 「選択されていない依存 Workflow を暗黙に追加しない」「任意 DAG を受理しない」契約を確認する。
- GUI の順序決定と **同一実装を共有している**（drift が無い）ことを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-order/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- 依存関係の正本は次で取得する。**図や文書の記載を鵜呑みにしないこと。**

```sh
python -c "from hve.workflow_registry import get_meta_dependencies, list_workflows; [print(w.id, '<-', [(d.workflow_id, d.soft) for d in get_meta_dependencies(w.id)]) for w in list_workflows()]"
```

## 実施項目

### A. 依存順の実測

1. 上記コマンドで全 Workflow の meta 依存を取得し、**実測値の表** を作る。
2. 次の組合せを request に書き、`hve prompt plan` の `実行順:` 行を確認する。
   request での **記述順は依存順と逆** にして、並べ替えが実際に効くことを確かめる。

| # | request の記述順 | 期待する実行順の根拠 |
|---|---|---|
| A1 | `aad-web`, `aas` | `aad-web` は `aas` に hard 依存 |
| A2 | `asdw-web`, `aad-web`, `aas` | 連鎖依存 |
| A3 | `adfdv`, `adfd` | `adfdv` は `adfd` に hard 依存 |
| A4 | `aagd`, `aag` | `aagd` は `aag` に hard 依存 |
| A5 | `adfd`, `aas` | soft 依存でも順序に反映されるかを実測 |

**期待順は A の 1 で取得した実測表から導くこと。上表の「根拠」列を鵜呑みにしない。**

### B. 暗黙追加の禁止

1. `aad-web` **だけ**を request に書いて `plan` する。
2. 実行順に `aas` や `ard` が **追加されていないこと** を確認する。
3. 同様に `asdw-web` 単独で `aad-web` が追加されないことを確認する。

### C. 依存を持たない Workflow

1. `akm` / `adi` / `adoc` は meta 依存を持たない。
   これらを他 Workflow と混ぜたとき、**request の記述順が保たれる**（安定ソート）ことを確認する。
2. 例: `adoc`, `aas`, `akm` の順で書いたときの実行順を実測して記録する。

### D. GUI との同値性

1. `hve/gui/main_window.py` の `_sort_workflows_by_dependencies` が
   `hve/workflow_order.py` の `sort_workflows_by_dependencies` へ委譲していることをコードで確認する。
2. 同じ入力列に対して両者が同じ結果を返すことを Python から直接呼び出して確認する。

```sh
python -c "from hve.workflow_order import sort_workflows_by_dependencies as a; from hve.gui.main_window import _sort_workflows_by_dependencies as b; xs=['aad-web','aas','asdw-web']; print(a(xs), b(xs), a(xs)==b(xs))"
```

### E. 異常系

| # | 入力 | 期待 |
|---|---|---|
| E1 | 同じ Workflow を 2 回書く | request 段階で拒否（01 の B4 と同じ） |
| E2 | `sort_workflows_by_dependencies` へ重複を直接渡す | 「重複」と分かるエラー（「循環依存」と誤報しないこと） |
| E3 | 任意の依存関係を request で指定しようとする | そのようなフィールドは存在せず、未知フィールドとして拒否される |

## 記録すること

- A の 1 で取得した **依存関係の実測表**（これが以降の期待値の根拠になる）
- 各ケースの request 記述順・実測された実行順・一致 / 不一致
- GUI と core の同値性チェックの実出力

## 重要

- **捏造は絶対に禁止**です。依存関係を記憶や図から書かず、必ず `get_meta_dependencies()` の出力を使う。
- 期待順と実測順が食い違った場合、まず **期待順の導出が正しいか** を疑う。
  そのうえで実装が誤っていると判断した場合のみ、`hve-dev/requirement-definition.md` FR-PROMPT-06 を根拠に報告する。
- テストを通すために `hve/workflow_registry.py` の依存宣言を書き換えないこと。
- A / B / C は互いに独立なので並列実行してよい。各ケース完了後に敵対的レビューを行い、
  レビュー結果を反映してから次へ進むこと。
````
