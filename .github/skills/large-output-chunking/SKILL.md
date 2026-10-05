---
name: large-output-chunking
description: >
  大きな出力を会話へ入れ過ぎないための扱いと書き込み確認手順。 USE FOR: terminal output handling, write safety, staged writing, read verification, retry on write failure, 300-line write guidance reference. DO NOT USE FOR: data-model split thresholds, split axis design decision, normal verification. WHEN: terminal output が長い、成果物を書き込む、書き込み結果が空または不正なとき。
metadata:
  origin: user
  version: 2.1.0
---

# large-output-chunking

## 目的

長い terminal output と大きな書き込みを、後から確認できる形で小さく扱うための共通メモ。
分割サイズの正本ではなく、実行時プロンプトと書き込み確認手順への参照を置く。

## Non-goals

- データモデル生成の文字数分割閾値を定義しない。
- ファイル配置パスは Skill `work-artifacts-layout` を参照する。
- 通常の検証判定は Skill `harness-verification-loop` を参照する。

## 書き込み単位

`1 回の書込みは 300 行以内` とする。正本は
`.github/prompts/runtime/runner/runtime-guidance-suffix.prompt.md` の FR-CLI-102 runtime guidance であり、
この Skill は Cloud Copilot coding agent や VS Code session が同じ制約を見つけるために参照する。
理由は、長すぎる一括書き込みは欠落や空ファイルを見落としやすく、失敗時の再試行範囲も大きくなるため。

## terminal output の会話外処理

- 長い terminal output は会話へ全文注入しない。コマンドの quiet option を使い、必要なら安全な run-scoped ファイルへ保存して、失敗行・summary・exit code だけを限定抽出する。
- 継続時間が長い実行や出力上限を超える可能性がある実行は `execution_subagent` へ委譲し、親会話にはコマンド、exit code、summary、失敗理由の要約だけを返す。
- 秘密値を含む原本は保存せず、保存前に安全な項目だけを選別する。正常な空出力は許容し、埋め草で非空にしない。
- 出力全体が必要な場合も会話へ貼り戻さず、保存先と hash を返し、必要な部分だけを後から限定抽出する。

## 書き込み確認とリトライ

1. 書き込む。
2. 直後に読み戻し、空でないことと直前に書いた見出し・末尾行などの目印を確認する。
3. 空または不正なら、同じ内容をより小さい単位に分けて再書き込みする。
4. リトライは最大 3 回までとし、失敗範囲を広げない。

短い補足は `references/chunking-procedure.md` を参照する。

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/chunking-procedure.md` | 書き込み確認、読み戻し、最大 3 回の小分けリトライ |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `work-artifacts-layout` | 前提 | artifacts/ ディレクトリ構造の定義元 |
| `harness-verification-loop` | 後続 | 分割後の各 part の通常検証 |
| `adversarial-review` | 条件付き | 明示的な敵対的レビュー時のみ使用 |
| `harness-error-recovery` | 関連 | 書き込み失敗時の原因・再試行条件・停止条件の記録と連携 |
