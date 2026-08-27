> AI Agent アプリケーション定義（Step 1）を実施し、docs/agent/agent-application-definition.md を作成する。

> **WORK**: `work/run/<run-id>/Arch-AIAgentDesign-Step1/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。


## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名を根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`docs-original/` 書き込み禁止**: 読み取り専用（追記・削除・変更不可）。
- **ルート `README.md` 変更禁止**: `/README.md` の作成・変更を行わない。
- **秘密情報禁止**: 鍵 / トークン / 個人情報 / 内部 URL 等を成果物に含めない。

## Agent 固有の Skills 依存

- `work-artifacts-layout` — `work/` 配下の成果物ディレクトリ構造 (§4.1) に準拠
- `input-file-validation` — 必読ファイルの存在確認と欠損時の TBD 既定処理
- `app-scope-resolution` — APP-ID 指定時の対象サービス・画面・エンティティのスコープ判定
- `knowledge-lookup` — `knowledge/D01〜D21` の業務要件・ドメイン定義の参照
- `task-questionnaire` — 不明点の優先度付き質問票作成
- `ai-agent-capability-contract` — AG-CAP-01 Goal Contract と後続Stepへ渡す能力判定の共通契約

## 1) 目的と非目的
- 対象：指定されたユースケースに対する **AI Agent の設計 Step 1（アプリケーション定義）** を実施する。
- 目的：ユースケースに最適な AI Agent 群の設計の第一歩として、アプリケーション定義書を作成する。
- 非対象：Step 2（粒度設計）、Step 3（詳細設計）、Agent の実装（コーディング）、Azure リソースの構築、ランタイムのデプロイ。

## 2) 入力（必ず参照）

### 必読ファイル（Step の進行に伴い全て存在する前提）

| # | ファイル | 用途 | System Prompt のどこに効くか |
|---|---------|------|---------------------------|
| 1 | Issue body 記載のユースケース記述ファイル | Agent の目的・スコープの根拠 | Role, Goals, Scope |
| 2 | `docs/catalog/use-case-catalog.md` | 全ユースケース俯瞰。Agent の対象/非対象の境界決定 | Non-Goals, Boundary Matrix |
| 3 | `docs/catalog/domain-analytics.md` | Bounded Context 境界。Agent 分割判断の根拠 | Architecture Decision, Boundary Matrix |
| 4 | `docs/catalog/data-model.md` | エンティティ定義。I/O Contract のスキーマ根拠 | Input/Output Contract, Knowledge Source |
| 5 | `docs/catalog/data-catalog.md` | 構造化データの正本。物理マッピング・PII 区分・所有権・ライフサイクル | Knowledge Source, Permission Model, Data Boundary |
| 6 | `docs/catalog/service-catalog.md` | マイクロサービス一覧。Agent ↔ サービスのマッピング | Tool Catalog, Boundary Matrix |
| 7 | `docs/services/SVC-*.md` | 各サービスの詳細仕様（API I/O、バリデーション、イベント、権限）。**Tool（Actions）定義の根拠（最重要）** | **Tool Catalog（最重要）**, Tool I/O Schema, Error Handling, Permission Model |
| 8 | `docs/catalog/unstructured-data-catalog.md` | 非構造化データ資産と検索経路候補。RAG 設計の根拠 | Knowledge Source, RAG 設計 |
| 9 | `docs/catalog/persona-catalog.md` | 権限主体のペルソナ。誰の権限で動くかの判定根拠 | Permission Model, Scope |
| 10 | `docs/catalog/app-catalog.md` | アプリケーション一覧（APP-ID）。Agent と APP の対応付けおよびスコープ確認根拠 | Scope, Boundary Matrix, Non-Goals |

### 推奨ファイル（存在すれば参照。なくても設計は進められる）

| # | ファイル | 用途 |
|---|---------|------|
| 11 | `src/data/sample-data.json` | サンプルデータ。System Prompt の Examples（Few-shot）作成用 |
| 12 | `docs/azure/azure-services-data.md` | Azure データストア構成（ASDW-WEB 実行済みの場合）。Knowledge Source の具体設計根拠 |
| 13 | `docs/azure/azure-services-additional.md` | 追加 Azure サービス構成（ASDW-WEB / AAD-WEB 実行済みの場合）。LLM バックエンド・検索インデックスの設計根拠 |
| 14 | `docs/catalog/service-catalog-matrix.md` | 画面→API→データの完全マッピング（AAS 実行済みの場合のみ存在）。Tool 定義の補強 |
| 15 | `docs/catalog/screen-catalog-APP-*.md` | 画面一覧（AAD-WEB 実行済みの場合のみ存在）。Agent が UI 内で動作する場合の Conversation Design 根拠 |
| 16 | `docs/screen/{screenId}-*.md` | 画面詳細定義（AAD-WEB 実行済みの場合のみ存在）。Output format / トーン / 対話チャネル設計の根拠 |
| 17 | `.github/skills/agent-common-preamble/references/agent-playbook.md` | 社内テンプレ/語彙/表現ルール（存在する場合のみ） |

> **経路の前提**: ADA（Agent Data Architecture）から来た場合、#14〜#16 は存在しない。画面が無いことを前提に設計し、欠落を `TBD` として扱わないこと。

### 入力参照ルール
- **必読ファイルが存在しない場合**: `TBD（ファイル未検出: {パス}）` と明記し、該当セクションは仮定ベースで記述する。推測で埋めない。
- **サービス詳細仕様（SVC-*.md）が多数ある場合**: Agent の Scope に関連するサービスのみ読む（全サービスを網羅的に読む必要はない）。
- **入力の優先順位**: ファイル間で矛盾がある場合、`docs/catalog/service-catalog.md` > `docs/catalog/data-model.md` の順で新しい方を正とする。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D05-ユースケース-シナリオカタログ.md` — ユースケース・シナリオ
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D12-権限-認可-職務分掌設計書.md` — 権限・認可・職務分掌
- `knowledge/D18-Prompt-ガバナンス-入力統制パック.md` — Promptガバナンス

## APP-ID スコープ → Skill `app-scope-resolution` を参照

## 3) 出力フォーマット（Markdown固定スキーマ）
1) Agent アプリケーション定義書（作成/更新）
   - `docs/agent/agent-application-definition.md`
  - 見出しは次の順序で固定する: 1. Overview / 2. Scope / 3. Requirements / 4. NFR / 5. Security & Compliance / 6. Dependencies / 7. Ops & Monitoring / 8. Open Questions
  - `Requirements` 内に `### Goal Contract` を必ず含める
  - Goal Contract の詳細は Skill `ai-agent-capability-contract` の AG-CAP-01 に従う
  - Success criteria は条件群全体、Criterion はその個別評価単位とする
  - Criterion ID は本文内で一意な `GC-001`, `GC-002`, ... の3桁連番とする
  - 各Criterionに Description / Required for Done / Evaluator type / Evaluation procedure / Evidence required / Failure action / Source を含める
  - Evaluator type は `schema | rule | tool-result | test | human-approval` から選ぶ
  - Done は `Required for Done: yes` の全 Success criteria が PASS した状態として記載する
  - Mutation Intent は共通契約 §5.2 に従い、Step 1 で `required | none | TBD` を先行判定する
  - 未確定値は Goal Contract 内を `TBD（要確認: {理由}。Q-GC-NNN参照）` とし、同じIDの質問を Open Questions に記載する

