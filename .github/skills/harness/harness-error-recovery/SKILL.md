---
name: harness-error-recovery
description: >
  エラー発生時の統一リカバリ契約。エラー分類（Build失敗・Test失敗・書き込み失敗・ API制限・権限不足）ごとのリカバリフロー、3要素出力（root_cause_hint / safe_retry_instruction / stop_condition）テンプレートを提供する。 USE FOR: error recovery, build failure recovery, test failure recovery. DO NOT USE FOR: verification pipeline execution (use harness-verification-loop). WHEN: エラーが発生した、ビルドが失敗した。
metadata:
  origin: user
  version: 2.0.0
---

# harness-error-recovery

## 目的

copilot-instructions.md §0（エラーリカバリ）で定義したエラーリカバリ契約の **エラー分類と対処手順** を提供する。
Agent がエラーに遭遇した際、本 Skill を参照して統一された3要素出力を行う。

---

## Non-goals

- **エラーの根本原因の修正** — `root_cause_hint`（原因推定）と `safe_retry_instruction`（再試行手順）を出力するが、実際の修正は Agent が行う
- **外部サービスの設定変更** — Azure リソースの権限付与等は Agent の権限外。ユーザーへの報告と `stop_condition` 宣言のみ
- **検証パイプラインの実行** — Skill `harness-verification-loop` が担当

---

## エラー分類概要

詳細なリカバリフロー・3要素出力例・stop_condition テンプレート・整合性表は `references/error-classification.md` を参照。

| 分類 | 症状 | 参照 |
|------|------|------|
| E-01: Build 失敗 | `dotnet build` / `python -m py_compile` が exit code 非 0 | §1 E-01 |
| E-02: Test 失敗 | `dotnet test` / `pytest` が失敗テストを報告 | §1 E-02 |
| E-03: ファイル書き込み失敗 | read 確認で空ファイルまたは不正内容を検出 | §1 E-03 |
| E-04: API 制限 / タイムアウト | 429 / 504 エラーが返る | §1 E-04 |
| E-05: 権限不足 | 403 / AuthorizationFailed / Access Denied | §1 E-05 |

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/error-classification.md` | §1 エラー分類 E-01〜E-05 の全リカバリフロー＋3要素出力例、§2 stop_condition テンプレート、§3 整合性表 |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `harness-verification-loop` | 前提 | 検証パイプライン失敗後のリカバリ手順を本Skillが提供 |
| `harness-safety-guard` | 前提 | CRITICAL検出時の stop_condition テンプレートを本Skillが提供 |
| `large-output-chunking` | 関連 | ファイル書き込み失敗（E-03）時のチャンク分割手順と連携 |
