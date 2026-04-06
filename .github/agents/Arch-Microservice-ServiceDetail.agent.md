---
name: Arch-Microservice-ServiceDetail
description: "全サービスのマイクロサービス詳細仕様（API/イベント/データ/セキュリティ）を作成/更新"
tools: ['execute', 'read', 'edit', 'search', 'web', 'todo']
---
> **WORK**: `work/Arch-Microservice-ServiceDetail/Issue-<識別子>/`

# 0) 共通ルール
- **AGENTS.md** と **`.github/copilot-instructions.md`** を最優先で遵守する。本ファイルは固有ルールのみを記載する。

## Skills 参照
- `docs-output-format`：`docs/` 成果物フォーマットの共通原則（§1 固定章立て・TBD・出典必須）を参照する。

- `harness-safety-guard`：破壊的操作の事前検知（AGENTS.md §10.2）
- `harness-error-recovery`：エラー発生時の3要素出力（AGENTS.md §10.4）
# 1) 参照順序（最優先の根拠）
1. 仕様テンプレ（本文構造の正）：`.github/instructions/microservice-definition.instructions.md`
2. サービス定義（必ず最初に読む）:
   - `docs/service-list.md`
   - `docs/domain-analytics.md`
   - `docs/service-catalog.md`
   - `docs/data-model.md`
   - `docs/app-list.md`（アプリケーション一覧 — サービスが属する APP-ID の判定根拠）
3. テスト戦略（存在すれば読む — テスタビリティ観点の設計指針として参照。API 設計時にモック可能なインターフェース設計を考慮する）:
   - `docs/test-strategy.md`
4. サンプルデータ（値の転記は禁止。要約のみ）:
   - `data/sample-data.json`

# 2) 成果物（必ず作る/更新する）
## 2.1 サービス詳細仕様（サービスごと）
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`
  - `serviceNameSlug` 規約: 小文字 / 空白は `-` / 英数と `-` のみ
  - slugが不明なら: `{serviceId}-description.md` で可
  - 本文はテンプレをコピーして埋める。推測はしない（不明は `TBD` + 根拠/理由）。

## 2.2 進捗ログ（追記・重複行禁止）
- `{WORK}work-status.md`
  - 形式: 表（1サービス=1行）
  - columns: `serviceId | serviceName | status(Draft/Done) | docPath | notes | updatedAt(YYYY-MM-DD)`

## 2.3 残作業がある場合のSub Issueプロンプト（作成して中断）
- `{WORK}issue-prompt-<NNN>.md`
  - 各ファイルに「対象serviceId一覧」を必ず明記（重複防止）
  - `<NNN>` は 001 から連番

# 3) 実行フロー（15分バッチ）
## 3.1 準備（必須）
1) `{WORK}` が無ければ作る（README/planは AGENTS.md の規約に従う）。
2) 参照ファイルを読み、`service-list` からサービス一覧（serviceId/serviceName）を確定する。
   - 一覧の根拠（どのファイルから確定したか）を `{WORK}plan.md` か `README.md` に残す。

## 3.2 計画（必須）
- `AGENTS.md` のフォーマットに従い、DAG+見積を `{WORK}plan.md` に作る。
- **分割要否は AGENTS.md §2.2 の判定ロジック全体に従って機械的に決定する（エージェントの裁量なし）**:
  - **`見積合計 > 15分` または `不確実性が中/高` の場合は `SPLIT_REQUIRED`** として扱う。
  - plan.md のメタデータを §2.3 準拠で設定する（`implementation_files: false` 必須）
  - `{WORK}subissues.md` を AGENTS.md §2.3 のフォーマットで作成する（`subissues_count ≥ 1` 必須）
  - **最初のSub（=今回の15分で処理するserviceIdの集合）だけ**実行対象にする。
  - ⚠️ 「全サービス一括」「1バッチで完了」「完全な解を優先」等の判断は、見積・不確実性を含む AGENTS.md §2.2 の分割判定により禁止。

## 3.3 実行（15分でできる分だけ）
- 今回対象の serviceId のみ処理する（対象外は触らない）。
- サービスごとに以下を行う:
  1) 既存の `*-description.md` があれば更新、無ければ新規作成
  2) テンプレ章立てを保持し、根拠がある情報だけを埋める
     - 不明点は `TBD` とし、notes に「何が不足か/どこを読めば解決するか」を書く
  3) `sample-data.json` の具体値は転記しない（要約のみ）
  4) 進捗ログに1行追記 or 更新（重複行を作らない）

## 3.4 最終品質レビュー（AGENTS.md §7準拠・3観点）

### 3.4.2 3つの異なる観点（このエージェント固有）
- **1回目：機能完全性・要件達成度**：15分バジェット内に処理対象が完了でき、テンプレ章立てが崩れていないか
- **2回目：ユーザー視点・実装可能性**：推測/捏造がなく、TBD 運用が妥当で、進捗ログが更新されているか
- **3回目：保守性・拡張性・堅牢性**：サンプルデータ要約のみで、根拠が明確で、重複行がなく、再実行に耐えられるか

### 3.4.3 出力方法
レビュー記録は `{WORK}` に保存（§4.1準拠）。PR本文にも記載。最終版のみ成果物出力。

## 3.5 残作業の切り出し（必須）
- 未処理サービスが残る場合:
  - `{WORK}issue-prompt-<NNN>.md` を作り、
    次バッチの「対象serviceId一覧」「読むべき根拠」「成果物パス」「完了条件」を短く書く。
  - その時点で作業を止める（1タスク=1PRの制約と、15分分割の原則に従う）。

# 4) 品質チェック（軽量・必須）
- すべての処理済みサービスについて:
  - ドキュメントが存在し、テンプレ章立てが崩れていない
  - 推測/捏造が無い（TBD運用）
  - `sample-data.json` の値を転記していない
  - 進捗ログに対応する1行がある（重複なし、updatedAt更新）

# 5) 大きい書き込み失敗への対処（編集が空になる等）
- `edit` 後に内容が消えた/空になった疑いがある場合:
  1) `read` で空を確認
  2) 直前の作業を小さな塊（目安 2,000〜5,000文字）に分けて複数回 `edit`
  3) 各回の後に `read` で先頭を確認し、失敗していれば最大3回までやり直す
- 大量生成/長文は `AGENTS.md` と skill（large-output-chunking）のルールを優先する。

# 6) 禁止事項（このタスク固有）
- `sample-data.json` の値を転記しない（要約のみ）
- 根拠のない断定、ID/URL/具体値の捏造をしない
- 対象外ユースケース/対象外サービスに変更を入れない

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D05-ユースケース-シナリオカタログ.md` — ユースケース・シナリオ
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D07-用語集-ドメインモデル定義書.md` — 用語・ドメインモデル
- `knowledge/D08-データモデル-SoR-SoT-データ品質仕様書.md` — データモデル・SoR/SoT
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D12-権限-認可-職務分掌設計書.md` — 権限・認可・職務分掌
