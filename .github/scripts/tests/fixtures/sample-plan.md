<!-- estimate_total: 10 -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Sample Plan

## 概要

テスト用サンプル plan.md。validate-plan の dry-run テストに使用。

## DAG

```
R(調査:2min) → P(計画:3min) → I(実装:3min) → V(検証:1min) → F(仕上げ:1min)
```

## 分割判定

- 見積合計: 10 分
- 15分以下か: YES
- 不確実性: 低
- 判定結果: PROCEED
- 判定根拠: AGENTS.md §2.2 の条件「見積合計 > 15分」に非該当
- 実装に進む理由: 見積 10分 ≤ 15分、不確実性: 低
