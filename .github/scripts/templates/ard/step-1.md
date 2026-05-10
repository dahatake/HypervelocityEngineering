{root_ref}
## 目的
対象事業がまだ明確に定まっていない段階で、`{company_name}` の企業全体の As-Is / To-Be / Gap / Strategic Recommendations を作成し、戦略コンサルティングレポートとして `docs/company-business-requirement.md` を生成する。

## 入力
- 対象企業名: `{company_name}`（必須）
- 調査基準日: `{survey_base_date}`
- 調査期間年数: `{survey_period_years}` 年
- 対象地域: `{target_region}`
- 添付資料: `{attached_docs}`（任意。空の場合は「添付なし」として扱う）

## 出力
- `docs/company-business-requirement.md`

## Custom Agent
`Arch-ARD-BusinessAnalysis-Untargeted`

## 依存
- なし（ARD ワークフローのルートステップ）

## 完了条件
- `docs/company-business-requirement.md` が生成されている
- レポートに Executive Summary / Company Overview / As-Is Analysis / To-Be Vision / Gap Analysis / Strategic Recommendations / Appendix の章が含まれている
- KPI に「現状値・目標値・計測方法」が揃っている
- 不足データ・追加調査論点が Appendix に明記されている
{completion_instruction}{additional_section}
