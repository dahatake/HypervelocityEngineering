{root_ref}
## 目的
非機能要件の現状分析を実施する。

## 入力
- `docs-generated/component-index.md`
- `docs-generated/components/test-spec-summary.md`
- `docs-generated/components/tech-debt.md`

## 出力
- `docs-generated/architecture/nfr-analysis.md`

## Custom Agent
`Doc-NFRAnalysis`

## 依存
- Step.4 / Step.3.4 / Step.3.5 が `adoc:done`

## 完了条件
- `docs-generated/architecture/nfr-analysis.md` が作成されている
{completion_instruction}{additional_section}
