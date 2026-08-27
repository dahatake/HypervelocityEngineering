# 04. 入力別名（canonical → actual）の安全契約（FR-PROMPT-08 / 09）

## 目的

- canonical な必須入力を、その run に限りリポジトリ内の実ファイルへ読み替える **入力別名** が、
  安全契約どおり fail-closed で動作するかを検証する。
- 別名が **Prompt 版の経路だけでなく `orchestrate --input-alias` を直接使う経路でも** 検証されることを確認する。
  （検証を省くと、リポジトリ外のパスが Step Prompt へ注入されて Agent に読み取りを指示してしまう）
- 別名が **単一の解決器** を通して 4 箇所へ同じ結果で適用されることを確認する。
- 結果を `work/run/{yyyyMMdd}T{HHmmss}-prompt-alias/Issue-prompt-version-integration-test/README.md` に保存する。

## 前提

- canonical は「選択した Step の `required_input_paths` に **リテラルで** 一致する値」だけが有効。
  実測は次で行う。**記憶や文書から書かないこと。**

```sh
python -c "from hve.workflow_registry import get_workflow; w=get_workflow('aad-web'); [print(s.id, list(s.required_input_paths or [])) for s in w.steps]"
```

- 別名の実ファイルはテスト用に用意する。リポジトリ内の既存ファイル（例 `README.md`）でもよい。

## 実施項目

### A. 正常系

1. `aad-web` の Step `1` と `2.1` を選び、両方が要求する canonical 入力を 1 つ選ぶ。
2. その canonical に対して、リポジトリ内に実在する通常ファイルを `actual` として指定する。
3. `hve prompt plan` の出力に次の行が現れることを確認する。

```text
- 入力別名: `<canonical>` → `<actual>`
```

4. 同じ別名を `orchestrate --input-alias <canonical> <actual>` で直接指定しても
   エラーにならないことを確認する。

### B. 異常系（**両方の経路で**拒否されること）

各ケースを次の 2 経路で実行し、**どちらでも実行前に拒否される**ことを確認する。

- 経路 1: `python -m hve prompt plan --request <request に input_aliases を書いたもの>`
- 経路 2: `python -m hve orchestrate --workflow <id> --input-alias <canonical> <actual> --dry-run`

| # | 入力 | 期待 |
|---|---|---|
| B1 | `actual` が `../../../etc/passwd`（`..` でリポジトリ外） | 拒否 |
| B2 | `actual` が絶対パス（`C:\...` / `/etc/...`） | 拒否 |
| B3 | `actual` が存在しないファイル | 拒否 |
| B4 | `actual` がディレクトリ | 拒否 |
| B5 | `actual` が symlink / junction | 拒否 |
| B6 | `canonical` が glob（`docs/catalog/*.md`） | 拒否。「v1 は glob に対応していない」と分かる文言 |
| B7 | `canonical` が placeholder を含む（`docs/catalog/screen-catalog-{key}.md`） | 拒否 |
| B8 | `canonical` がディレクトリ（末尾 `/`） | 拒否 |
| B9 | `canonical` が **選択した Step の入力ではない** | 拒否 |
| B10 | 同じ `canonical` に 2 つの別名 | 拒否 |
| B11 | `canonical` が **選択した Step が生成する成果物** | 拒否 |

> **B1 は最重要です。** 拒否されずに `plan` や Step Prompt に `../../../etc/passwd` が現れた場合、
> リポジトリ外ファイルの読み取り指示になるため **Critical** として報告してください。

### C. 表示グループ Step ID

CLI / GUI は表示グループ ID（`"1"`〜`"5"` 等）を渡すことがある。

1. グループ ID を持つ Workflow（`ard` / `asdw-web` / `adoc` 等）で `--steps <グループID>` を指定し、
   そのグループに展開される実 Step が要求する canonical を別名指定する。
2. **正しく受理される**ことを確認する（グループ ID が展開されずに全別名が誤って拒否されないこと）。

### D. 単一解決器による 4 箇所への適用

別名が次の 4 箇所すべてで同じ結果になることを確認する。

| 適用先 | 確認方法 |
|---|---|
| root Step の前提成果物判定 | canonical が無く actual が有る状態で、前提が満たされたと判定されること |
| meta 依存の artifact pattern 判定 | 同上 |
| Step Prompt | 関係する Step の prompt に `- \`<canonical>\` → \`<actual>\`` の addendum が入ること |
| Fleet task の必須入力表示 | 解決後の actual path が表示されること |

1. **別名に関係しない Step の prompt が変化していないこと** を確認する。
2. **ファイル本文が prompt に埋め込まれていないこと**（path だけであること）を確認する。
3. **canonical な出力パスが一切変わっていないこと**を確認する。

### E. 出力契約の不変

1. `.github/io-contracts/` と `StepDef.output_paths` が実行時に書き換えられていないことを確認する。
2. 別名を使った `plan` の argv に、出力先を変えるオプションが混入していないことを確認する。

## 記録すること

- A の前提で取得した **`required_input_paths` の実測値**
- 各異常系の実コマンド・終了コード・エラー本文（2 経路それぞれ）
- D の 4 箇所の確認方法と実出力

## 重要

- **捏造は絶対に禁止**です。「拒否された」は必ずエラー本文の引用とセットで書くこと。
- **B1 で `../../../etc/passwd` を実際に配置しないこと。** パス指定だけで拒否されることを確認する。
- テストを通すために `hve/input_aliases.py` の検証を緩めないこと。
- B1〜B11 は互いに独立なので並列実行してよい。各ケース完了後に敵対的レビューを行い、
  レビュー結果を反映してから次へ進むこと。
