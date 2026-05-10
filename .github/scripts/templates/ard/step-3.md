{root_ref}
## 目的
Step 2 で生成された `docs/business-requirement.md`（優先）または Step 1 で生成された `docs/company-business-requirement.md`、および `docs/` 配下の関連文書を入力として、ユースケースカタログ `docs/catalog/use-case-catalog.md` を作成する。

## 入力
- 以下のいずれか／両方（必須。両方存在時は `docs/business-requirement.md` を優先採用）
  - `docs/business-requirement.md`（Step 2 出力。優先）
  - `docs/company-business-requirement.md`（Step 1 出力。後方互換／Step 2 未実行時のフォールバック）
- `docs/D01-*.md` 〜 `docs/D21-*.md`（任意・存在する場合のみ）
- 対象企業名: `{company_name}`（任意）

## 出力
- `docs/catalog/use-case-catalog.md`

## Custom Agent
`Arch-ARD-UseCaseCatalog`

## 依存
- Step 2（推奨）または Step 1（後方互換: Step 2 がスキップされた場合）。どちらか一方が完了していれば本ステップは起動可能。

## 完了条件
- `docs/catalog/use-case-catalog.md` が生成されている
- 各ユースケースに ID / 名称 / 目的（価値）/ 一次アクター / 前提条件 / 基本フロー要約 / 主要例外 / 主要データ I/O / KPI / 優先度（P0/P1/P2）が記載されている
- 不確定事項は TBD として明示されている

## 補足: Work IQ 連携
本ステップは Work IQ が利用可能な環境（`is_workiq_available()` が True かつ Work IQ QA が有効）では Work IQ MCP 経由で実行され、それ以外の場合は GitHub Copilot CLI 経由で実行されます。
{completion_instruction}{additional_section}
