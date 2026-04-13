---
name: harness-verification-loop
description: >
  コード変更後の5段階検証パイプライン（Build/Lint/Test/Security/Diff）の詳細手順。
  各言語（C#/Python/Shell）の具体的コマンドライン、Phase 失敗時の対処法、
  verification-report.md テンプレートを提供する。
  USE FOR: build check, lint, test execution, security scan,
  diff review, verification-report, PR submission quality check,
  5-phase verification pipeline.
  DO NOT USE FOR: error recovery (use harness-error-recovery),
  safety guard (use harness-safety-guard),
  test code creation or modification.
  WHEN: コードを変更した後の検証、ビルド確認、lint チェック、
  テスト実行、セキュリティスキャン、diff レビュー、
  verification-report.md を作成したい、PR 提出前の品質確認。
metadata:
  origin: user
  version: "2.0.0"
---

# harness-verification-loop

## 目的

copilot-instructions.md §0（検証ループ）で定義した5段階検証パイプラインの **実行手順と具体的コマンド** を提供する。

---

## Non-goals

- **エラー発生時のリカバリ手順** — Skill `harness-error-recovery` が担当
- **破壊的操作の検出・阻止** — Skill `harness-safety-guard` が担当
- **テストコードの作成・修正** — 実装コードの修正は Agent が行う（テストは正解定義）

---

## 5段階検証パイプライン概要

| Phase | 内容 | 詳細コマンド |
|---|---|---|
| **Phase 1: Build** | 構文・コンパイルチェック | `references/verification-commands.md` §1 |
| **Phase 2: Lint** | 静的解析 | `references/verification-commands.md` §1 |
| **Phase 3: Test** | テスト実行 | `references/verification-commands.md` §1 |
| **Phase 4: Security Scan** | 秘密情報検出 | `references/verification-commands.md` §1 |
| **Phase 5: Diff Review** | 変更差分確認 | `references/verification-commands.md` §1 |

各 Phase の結果を `{WORK}verification-report.md` に記録する（テンプレート: `references/verification-commands.md` §2）。

Phase 失敗時のエスカレーション: `references/verification-commands.md` §3 を参照。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/verification-commands.md` | §1 Phase別コマンドリファレンス（Phase 1〜5）、§2 検証レポートテンプレート、§3 エスカレーション手順 |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `harness-error-recovery` | 後続 | Phase失敗時のエスカレーション先（3要素出力） |
| `harness-safety-guard` | 前提 | コマンド実行前の安全チェック |
| `work-artifacts-layout` | 出力先 | `verification-report.md` の配置先と `{WORK}` 構造の参照先 |
| `adversarial-review` | 補完 | 本Skillは自動検証、adversarial-reviewは人的レビュー |
