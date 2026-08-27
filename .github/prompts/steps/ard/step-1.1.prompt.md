{root_ref}
## 目的
Step 1 で列挙した事業候補 `{key}` について、深掘り分析を実施し、`docs/business/{key}-analysis.md` を生成する。

> Sub-10 (ADR-0003): 本 step は ARD Step 1 の fan-out 子であり、1 事業候補 = 1 セッション。

## Custom Agent
`Arch-ARD-BusinessAnalysis-Untargeted`

## 入力
- `docs/company-business-recommendation.md`（Step 1 出力、`{key}` の行）
- 対象企業名: `{company_name}`
- 調査基準日: `{survey_base_date}`、調査期間: `{survey_period_years}` 年
- 対象地域: `{target_region}`

## 出力
- `docs/business/{key}-analysis.md`

## 内容要件
- 事業候補 `{key}` の以下を含むこと:
  1. 事業概要・規模・成長性
  2. 主要顧客セグメント
  3. 競合構造
  4. 規制・法令上の制約
  5. デジタル化機会（候補）
- 不明・推論項目は `TBD` / `要確認` と明示
- 他事業（他の `BIZ-NN`）への言及は最小限に抑える

## 完了条件
- `docs/business/{key}-analysis.md` が作成されている
{completion_instruction}{additional_section}
