{root_ref}
## 目的
Step 3.2（ユースケース詳細生成）の全 fan-out 子の出力を統合し、最終成果物 `docs/catalog/use-case-catalog.md` を生成する。

> Sub-10 (ADR-0003): 本 step は Step 3.2 fan-out の join。

## Custom Agent
`Arch-ARD-UseCaseCatalog`

## 入力
- `docs/use-cases/*-detail.md`（Step 3.2 の全 fan-out 子出力）
- `docs/catalog/use-case-skeleton.md`（Step 3.1 出力、ID 順序の根拠）

## 出力
- `docs/catalog/use-case-catalog.md`

## 内容要件
- 全 UC を ID 順に統合したカタログ
- 優先度別の集計（P0/P1/P2 件数）
- 不明・推論項目は `TBD` / `要確認` と明示

## 完了条件
- `docs/catalog/use-case-catalog.md` が作成されている
- 全 `UC-*` のエントリが網羅されている
{completion_instruction}{additional_section}
