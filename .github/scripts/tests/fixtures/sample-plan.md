<!-- task_scope: single -->
<!-- context_size: medium -->
<!-- split_decision: PROCEED -->
<!-- subissues_count: 0 -->
<!-- implementation_files: false -->

# Sample Plan

## 概要

テスト用サンプル plan.md。validate-plan の dry-run テストに使用。

## DAG

```
S1(調査:2min) → S2(実装:3min) → S3(検証:1min)
```

## 分割判定

- task_scope: single
- context_size: medium（参照ファイル: 5件）
- 判定結果: PROCEED
- 判定根拠: task_scope=single かつ context_size=medium → PROCEED（上記いずれも非該当）
- 実装に進む理由: task_scope=single、context_size=medium
