{root_ref}

{app_arch_scope_section}
## 目的
ドメイン分析結果とデータソース分析結果を根拠に、バッチデータモデル（入力/ステージング/中間/出力モデル・冪等性キー・パーティション戦略・ER図）を設計する。

## 入力
- `docs/batch/batch-domain-analytics.md`
- `docs/batch/batch-data-source-analysis.md`
- `docs/catalog/data-model.md`

## 出力
- `docs/batch/batch-data-model.md`

## Custom Agent
`Arch-Batch-DataModel` を使用

## 依存
- Step.1.1（バッチドメイン分析）が `abd:done` であること（AND依存）
- Step.1.2（データソース/デスティネーション分析）が `abd:done` であること（AND依存）

## 完了条件
- `docs/batch/batch-data-model.md` が作成されている
{completion_instruction}{additional_section}