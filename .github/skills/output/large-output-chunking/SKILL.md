---
name: large-output-chunking
description: >
  巨大出力の分割ルール。50,000文字超は分割必須、20,000文字以下が推奨上限。
  意味のある単位（章/サービス/API/モジュール）で分割し、
  artifacts/<name>.index.md + artifacts/<name>.part-XXXX.md 形式で保存する。
  書き込み安全策（段階的書き込み・read 検証・最大3回リトライ・分割切替）を提供する。
  USE FOR: large output splitting, 50000 char threshold, chunking,
  index plus part format, write safety, staged writing,
  read verification, retry on write failure.
  DO NOT USE FOR: split axis design decision (agents decide),
  content quality evaluation (use adversarial-review),
  file path decision (use work-artifacts-layout).
  WHEN: 大量の出力を生成する、50,000文字を超えそう、
  ファイルが巨大になりそう、分割して保存したい、
  index + part 形式で保存、書き込みが失敗する、
  リトライしても書き込みが安定しない、チャンク分割。
metadata:
  origin: user
  version: "2.0.0"
---

# large-output-chunking

> ⚠️ **必須：失敗とレビュー困難を防ぐ**
> 1ファイルが **50,000文字超** になりそうな場合、分割は強制（copilot-instructions.md §0 準拠）。
> **20,000文字以下** を推奨上限とする。

## 目的

巨大出力によるコンテキスト超過・レビュー困難・書き込み失敗を防ぐため、成果物を意味のある単位で分割し、`artifacts/<name>.index.md` + `artifacts/<name>.part-XXXX.md` 形式で保存する。

## Non-goals

- **分割軸の設計判断** — Agent が決定する。本スキルは分割の実行手順と閾値のみを提供する
- **ファイル内容の品質評価** — Skill `adversarial-review` が担当
- **ファイル配置パスの決定** — Skill `work-artifacts-layout` が定義する

## §0 分割閾値（copilot-instructions.md §0 準拠）

| 推定サイズ | 対応 |
|-----------|------|
| **50,000文字超** | 🔴 **分割必須**（強制） |
| **20,001〜50,000文字** | 🟡 分割を強く推奨 |
| **20,000文字以下** | 🟢 推奨上限内（分割は任意） |

## 分割手順・書き込み安全策

詳細手順（§1 分割軸・index構成・part先頭メタ、§3 段階的書き込み・リトライ・切替テンプレート）は `references/chunking-procedure.md` を参照。

---

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/chunking-procedure.md` | §1 手順詳細（分割軸・index/part構成）、§2 part メタ、§3 書き込み安全策全体（3.1〜3.3） |

---

## 入出力例

> ※ 以下は説明用の架空例です

**例1（60,000文字 → 分割必須）**: 推定60,000文字 > 50,000文字 → 分割確定。`service-catalog.index.md` + `service-catalog.part-0001.md`〜`part-0003.md` に分割。

**例2（25,000文字 → 分割推奨）**: 推定25,000文字 → 50,000文字未満のため分割は強制ではない。ただし20,000文字超のため分割を強く推奨。意味のある単位で2分割。

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `work-artifacts-layout` | 前提 | artifacts/ ディレクトリ構造の定義元 |
| `adversarial-review` | 後続 | 分割後の各 part の品質検証 |
| `harness-error-recovery` | 関連 | 書き込み失敗（E-03）時のリトライルールと連携 |
