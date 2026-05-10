{root_ref}
## 目的
対象事業 `{target_business}`（企業: `{company_name}`）について、添付資料を一次情報として As-Is / To-Be / Gap / Strategic Recommendations の事業・業務分析レポートを作成し、`docs/business-requirement.md` を生成する。

## 入力
- 対象企業名: `{company_name}`（任意。Step 1 を同時実行しない場合は未指定可）
- 分析対象事業・業務名: `{target_business}`（必須）
  - 文章での説明、または対象資料が格納されているフォルダパス／複数ファイルのパスを指定可能（パス指定対応は後続 PR で実装）
- 調査期間年数: `{survey_period_years}` 年
- 対象地域: `{target_region}`
- 分析目的: `{analysis_purpose}`
- 使用するファイル・資料: `{attached_docs}`（任意。空の場合は「添付なし」として扱う）
- `docs/company-business-requirement.md`（任意・参考。Step 1 が先行実行されている場合は補助コンテキストとして参照する。既存の入力（添付資料・指定資料）を一次情報として優先する）

## 出力
- `docs/business-requirement.md`（対象業務指定済みの事業分析レポート。Step 1 出力 `docs/company-business-requirement.md` とは別ファイル）

## Custom Agent
`Arch-ARD-BusinessAnalysis-Targeted`

## 依存
- なし（ARD ワークフローのルートステップとしても起動可能。Step 1 完了後の継続実行にも対応）

## 完了条件
- `docs/business-requirement.md` が生成されている
- 添付資料を一次情報として優先的に参照した形跡がある（資料に記載のない情報は「外部情報に基づく補足」「合理的な仮説」「追加確認が必要な論点」のいずれかに分類されている）
- レポートに Executive Summary / Analysis Scope and Methodology / Business / Operation Overview / As-Is Analysis / Key Issues / To-Be Vision / Gap Analysis / Strategic Options / Strategic Recommendations / Appendix の章が含まれている
- 推奨戦略に短期・中期・長期の実行ロードマップと KPI が含まれている
{completion_instruction}{additional_section}