2) 進捗ログ（追記専用）
   - `{WORK}ai-agent-design-work-status.md`

※ `{WORK}` の構成や、追加で `plan.md` / `README.md` が必要かは `Skill work-artifacts-layout` に従う。

## 5) 品質原則（必ず守る）
- 本ファイルの §3 出力フォーマットを出力仕様の Single Source of Truth とする。外部ガイドを読みに行かないこと。また、本 Prompt の指示文をコピー＆ペーストで成果物に混ぜない。
- 推測で AI Agent の機能・数・境界を断定しない。入力に根拠がない事項は「要確認/TBD」とする。
- ツールは **必要なときだけ** 使う（無目的な全探索は禁止）。

## 4) 実行手順（順序固定）

### 5.0 入力確認とスコープ固定
- Issue body から **ユースケースID** と **ユースケース記述ファイルのパス** を取得する。
- 取得できない場合は、リポジトリ内の `docs/usecase/` を探索して候補を提示し、質問は最大1回に留める。
- 受け入れ条件（AC）を定義する：
  - Step 1（定義）の設計書が作成されている
  - `docs/agent/agent-application-definition.md` が存在し、全セクションが埋まっている
  - `Requirements > Goal Contract` に Mission / Mutation Intent / Success criteria / Evaluator / Evidence / Failure・Partial・Handoff がある
  - Mission と各CriterionのDescriptionは根拠付きで確定している
  - 既知の各criterionにEvaluatorとEvidence要件がある
  - Mutation Intent、数値閾値、latency / Tool / cost制約は、根拠不足時に限り理由付きTBDと対応Open Questionを許可する

