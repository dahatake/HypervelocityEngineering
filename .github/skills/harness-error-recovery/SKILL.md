---
name: harness-error-recovery
description: >
  エラー発生時に原因、再試行条件、停止条件を短く記録する契約。 PHASE: エラー発生時。 USE FOR: error recovery notes, retry condition, stop condition, write retry coordination. DO NOT USE FOR: verification execution (use harness-verification-loop), pre-execution safety check (use harness-safety-guard), fixed error taxonomy. WHEN: エラーが発生し、続行可否を記録するとき。
metadata:
  origin: user
  version: 2.1.0
---

# harness-error-recovery

## 目的

エラーに遭遇したとき、次に進めるかを後から確認できる形で記録する。
分類表ではなく、原因、再試行できる条件、停止する条件だけを残す。

---

## Non-goals

- エラー分類コードや固定テンプレートは提供しない。
- 検証コマンドの選択は Skill `harness-verification-loop` を参照する。
- 破壊的操作の扱いは Skill `harness-safety-guard` を参照する。

---

## 記録すること

- 原因: 実出力、exit code、対象ファイル、失敗した操作から分かる範囲で書く。
- 再試行条件: 何が変われば安全に再試行できるかを書く。
- 停止条件: どの条件なら続行しないかを書く。

書き込み失敗では Skill `large-output-chunking` の書き込みリトライ規則に従い、書く、読み戻す、空または不正なら小さくして最大 3 回まで再試行する。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/error-classification.md` | 旧分類表ではなく、原因・再試行条件・停止条件の短い記録例 |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `harness-verification-loop` | 前提 | 対象コマンドと exit code による判定 |
| `harness-safety-guard` | 前提 | 危険操作検出時の扱い |
| `large-output-chunking` | 関連 | 書き込み失敗時の読み戻しと小分けリトライ |
