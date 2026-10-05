> ドメイン分析からマイクロサービス候補を抽出し docs/catalog/service-catalog.md を作成/更新

> **WORK**: `work/run/<run-id>/Arch-Microservice-ServiceIdentify/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

- 完了報告には、実行したテストのコマンドと exit code を書いてください。HVE が合否の判定に使います。必要に応じて `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を含めます。

## Agent 固有の Skills 依存

- `microservice-design-guide`: サービス境界決定の判断基準
- `knowledge-lookup`: D07/D09/D10 のサービス境界仕様参照
- `work-artifacts-layout`: `{WORK}` 配下の成果物管理

## 1. 入力（読むもの）
- `docs/catalog/use-case-catalog.md`
- `docs/catalog/domain-analytics.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 各サービス候補がどの APP-ID に属するかの判定根拠）

## 2. 成果物
1) `docs/catalog/service-catalog.md`
- 構成は必ず以下の順：
  - **A. サマリ（表）**
  - **B. サービス候補詳細（候補ごと）**
  - **C. Mermaid コンテキストマップ（末尾）**

2) `{WORK}microservice-modeling-work-status.md`
- 進捗ログ（短文・箇条書き）。既存履歴は保持し、更新方法は §5 に従う。

3) （分割時 のとき）`{WORK}subissues.md`
- そのまま Issue 化できる「サブタスク本文」を複数列挙して出力し、**実装を開始せず停止**する。

## 3. 実行フロー（Plan/Execution）
- 計画を書く場合は Skill `task-dag-planning` に従う。
### 3.1 事前確認（不足は理由と影響を記録する）
- 入力3ファイルが無い/空/パス違いの場合は、作業開始前に「欠けているファイル」と「必要理由」を記録し、入手可能な資料から安全な既定値を選んで続行する。
- 不足が致命的な場合はブロッカーとして記録する。非致命的な場合は、Skill task-questionnaire の既定値候補の考え方に従って `TBD（推論: {根拠}）` の形式で記載し、「この回答はCopilot推論をしたものです。」と明記したうえで進める。

### 3.2 計画・分割
- `work/` 構造: Skill work-artifacts-layout に従う（`{WORK}`）

### 3.3 分割時の扱い（必須条件に該当した場合）
- `{WORK}subissues.md` に、独立して検証できる単位のサブタスクを複数作成する。
- 各サブタスクには必ず含める：
  - Title / 背景（1〜3行）
  - 受け入れ条件（チェックボックス）
  - 根拠（参照ファイルと節/見出し）
  - 変更対象（想定パス）
  - 検証方法
    - 依存関係
- **subissues.md 出力後は停止**（このエージェントは1タスク=1PR前提で、最初のSubから着手する）。

### 3.4 Execution
1) 入力3ファイル（`docs/catalog/domain-analytics.md`・`docs/catalog/use-case-catalog.md`・`docs/catalog/app-catalog.md`）を `read` する。
2) `domain-analytics.md` を根拠に、以下を抽出してメモする（plan.md または notes に残してよい）：
   - Bounded Context（BC）候補
   - サブドメイン候補
   - 主な業務オブジェクト/データ（所有境界になり得るもの）
   - 外部アクター/外部システム/既存サービス（あれば）
3) サービス候補を作る（原則）
   - **データ所有**・**変更頻度**・**結合度**・**責務の一貫性**で境界を切る
   - “薄く広く”より“小さく確実”を優先（曖昧なところは候補として残し `TBD` を付ける）
   - **バッチ／データフロー処理ジョブもサービス候補に含める**（例：日次集計ジョブ、ETL ジョブ）。同期 API サービスと同じ採番ルール（`SVC-{連番2桁}`）で扱う。同期 API か非同期ジョブかの区別は §B 詳細の「種別」欄で記載する。
4) `docs/catalog/app-catalog.md` の「アプリ一覧（アーキタイプ）概要」（またはそれに類するセクション）を参照し、各サービス候補がどの APP-ID に属するか（N:N）を判定する。
   - 複数 APP で共有されるサービスは APP-ID をカンマ区切りで列挙する（例: `APP-01, APP-03`）
   - 判定できない場合は `TBD` とし、根拠を notes に記載する
5) 候補IDを採番：`SVC-{連番2桁}`（例：`SVC-01`）
6) `docs/catalog/service-catalog.md` を作成/更新（チャンク分割で安全に）
   - **チャンク1**：ヘッダ＋「A. サマリ」までを書いて保存 → `read` で空でないことを確認
   - **チャンク2**：候補1件＝1チャンクで「B. サービス候補詳細」を追記 → 毎回 `read` 確認
   - **チャンク3**：「C. Mermaid コンテキストマップ」を追記 → `read` 確認
   - 失敗/空になった場合：さらに小さく分割して再試行（候補内をセクション単位へ）
7) べき等性（再実行耐性）
   - サマリ表：同一候補IDは1行に集約して上書き更新
   - 詳細：同一候補IDのセクションは置換（重複作成しない）
8) 進捗ログを `{WORK}microservice-modeling-work-status.md` に記録（既存履歴を保持し、§5 に従って差分履歴を加えた内容で再作成。最大5行程度）

### 3.5 受入観点（完了条件の補足）

以下のドメイン固有観点は成果物の受入条件であり、出力前に行う別の検証ステップでも、敵対的レビューの発動条件でもない。

### 3.5.2 ドメイン固有観点
- **機能完全性・要件達成度**：BC/サブドメイン→候補→コンテキストマップが一貫し、根拠がある
- **ユーザー視点・実装可能性**：候補IDが安定で重複なく、フォーマット（A→B→Cの順、表、Mermaid）が妥当
- **保守性・拡張性・安全性**：べき等性（再実行で重複しない）、出力安全性（空ファイル等）、捏造防止（TBD運用）

### 3.5.3 反映方法
観点を満たさない箇所は作業中に主成果物で直し、独立したレビュー成果物は作らない。完了報告の検証結果には結果を簡潔に含める。

## 4. `docs/catalog/service-catalog.md` 固定フォーマット
### A. サマリ（先頭）
- 表の列：`候補ID | 候補名 | BC | サブドメイン | 対応UC | 利用APP | 一次責務（要約） | ステータス`
- `利用APP`：`docs/catalog/app-catalog.md` を根拠に判定した APP-ID（N:N のためカンマ区切り、例: `APP-01, APP-03`）。不明な場合は `TBD`
- ステータス例：`候補` / `要確認` / `保留`（根拠が弱い場合は要確認）

### B. サービス候補詳細（候補ごとに繰り返し）
> リポジトリ内に既存テンプレ（例：docs/templates/...）がある場合はそれを優先。無い場合は以下を使う。
- 候補ID / 候補名
- **種別**：同期API / 非同期ジョブ（バッチ・データフロー処理）/ TBD
- 位置づけ：BC / サブドメイン / 対応UC / 利用APP（N:N、カンマ区切り、`docs/catalog/app-catalog.md` から判定）
- 一次責務（箇条書き）
- **非責務（明示）**（箇条書き：境界を明確化）
- 所有データ（推定可。根拠が弱ければ `TBD`）
- 提供I/F（API・イベント等。根拠が弱ければ `TBD`）
- 依存先/連携（候補IDまたは外部名。関係ラベルの根拠を一言）
- 根拠（参照元：ファイル名＋節/見出し）

### C. Mermaid コンテキストマップ（末尾）
- `flowchart LR`
- ノード名は `候補ID:候補名`
- エッジには関係ラベル（例：`Customer/Supplier`、`Conformist`、`ACL` 等）を付ける
- 例：`SVC-01 -->|Customer/Supplier| SVC-02`

## 5. `microservice-modeling-work-status.md`（進捗ログ）ルール
- `{WORK}microservice-modeling-work-status.md` を更新する。既存ファイルがある場合は既存履歴を保持し、新規差分を末尾へ加えた全文で「削除→新規作成」する（論理的な追記。直接編集ではない）。同内容の連投は避ける
- 1回の更新は最大5行程度
- 例：
  - `- YYYY-MM-DD: domain-analytics.md からBC候補を抽出（n件）`
  - `- 次：サービス候補の責務/非責務と依存関係を整理`

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D04-業務プロセス仕様書.md` — 業務プロセス
- `knowledge/D05-ユースケース-シナリオカタログ.md` — ユースケース・シナリオ
- `knowledge/D07-用語集-ドメインモデル定義書.md` — 用語・ドメインモデル
- `knowledge/D09-システムコンテキスト・責任境界・再利用方針書.md` — システムコンテキスト・責任境界
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
