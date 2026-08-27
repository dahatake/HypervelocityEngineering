{root_ref}
## 目的
Step 1.1（事業分野別深掘り分析）の全 fan-out 子の出力を統合し、対象企業全体の事業要件文書を生成する。

> Sub-10 (ADR-0003): 本 step は Step 1.1 fan-out の join。

## Custom Agent
`Arch-ARD-BusinessAnalysis-Untargeted`

## 入力
- `docs/business/*-analysis.md`（Step 1.1 の全 fan-out 子出力）
- `docs/company-business-recommendation.md`（Step 1 出力）

## 出力
- `docs/company-business-requirement.md`

## 内容要件
- 各事業 (`BIZ-NN`) のサマリーを含む統合レポート
- 事業横断のシナジー・コンフリクト分析
- 不明・推論項目は `TBD` / `要確認` と明示

## 完了条件
- `docs/company-business-requirement.md` が作成されている
- 全 `BIZ-NN` のサマリーが網羅されている
{completion_instruction}{additional_section}
