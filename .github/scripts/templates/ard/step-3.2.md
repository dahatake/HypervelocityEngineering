{root_ref}
## 目的
Step 3.1 で抽出されたユースケース骨格 `{key}` について、詳細仕様を生成する。

> Sub-10 (ADR-0003): 本 step は ARD Step 3.1 の fan-out 子であり、1 ユースケース = 1 セッション。

## Custom Agent
`Arch-ARD-UseCaseCatalog`

## 入力
- `docs/catalog/use-case-skeleton.md`（Step 3.1 出力、`{key}` の行）
- `docs/business-requirement.md`（Step 2 出力。存在時優先）または `docs/company-business-requirement.md`（Step 1.2 出力。フォールバック）
- `original-docs/*`（任意）

## 出力
- `docs/use-cases/{key}-detail.md`

## 内容要件
- ユースケース `{key}` の以下を含むこと:
  1. ID / 名称 / 目的（価値）
  2. 主アクター
  3. 前提条件
  4. 基本フロー要約
  5. 主要例外
  6. 主要データ I/O
  7. KPI
  8. 優先度（P0/P1/P2）
- 不明・推論項目は `TBD` / `要確認` と明示

## 完了条件
- `docs/use-cases/{key}-detail.md` が作成されている
{completion_instruction}{additional_section}
