{root_ref}

{app_arch_scope_section}
## 目的
ユースケース文書を根拠に、データソース/デスティネーション分析（接続先・スキーマ概要・データ量見積・変換ルール・SLA/SLO）を行い、docs/batch/batch-data-source-analysis.md を作成する。

## 入力
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/data-model.md`（任意）

## 出力
- `docs/batch/batch-data-source-analysis.md`

## Custom Agent
`Arch-Batch-DataSourceAnalysis` を使用

## 完了条件
- `docs/batch/batch-data-source-analysis.md` が作成されている
{completion_instruction}{additional_section}