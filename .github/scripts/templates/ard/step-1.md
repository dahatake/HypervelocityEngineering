{root_ref}
## 目的
対象事業未定時の前段ステップとして、対象企業の事業ポートフォリオを俯瞰し、後続の per-business 詳細分析対象となる **事業分野候補リスト**（`BIZ-NN` ID 付き）を生成する。

> Sub-10 (ADR-0003): 本 step は ARD 全体の fan-out 起点であり、対象事業候補を `BIZ-NN` 形式で列挙する。
> `target_business` パラメータが指定されている場合は本 step はスキップされ、Step 2 が直接実行される。

## Custom Agent
`Arch-ARD-BusinessAnalysis-Untargeted`

## 入力
- 対象企業名: `{company_name}`（任意）
- 調査基準日: `{survey_base_date}`（任意）
- 調査期間: `{survey_period_years}` 年
- 対象地域: `{target_region}`
- 分析目的: `{analysis_purpose}`
- 添付資料: `{attached_docs}`
- `original-docs/*`（任意 / 読み取り専用）

## 出力
- `docs/company-business-recommendation.md`（事業候補表 + `BIZ-NN` 付き）

## 出力フォーマット要件
- Markdown テーブル形式で `| BIZ-NN | 名称 | 概要 | 想定規模 |` の列を含むこと
- `BIZ-NN` は 2 桁ゼロパディング（`BIZ-01`, `BIZ-02`, ...）
- 候補数は通常 5〜10 件、上限 10 件
- 不明・推論項目は `TBD` / `要確認` と明示

## 完了条件
- `docs/company-business-recommendation.md` が作成されている
- 各候補に `BIZ-NN` ID が割り振られている
{completion_instruction}{additional_section}
