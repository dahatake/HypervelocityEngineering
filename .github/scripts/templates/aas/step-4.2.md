{root_ref}
## 目的
Step 4.1 で設計済みのデータモデルから、検証用のサンプルデータ（最小セット）を JSON 形式で生成する。

## 入力
- `docs/catalog/data-model.md`（Step 4.1 の出力）
- `docs/catalog/domain-analytics.md`
- `docs/catalog/service-catalog.md`
- `docs/catalog/app-catalog.md`

## 出力
- `src/data/sample-data.json`

## Custom Agent
`Arch-DataModeling` を使用（実装は最小サンプル JSON のみ）

## 依存
- Step.4.1（データモデル）が完了していること（`docs/catalog/data-model.md` が存在）

## アプリケーション粒度
📋 `docs/catalog/app-catalog.md` の各 APP-ID で参照されるエンティティを最小 1 レコードずつカバーすること。
PII・実データを含めない（架空のサンプルのみ）。

## 完了条件
- `src/data/sample-data.json` が作成されている
- データモデルの主要エンティティが網羅されている
- 機微情報・実データを含まない
{completion_instruction}{additional_section}
