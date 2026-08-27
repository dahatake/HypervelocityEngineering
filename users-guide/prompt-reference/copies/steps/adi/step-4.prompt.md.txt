{root_ref}
## 目的
トリアージ結果を下流ワークフロー（AKM / ARD / AAS / ADFD）の入力へ対応づけるルーティング表と、設計書間の依存図を生成する。

## Custom Agent
`Doc-OriginalRouting`

## 実行パラメータ

| パラメータ | 値 |
|-----------|---|
| purpose | `{adi_purpose}` |

## 入力
- `docs/catalog/design-doc-catalog.md`（Step 3 の判定結果）
- `docs/original-design-doc-ingest/*/card.md`（`d_classes` / `job_ids` / `depends_on` / `depended_by`）

## 出力
- `docs/catalog/design-doc-routing.md`

{existing_artifact_policy}

## 完了条件
- `must` / `should` の全文書がルーティング表に掲載されている
- 「D 分類別の担当文書」に D01〜D21 の全行がある（該当なしは `—`）
- 各行に `→ 反映先成果物` が埋まっている（Step 5.x が参照する）
- 依存図のエッジが Doc Card の記載に基づいている（推測エッジが無い）
- Step 3 の採否判定を変更していない{additional_section}
