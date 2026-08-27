# 既存設計書の取り込み（ADI）の Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `adi`

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## `adi` がやること

`docs-original/` に置いた原本（PDF / Office / Markdown 等）を目録化・正規化し、
D01〜D21 の質問票を生成して、目的に沿って選別した候補を下流成果物へ反映します。

Step ID: `1`, `1.1`, `1.2`, `2`, `3`, `4`, `5.1`, `5.2`, `5.3`

主な成果物: `docs/original-design-doc-ingest/index.json` /
`docs/catalog/design-doc-inventory.md` / `qa/D01〜D21-docs-original-questionnaire.md` /
`qa/docs-original-cross-questionnaire.md` / `docs/catalog/design-doc-catalog.md` /
`docs/catalog/design-doc-routing.md`

| パラメータ | 意味 | 値 |
|---|---|---|
| `purpose` | 取り込みの目的（任意） | 自由記述。省略すると目的非依存モードになり `must` は付与されない |
| `target_scope` | 対象範囲 | 既定 `docs-original/` |
| `depth` | 分析の深さ | `standard` / `lightweight` |
| `focus_areas` | 重点領域（任意） | 自由記述 |

> `adi` は **CLI / GUI 専用** の Workflow です（Cloud の Issue Template 経路は未対応）。
> Prompt 版もローカル実行のみで、この点は変わりません。

---

## 目的を指定して取り込む

```text
HVE の Prompt 版で作業してください。

- 目的: docs-original/ にある既存設計書を取り込み、再構築に必要な情報を選別したい
- Workflow: adi
- パラメータ:
  - purpose=<この取り込みで達成したいこと>
  - depth=standard
- 制約: docs-original/ は読み取り専用。原本の変更・削除・追記を一切しないこと
- 期待する成果物:
  - docs/original-design-doc-ingest/index.json
  - docs/catalog/design-doc-inventory.md
  - qa/ 配下の質問票

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## 軽量モードで目録だけ先に作る

```text
HVE の Prompt 版で作業してください。

- 目的: docs-original/ に何があるかをまず一覧化したい
- Workflow: adi
- Step: 1, 1.1
- パラメータ: depth=lightweight
- 制約: docs-original/ は読み取り専用。質問票の生成まで進めないこと
- 期待する成果物: docs/catalog/design-doc-inventory.md

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## 注意

- **`docs-original/` は読み取り専用です。** 原本を書き換える依頼はしないでください。
- `purpose` を省略すると `must` 判定が付かず、選別が緩くなります。
- 取り込み後に `knowledge/` を更新したい場合は [knowledge-management.md](knowledge-management.md) を参照してください。

---

## 関連

- 詳細ガイド: [00-design-doc-ingestion.md](../00-design-doc-ingestion.md)