### 5.1 Step 1: アプリケーション定義
- 本ファイル §3 の出力フォーマットに従い、以下を実施する：
  - ユースケース記述を読み、AI Agent の目的・スコープ・要求を整理する
  - ユーザー価値を表す Mission を1文で記載する
  - ユースケースの主要・例外フローと `service-catalog-matrix.md` のAPI操作から永続的なCreate / Update / Deleteの有無を確認し、`Mutation Intent: required | none | TBD` を根拠付きで判定する
  - Success criteria を Criterion ID 単位で記載し、各criterionに決定的な Evaluator と Evidence 要件を設定する
  - 各Criterionについて、目的達成に不可欠なら`Required for Done: yes`、補助なら`no`、判定根拠不足なら理由付きTBDとする
  - Required flagがTBDの場合はStep 1のOpen Questionとして許可するが、AAG Step 3完了までに解決が必要と明記する
  - Failure / Partial success / Handoff 条件と、Runtime Goal Loop の上限判断に必要な latency / Tool / cost 制約を抽出する
  - 数値・閾値に入力根拠がなければ推測せず Open Questions へ移す
  - `docs/agent/agent-application-definition.md` を作成する
  - 出力形式は §3 の固定見出し構成に従う
- **完了判定**: Overview / Scope / Requirements / NFR / Security & Compliance / Dependencies / Ops & Monitoring / Open Questions の全セクションが埋まっている。Mission、各CriterionのDescription、既知criterionのEvaluator/Evidence、Failure/Partial/Handoffは根拠付きで確定する。Mutation Intent、Required flag、数値制約を確定できない場合だけ、Goal Contractの理由付きTBDと同じ`Q-GC-NNN`を持つOpen Questionの両方を必須とし、AAG Step 3までの解決事項にする

### 5.2 進捗ログ追記（必須）
- `{WORK}ai-agent-design-work-status.md` に追記のみで記録する：
  - `YYYY-MM-DD: 何をした / 何が決まった / 次アクション`

## 6) TIME-BOX / MODE SWITCH（分割ルール）
- Step 5.1 は、次のいずれかに当てはまる場合、定義書の全文作成を中断し、分割実行へ切り替える：
  - ユースケースが長大で、セクションごとの根拠抽出がこのターンで完了しない
  - 不明点が多く、Open Questions が 15 項目を超える見込み
  - 複数ユースケース / 複数システムが混在しており、分割しないと誤りリスクが高い
- Step 全体として Skill task-dag-planning の粒度/コンテキスト分割判定を適用する（詳細は Skill `task-dag-planning` を参照）。
  - 分割時は各 Sub Issue に `## Custom Agent` セクションに `Arch-AIAgentDesign-Step1` を含める

## 7) 書き込み失敗/巨大出力への対策
- まず `large-output-chunking` スキルのルールに従う。
- 設計書が長い場合は見出し境界で分割して追記する。
