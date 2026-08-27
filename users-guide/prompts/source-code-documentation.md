# ソースコードからのドキュメント生成の Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `adoc`

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## `adoc` がやること

既存のソースコードを読み、技術ドキュメントを `docs-generated/` に生成します。

主な成果物: `docs-generated/` 配下（アーキテクチャ / コンポーネント / ファイル / ガイド）

| パラメータ | 意味 | 値 |
|---|---|---|
| `target_dirs` | 読み取り対象ディレクトリ | `src/api` など。カンマ区切りで複数指定可 |
| `exclude_patterns` | 除外パターン | `**/node_modules/**` など |
| `doc_purpose` | ドキュメントの主目的 | `all` / `onboarding` / `refactoring` / `migration` |
| `max_file_lines` | 大規模ファイル分割閾値 | `300` / `500` / `1000` |

> **`target_dirs` を指定してください。** 未指定だとリポジトリ全体が対象になり得ます。
> 対象を絞ると読み取り範囲と実行時間を抑えられます。

---

## 新規参画者向けのオンボーディング資料を作る

```text
HVE の Prompt 版で作業してください。

- 目的: 新しく参加するメンバー向けに src/api の構造を説明する資料が欲しい
- Workflow: adoc
- パラメータ:
  - target_dirs=src/api
  - doc_purpose=onboarding
  - max_file_lines=500
- 制約: src/ 配下のコードは変更しないこと。読み取りと docs-generated/ への出力のみ
- 期待する成果物: docs-generated/ 配下のオンボーディング資料

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## リファクタリング前の現状把握

```text
HVE の Prompt 版で作業してください。

- 目的: リファクタリング対象を洗い出すために現状の構造と技術的負債を整理したい
- Workflow: adoc
- パラメータ:
  - target_dirs=src/api,src/web
  - exclude_patterns=**/node_modules/**,**/bin/**,**/obj/**
  - doc_purpose=refactoring
- 制約: ソースコードは変更しないこと
- 期待する成果物: docs-generated/ 配下のアーキテクチャ・コンポーネント資料

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
target_dirs の範囲が広すぎないか、承認前に私に確認させてください。
```

---

## 注意

- 出力先は `docs-generated/` です。`docs/`（設計成果物）とは別のディレクトリです。
- Step ID は表示グループ（`1`〜`6`）とその配下で構成されます。正本は `hve/workflow_registry.py` を参照してください。

---

## 関連

- 詳細ガイド: [sourcecode-documentation.md](../sourcecode-documentation.md)
