---
name: tdd-green-retry-strategy
description: >
  TDD GREEN フェーズの再試行上限の所在と、再試行前の原因確認を示す短い契約。 USE FOR: TDD GREEN retry strategy, tdd_max_retries ownership, root cause check before retry, TDD report retry evidence. DO NOT USE FOR: RED phase test code generation, test pyramid/test-double/coverage policy (tdd-red-green-reality §1.7), RED/GREEN reality proof, generic error recovery. WHEN: GREEN 化ループで再試行回数や記録先を確認するとき。
metadata:
  origin: user
  version: 1.1.0
---

# tdd-green-retry-strategy

## 目的

TDD GREEN フェーズの再試行で、上限の正本と記録先を迷わないようにする。
リトライ回数の上限は HVE の `tdd_max_retries` が所有する。
再試行の前には、失敗出力から根本原因を確認する。理由は、同じ失敗を回数だけ消費すると
後から何を試したか分からなくなるため。

---

## Non-goals

- RED フェーズのテストコード生成は扱わない。
- RED/GREEN を実出力で証明する原則は Skill `tdd-red-green-reality` を参照する。
- HVE 生成テスト方針は Skill `tdd-red-green-reality` §1.7 を参照する。
- 一般的なエラー復旧は Skill `harness-error-recovery` を参照する。

---

## GREEN リトライの最小規則

- 再試行上限は HVE の `tdd_max_retries` を正本とする。Skill 内に別の固定上限を持たない。
- 再試行前に、exit code、失敗テスト名、エラーメッセージから根本原因を確認する。
- 外部サービス設定（Endpoint / base URL / Resource 名 / 認証経路）が不足している場合は、テストを緩めず、設定不足または環境ブロッカーとして記録する。
- GREEN 化ループの各試行は、TDD テスト結果レポート
  `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
  に記録する。最低限、失敗テスト、Root-Cause（根本原因）、次の対応を残す。
- 実装だけでは GREEN 化できない確定ブロッカーは、Step の契約に従って `TDD-Judgement: BLOCKED` として記録する。

---

## 参照元

- RED/GREEN を実出力で証明する原則: Skill `tdd-red-green-reality`
- HVE 生成テスト方針（ピラミッド・ダブル・データ・カバレッジ）: Skill `tdd-red-green-reality` §1.7
- 失敗時の原因・再試行条件・停止条件: Skill `harness-error-recovery`
- 対象コマンドの exit code による完了判定: Skill `harness-verification-loop`
