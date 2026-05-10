---
name: harness-safety-guard
description: >
  破壊的操作を事前に検出・阻止する安全ガードの詳細パターンリストと判定フロー。 USE FOR: destructive operation detection, rm -rf detection, DROP TABLE detection. DO NOT USE FOR: error recovery after failure (use harness-error-recovery). WHEN: コマンドを実行する前の安全確認、破壊的操作の検出。
metadata:
  origin: user
  version: 2.0.0
---

# harness-safety-guard

## 目的

copilot-instructions.md §0（安全ガード）で定義した安全ガードの **具体的パターンと判定フロー** を提供する。
Agent が操作を実行する前に本 Skill を参照し、破壊的操作を事前に検出・阻止する。

---

## Non-goals

- **検出パターンの自動修正** — 危険パターンを検出した場合の修正は Agent が行う
- **権限付与の実行** — 権限不足（403/Access Denied）が判明した場合はユーザーへ報告し処理を停止
- **セキュリティ脆弱性の網羅的スキャン** — SAST/DAST 等の包括的スキャンは別途ツール・プロセスで実施

---

## 危険パターン概要

詳細な正規表現パターン一覧（CRITICAL/HIGH/MEDIUM）、Azure 固有の破壊的コマンド、ホワイトリスト、停止レベル別判定フロー図は `references/danger-patterns.md` を参照。

| レベル | 対応 |
|--------|------|
| **CRITICAL** | 絶対停止（確認なしに即時停止） |
| **HIGH** | 確認要求（実行前にユーザー確認を取る） |
| **MEDIUM** | 警告+理由記録（実行可能だが理由を記録する） |

---

## §5 安全ガード適用手順

1. 実行予定のコマンド/コードを `references/danger-patterns.md` §1 のパターンと照合する
2. 該当パターンがあれば `references/danger-patterns.md` §4 のフローに従い停止レベルを判定する
3. CRITICAL/HIGH 検出時はユーザーに通知し、操作を保留する
4. ホワイトリスト（`references/danger-patterns.md` §3）に該当する場合は除外して次の確認に進む
5. 最終結果を `{WORK}verification-report.md` の Security セクションに記録する

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/danger-patterns.md` | §1 危険パターン一覧（CRITICAL/HIGH/MEDIUM全テーブル）、§2 Azure固有コマンド、§3 ホワイトリスト、§4 停止レベル判定フロー図 |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `harness-verification-loop` | 利用元 | Phase 4（Security Scan）で本Skillのパターンを参照 |
| `harness-error-recovery` | 後続 | CRITICAL検出時の stop_condition 出力に使用 |
| `work-artifacts-layout` | 出力先 | verification-report.md の Security セクションに結果を記録 |
