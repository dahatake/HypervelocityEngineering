{root_ref}
## 目的
事業要件文書（`docs/business-requirement.md` または `docs/company-business-requirement.md`）を読み込み、後続の per-UC 詳細生成で fan-out する対象となる **ユースケース骨格** を `UC-*` ID 付きで列挙する。

> Sub-10 (ADR-0003): 本 step は ARD Step 3 fan-out の起点であり、UC 一覧を `UC-*` 形式で抽出する。

## Custom Agent
`Arch-ARD-UseCaseCatalog`

## 入力
- `docs/business-requirement.md`（Step 2 出力。存在時優先）または `docs/company-business-requirement.md`（Step 1.2 出力。フォールバック）
- `original-docs/*`（任意）

## 出力
- `docs/catalog/use-case-skeleton.md`（UC 骨格表 + `UC-*` ID）

## 出力フォーマット要件
- Markdown テーブル形式で `| UC-* | 名称 | 主アクター | 優先度 |` の列を含むこと
- `UC-*` の `*` は英数字・ハイフン・アンダースコアのみ（例: `UC-Signup`, `UC-01`, `UC-Member-Register`）
- UC 数は通常 10〜30 件、上限 50 件
- 詳細記述は Step 3.2 で行うため、本 step では骨格のみに留める

## 完了条件
- `docs/catalog/use-case-skeleton.md` が作成されている
- 各 UC に `UC-*` ID が割り振られている
{completion_instruction}{additional_section}
