---
name: repo-onboarding-fast
description: >
  初見のリポジトリで最小限の読解により入口・境界・標準コマンドを確定し、 onboarding.md に固定するスキル。"全部読む"を避け、作業に必要な最小限だけ確定する。 USE FOR: repository onboarding, first assignment, entry point discovery. DO NOT USE FOR: full code analysis. WHEN: リポジトリに初めてアサインされた、入口が不明。
metadata:
  origin: user
  version: 2.0.0
---

# repo-onboarding-fast

## 目的
- "全部読む" を避け、作業に必要な最小限（入口/境界/標準コマンド）だけ確定する。

## Non-goals

- **全ファイルの詳細読解** — 最小限の読解（入口/境界/標準コマンド）で作業開始に必要な情報を確定する
- **アーキテクチャ設計・分析** — Arch-* 系 Agent が担当する
- **onboarding.md 以外の成果物作成** — plan.md / subissues.md は Skill `task-dag-planning`、`work/<task>/README.md` は Skill `work-artifacts-layout` が担当する

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

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/onboarding-examples.md` | 入出力例セクション全体（例1: 本リポジトリを対象とした onboarding.md、例2: 既存 onboarding.md がある場合の更新） |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `work-artifacts-layout` | 出力先 | onboarding.md の配置パスと削除→新規作成ルール |
| `task-dag-planning` | 後続 | オンボーディング完了後に plan.md 作成へ遷移 |
| `task-questionnaire` | 後続 | 不明点がある場合のコンテキスト収集 |
