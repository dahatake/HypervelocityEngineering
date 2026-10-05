---
name: task-dag-planning
description: >
  計画を書くときの最小規約（受入条件と非対象、exit code で判定できる完了条件、独立して検証できる分割単位、任意の見積）を提供するスキル。
  USE FOR: create plan, estimate task, task decomposition into a dependency graph, acceptance criteria and non-goals,
  definition-of-done rules, choosing independently verifiable split units when the agent decides to split.
  DO NOT USE FOR: implementation execution (agents do that separately), forcing a split from task size.
  WHEN: 計画を立てたい、見積をしたい、作業を分けるか考えたい。
metadata:
  origin: user
  version: 4.0.0
category: planning
---

# task-dag-planning

## 目的

計画を書くときの最小規約を定める。分割するかどうかはモデルが作業内容から判断する（FR-PLAN-01）。作業量やファイル数から分割を機械的に強制する規則は置かない。ATG の実測で、計画用 DAG の強制は完成率を上げず時間と費用を増やしたためである。

- 規約の詳細は [references/planning.md](references/planning.md)。
- HVE 固有の `plan.md` / `subissues.md` の形式と実行面ごとの扱いは [`../_hve-plan-artifacts/hve-binding.md`](../_hve-plan-artifacts/hve-binding.md) にある。

## 規約（3 点）

1. 受入条件と非対象を書く。何を満たせば完了で、何を扱わないかが後から読んで分かるようにするためである。
2. 完了条件を exit code またはファイルの状態で判定できる形にする。自然言語の主張ではなく、コマンドの実出力で合否を示せるようにするためである。`plan.md` には `## 完了条件` を置く（FR-DOD-02）。
3. 分割するなら、独立して検証できる単位で分ける。1 単位の合否が他の単位の完成を待たずに判定できれば、失敗の切り分けと再実行が小さく済むためである。

見積（読込 / 計画 / 実装 / 検証 / 予備の分数）は任意とする。付ける場合は計画の比較にだけ使い、合否の判定には使わない。

## 手順サマリ

1. 実行面（standalone / Cloud / CLI-GUI / Prompt Edition controller）を確かめる（[`hve-binding.md`](../_hve-plan-artifacts/hve-binding.md) §4）。実行面によって、分割を選んだ場合の手段が異なる。
2. 受入条件と非対象を固定し、成果物ごとのノードと依存を書く。
3. 完了条件を exit code またはファイル状態で判定できる形にしてから実装へ進む。
4. 1 回の作業で終わらないと判断した場合に限り、独立して検証できる単位で分割する。Cloud では `subissues.md` を使える（[`subissues-template.md`](../_hve-plan-artifacts/subissues-template.md)）。

## 質問しないための判断

| 状況 | 自動動作 |
|---|---|
| 任意項目が未指定 | 既定値を適用する |
| 必須項目が未指定だが一意に解決可能 | 出典付きで解決し計画へ固定する |
| 必須項目の候補が複数 | 安全境界・資格情報・不可逆操作に関わる候補だけ停止する。それ以外は要求定義の目的に最も適う候補を選び、選定理由と棄却した候補を計画へ記録して続行する |
| 資格情報・権限が不足 | 停止する。秘密値を生成・保存しない |
| 本番デプロイ・課金・削除・権限変更 | 既存の明示承認が無い限り実行しない |

## 関連 Skill

| Skill | 関係 | 説明 |
|-------|------|------|
| `task-questionnaire` | 前提 | コンテキスト収集が完了してから計画フェーズへ遷移する |
| `work-artifacts-layout` | 出力先 | `plan.md` / `subissues.md` / `work-status.md` / `README.md` の配置パス規則 |
| `harness-verification-loop` | 後続 | 実装後の検証パイプライン |
| `adversarial-review` | 後続 | レビュー（marker / label / ユーザー依頼 / HVE Phase 3 の明示時のみ） |

## 詳細ガイド（Progressive Disclosure）

- 規約の詳細: [references/planning.md](references/planning.md)
- HVE 固有の成果物フォーマット・実行面: [`../_hve-plan-artifacts/hve-binding.md`](../_hve-plan-artifacts/hve-binding.md)
