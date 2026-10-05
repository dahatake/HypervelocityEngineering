---
name: harness-verification-loop
description: >
  変更後の完了判定を、要求定義から導いた対象コマンドの exit code と実出力で記録する。 PHASE: 実行後。 USE FOR: scoped verification, target tests, evidence-based completion. DO NOT USE FOR: error recovery (use harness-error-recovery), pre-execution safety check (use harness-safety-guard), broad regression planning. WHEN: コードを変更した後、完了条件を検証するとき。
metadata:
  origin: user
  version: 2.1.0
---

# harness-verification-loop

## 目的

変更後の完了を、要求定義から導いたコマンドの exit code で判定する。
合否を文章だけで主張しない。後から検証できないため。

## Non-goals

- エラー発生時のリカバリ手順は Skill `harness-error-recovery` を参照する。
- 破壊的操作の検出は Skill `harness-safety-guard` を参照する。
- 広い回帰計画や CI 設計はこの Skill で定義しない。

---

## 検証範囲

- 実行するのは対象変更に対応する対象テストまたは対象コマンドだけにする。
- 引数なしの全件回帰はローカルで繰り返さず、PR の CI で 1 回確認する。
- 未実行の検査を実行済みとして扱わない。実行できなかった理由と未測定事項を記録する。
- 既存失敗がある場合は、baseline と比較して対象変更で増えた失敗がないかを記録する。

## 記録すること

- 要求定義から導いた受入条件。
- 実行したコマンド、対象パス、exit code、要約した実出力。
- PASS / FAIL / BLOCKED の判定理由。
- TDD RED/GREEN Step の実テスト結果は `tdd-test-report.md` に分け、汎用の `verification-report.md` と混在させない。

詳細な記録例は `references/verification-commands.md` を参照する。

---

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `harness-error-recovery` | 後続 | 失敗時の原因・再試行条件・停止条件の記録 |
| `harness-safety-guard` | 前提 | コマンド実行前の安全チェック |
| `work-artifacts-layout` | 出力先 | `verification-report.md` の配置先と `{WORK}` 構造の参照先 |
| `adversarial-review` | 条件付き補完 | 通常の自動検証とは別に、明示時のみの敵対的レビューを扱う |
