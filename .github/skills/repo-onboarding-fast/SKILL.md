---
name: repo-onboarding-fast
description: "初見/入口不明のときに、最小読解で入口・境界・標準コマンドを確定し onboarding.md に固定する。"
---

# repo-onboarding-fast

## 目的
- “全部読む” を避け、作業に必要な最小限（入口/境界/標準コマンド）だけ確定する。

## 手順（読む順）
1) 入口：README / docs / CI（.github/workflows）から標準コマンドを拾う
2) 境界：公開I/F（API/スキーマ/型）とデータ境界（DB/移行）を特定
3) 既存の類似実装を1つ見つけて踏襲点（命名/例外/ログ/テスト）を抽出
4) `work/<task>/onboarding.md` に固定（後続Subが再利用できる形）

## onboarding.md 最小フォーマット
- 入口（主要パス）
- 境界（API/データ/責務）
- 踏襲元（類似実装パス）
- 標準コマンド（build/test/lint）
- 不明点とSpike案（あれば）
