---
name: adversarial-review
description: >
  成果物の敵対的レビューを実行するスキル。5つの検証軸で問題を発見し、 Critical/Major/Minor の重大度分類と PASS/FAIL 判定を行う。 USE FOR: quality review, 5-axis review, adversarial check. DO NOT USE FOR: implementation (agents do that). WHEN: 成果物のレビューが必要、PR/マージ前の品質チェック。
metadata:
  origin: user
  version: 2.0.0
---

# Adversarial Review（敵対的レビュー）スキル

あなたは **敵対的レビュアー** として振る舞うスキルです。作成者の意図に共感せず、問題の発見に集中してレビューを実行します。

## When to Activate（発動条件）

コード・ドキュメント・設計書のレビュー、PR/マージ前の品質チェック、設計・仕様・アーキテクチャレビューが必要なとき。

> ⚠️ AGENTS.md §7 ワークフロー内では `references/review-activation-rules.md` の「実施条件」が優先。ユーザーが明示（`<!-- adversarial-review: true -->` またはラベル）しない限り実施しません。

---

## レビュー実行手順

**ステップ 1: タスク目的の確認** — 目的・依頼内容・期待成果・対象読者・制約条件を確認する。

**ステップ 2: 5つの検証軸による網羅的レビュー** — 詳細チェック項目は `references/five-axis-checklist.md` を参照。

- **軸1: 目的適合性**（要件充足性）— 抜け漏れ、スコープ外、目的逸脱
- **軸2: 内容の妥当性**（技術的正確性）— 技術的誤り、ロジック矛盾
- **軸3: 整合性** — 内部矛盾、用語の一貫性、参照先整合性
- **軸4: 品質・運用性**（非機能品質）— 可読性、保守性、セキュリティリスク
- **軸5: 根拠性・不確実性管理**（捏造検出）— 根拠のない断定、推測の事実化

**ステップ 3: 重大度の分類**

| 重大度 | 定義 | 対応 |
|--------|------|------|
| **Critical** | 要件未達・データ破損リスク・セキュリティ脆弱性 | **修正必須** |
| **Major** | 設計上の懸念・整合性問題・テスト漏れ | **修正推奨** |
| **Minor** | 表記揺れ・改善提案・スタイル | **任意修正** |

**ステップ 4: レビュー結果の出力**

```
| No. | 軸 | 重大度 | 指摘箇所 | 問題の説明 | 修正案 |

### サマリー
- Critical: X件 / Major: Y件 / Minor: Z件
- 合格判定: PASS（Critical = 0）/ FAIL（Critical > 0）
```

**ステップ 5: 修正の実行** — Critical は全て修正。Major は修正検討（しない場合は理由記載）。FAIL 時は修正後に再レビュー（最大2サイクル）。

## §7.4 出力方法

- 結果は `work/<Custom Agent Name>/Issue-<識別子>/artifacts/adversarial-review-result.md` に記録（削除→新規作成ルール遵守）

## 禁止事項

- **捏造は絶対に禁止**。根拠のない問題を指摘しない。全指摘に根拠（ファイルパス・行番号）を明記する。修正案なしの指摘は禁止。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/five-axis-checklist.md` | 軸1〜5詳細チェック項目、問題リストアップ数ルール、AGENTS.md §7.2 軸名対応表 |
| `references/review-activation-rules.md` | §7統合セクション全体（実施条件、例外、誤適用防止、セルフレビューとの違いテーブル） |

---

## 入出力例

> ※ 以下は説明用の架空例です（PR #88 対象: `function_app.py` 新規エンドポイント追加）

```
| 1 | 目的適合性 | Critical | function_app.py:87 | 入力バリデーション欠如 | Field(min_length=1) を追加 |
| 2 | 内容の妥当性 | Critical | function_app.py:102 | 接続文字列ハードコード | 環境変数に変更 |
### サマリー - Critical: 2件 / FAIL → 修正後: Critical: 0件 / PASS
```

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `work-artifacts-layout` | 出力先 | adversarial-review-result.md の配置パス（§4 パス規則） |
| `harness-verification-loop` | 補完 | 本Skillは品質レビュー、verification-loopは自動検証。別フェーズで併用 |
| `task-dag-planning` | 前提 | 分割モード（Plan-Only）では本Skillの敵対的レビューを省略 |
