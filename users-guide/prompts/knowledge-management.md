# Knowledge Management の Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `akm`

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## `akm` がやること

`qa/` / `docs-original/` などのソースから、確定済みドキュメント
`knowledge/D01〜D21-*.md` を生成・更新します。

Step ID: `1`, `2`

| パラメータ | 意味 | 値の例 |
|---|---|---|
| `sources` | 取り込みソース | `qa` / `original-docs` / `workiq`（カンマ区切りで複数指定可） |
| `target_files` | 更新対象 | 既定は `sources` に応じて決まる |
| `force_refresh` | 既存内容を無視して作り直すか | `true` / `false` |
| `custom_source_dir` | 追加ソースディレクトリ | `docs/specs` など |

---

## `qa/` の回答から knowledge を更新する

```text
HVE の Prompt 版で作業してください。

- 目的: qa/ の回答内容を knowledge/ に反映したい
- Workflow: akm
- パラメータ: sources=qa
- 制約: docs-original/ は読み取り専用。変更・削除・追記をしないこと
- 期待する成果物: knowledge/D01〜D21-*.md の更新

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## 原本ドキュメントからまとめて再構成する

```text
HVE の Prompt 版で作業してください。

- 目的: docs-original/ の内容も含めて knowledge/ を作り直したい
- Workflow: akm
- パラメータ:
  - sources=qa,original-docs
  - force_refresh=true
- 制約:
  - docs-original/ は読み取り専用として扱うこと
  - 他の作業が同じ knowledge/ ファイルを更新中でないことを先に確認すること
- 期待する成果物: knowledge/D01〜D21-*.md

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
force_refresh=true は既存の記述を作り直すため、承認前に対象範囲を私に確認させてください。
```

---

## 注意

- `knowledge/` は **複数のワークフローが共有する書き込み先** です。
  並行して別の作業が走っている場合、同じファイルを同時に更新しないでください。
- `docs-original/` は全 Workflow から **読み取り専用** です。
- `force_refresh=true` は既存の確定内容を上書きします。承認前に対象ファイルを確認してください。

---

## 関連

- 詳細ガイド: [km-guide.md](../km-guide.md)
- 原本の取り込み（前段）: [design-doc-ingestion.md](design-doc-ingestion.md)
