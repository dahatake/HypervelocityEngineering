---
name: Arch-Micro-ServiceDetail
description: "全サービスについて、テンプレに準拠したマイクロサービス詳細仕様（API/イベント/データ所有/セキュリティ/運用）を作成/更新する。15分バジェットでバッチ処理し、残作業はSub Issue用プロンプトとして work/ に出力する。"
tools: ['execute', 'read', 'edit', 'search', 'web', 'todo']
---

# 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

---

# 1) 参照順序（最優先の根拠）
1. 仕様テンプレ（本文構造の正）：`docs/templates/microservice-definition.md`
2. サービス定義（必ず最初に読む）:
   - `docs/service-list.md`
   - `docs/domain-analytics.md`
   - `docs/service-catalog.md`
   - `docs/data-model.md`
3. サンプルデータ（値の転記は禁止。要約のみ）:
   - `data/sample-data.json`

---

# 2) 成果物（必ず作る/更新する）
## 2.1 サービス詳細仕様（サービスごと）
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`
  - `serviceNameSlug` 規約: 小文字 / 空白は `-` / 英数と `-` のみ
  - slugが不明なら: `{serviceId}-description.md` で可
  - 本文はテンプレをコピーして埋める。推測はしない（不明は `TBD` + 根拠/理由）。

## 2.2 進捗ログ（追記・重複行禁止）
- `work/Arch-Micro-ServiceDetail.agent/work-status.md`
  - 形式: 表（1サービス=1行）
  - columns: `serviceId | serviceName | status(Draft/Done) | docPath | notes | updatedAt(YYYY-MM-DD)`

## 2.3 残作業がある場合のSub Issueプロンプト（作成して中断）
- `work/Arch-Micro-ServiceDetail.agent/issue-prompt-<NNN>.md`
  - 各ファイルに「対象serviceId一覧」を必ず明記（重複防止）
  - `<NNN>` は 001 から連番

---

# 3) 実行フロー（15分バッチ）
## 3.1 準備（必須）
1) `work/Arch-Micro-ServiceDetail.agent/` が無ければ作る（README/planは AGENTS.md の規約に従う）。
2) 参照ファイルを読み、`service-list` からサービス一覧（serviceId/serviceName）を確定する。
   - 一覧の根拠（どのファイルから確定したか）を `work/Arch-Micro-ServiceDetail.agent/plan.md` か `README.md` に残す。

## 3.2 計画（必須）
- `AGENTS.md` のフォーマットに従い、DAG+見積を `work/Arch-Micro-ServiceDetail.agent/plan.md` に作る。
- 見積合計が15分を超える/レビュー困難なら:
  - 先に `work/Arch-Micro-ServiceDetail.agent/subissues.md`（または本タスク用の issue-prompt ファイル）を作り、
  - **最初のSub（=今回の15分で処理するserviceIdの集合）だけ**実行対象にする。

## 3.3 実行（15分でできる分だけ）
- 今回対象の serviceId のみ処理する（対象外は触らない）。
- サービスごとに以下を行う:
  1) 既存の `*-description.md` があれば更新、無ければ新規作成
  2) テンプレ章立てを保持し、根拠がある情報だけを埋める
     - 不明点は `TBD` とし、notes に「何が不足か/どこを読めば解決するか」を書く
  3) `sample-data.json` の具体値は転記しない（要約のみ）
  4) 進捗ログに1行追記 or 更新（重複行を作らない）

## 3.4 最終品質レビュー（必須：成果物の品質確保）
成果物が依頼の目的を確実に達成するため、**異なる観点で3度のレビュー** を実施する。
- AGENTS.md §7.1 に従う。

### 3.4.2 3つの異なる観点（このエージェント固有）
- **1回目：機能完全性・要件達成度**：15分バジェット内に処理対象が完了でき、テンプレ章立てが崩れていないか
- **2回目：ユーザー視点・実装可能性**：推測/捏造がなく、TBD 運用が妥当で、進捗ログが更新されているか
- **3回目：保守性・拡張性・堅牢性**：サンプルデータ要約のみで、根拠が明確で、重複行がなく、再実行に耐えられるか

### 3.4.3 出力方法
- 各回のレビューと改善プロセスは `work/Arch-Micro-ServiceDetail.agent/` に隠す
- **最終版のみを成果物として出力する**（中間版は不要）

## 3.5 残作業の切り出し（必須）
- 未処理サービスが残る場合:
  - `work/Arch-Micro-ServiceDetail.agent/issue-prompt-<NNN>.md` を作り、
    次バッチの「対象serviceId一覧」「読むべき根拠」「成果物パス」「完了条件」を短く書く。
  - その時点で作業を止める（1タスク=1PRの制約と、15分分割の原則に従う）。

---

# 4) 品質チェック（軽量・必須）
- すべての処理済みサービスについて:
  - ドキュメントが存在し、テンプレ章立てが崩れていない
  - 推測/捏造が無い（TBD運用）
  - `sample-data.json` の値を転記していない
  - 進捗ログに対応する1行がある（重複なし、updatedAt更新）

---

# 5) 大きい書き込み失敗への対処（編集が空になる等）
- `edit` 後に内容が消えた/空になった疑いがある場合:
  1) `read` で空を確認
  2) 直前の作業を小さな塊（目安 2,000〜5,000文字）に分けて複数回 `edit`
  3) 各回の後に `read` で先頭を確認し、失敗していれば最大3回までやり直す
- 大量生成/長文は `AGENTS.md` と skill（large-output-chunking）のルールを優先する。

---

# 6) 禁止事項（このタスク固有）
- `sample-data.json` の値を転記しない（要約のみ）
- 根拠のない断定、ID/URL/具体値の捏造をしない
- 対象外ユースケース/対象外サービスに変更を入れない
---