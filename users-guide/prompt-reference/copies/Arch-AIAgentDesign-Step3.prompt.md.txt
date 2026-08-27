> AI Agent 詳細設計（Step 3）を実施し、docs/agent/agent-detail-{key}.md（fan-out 子毎、1 ファイル、key = `AG-*`）および docs/ai-agent-catalog.md を作成する。

> **WORK**: `work/run/<run-id>/Arch-AIAgentDesign-Step3/Issue-<識別子>/`

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
- `task-questionnaire` — 詳細設計時の不明点確認
- `ai-agent-capability-contract` — AG-CAP-01〜10 の詳細設計・N/A・完了判定契約
- `agentic-retrieval-contract` — Section 7.0 で Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合の AR-CAP-01〜05 契約
- `foundry-toolbox-contract` — Tool 総数が 10〜15 を超えた場合の TB-CAP-01〜05 契約（Toolbox / tool search）

## 1) 目的と非目的
- 対象：指定されたユースケースに対する **AI Agent の設計 Step 3（詳細設計）** を実施し、Agent 一覧を出力する。
- 目的：Step 2 の Agent Catalog を入力として、各 Agent の詳細設計書と Agent 一覧（ai-agent-catalog.md）を作成する。
- 非対象：Step 1（アプリケーション定義）、Step 2（粒度設計）、Agent の実装（コーディング）、Azure リソースの構築、ランタイムのデプロイ。

## 2) 入力（必ず参照）

### 必読ファイル（Step の進行に伴い全て存在する前提）

| # | ファイル | 用途 | System Prompt のどこに効くか |
|---|---------|------|---------------------------|
| 1 | Issue body 記載のユースケース記述ファイル | Agent の目的・スコープの根拠 | Role, Goals, Scope |
| 2 | `docs/catalog/use-case-catalog.md` | 全ユースケース俯瞰。Agent の対象/非対象の境界決定 | Non-Goals, Boundary Matrix |
| 3 | `docs/catalog/domain-analytics.md` | Bounded Context 境界。Agent 分割判断の根拠 | Architecture Decision, Boundary Matrix |
| 4 | `docs/catalog/data-model.md` | エンティティ定義。I/O Contract のスキーマ根拠 | Input/Output Contract, Knowledge Source |
| 5 | `docs/catalog/service-catalog.md` | マイクロサービス一覧。Agent ↔ サービスのマッピング | Tool Catalog, Boundary Matrix |
| 6 | `docs/catalog/data-catalog.md` | 構造化データの正本。物理マッピング・PII 区分・所有権・ライフサイクル | Knowledge Source, Permission Model, Data Boundary |
| 7 | `docs/services/SVC-*.md` | 各サービスの詳細仕様（API I/O、バリデーション、イベント、権限）。Tool の入出力スキーマ・失敗分類の根拠 | Tool I/O Schema, Error Handling, Permission Model |
| 8 | `docs/catalog/unstructured-data-catalog.md` | 非構造化データ資産と検索経路候補。AG-CAP-03 の Preferred / Fallback と AG-CAP-10 の候補経路の根拠 | Knowledge Source, RAG 設計, Evaluation |
| 9 | `docs/catalog/persona-catalog.md` | 権限主体のペルソナ。AG-CAP-07 の Permission scope の根拠 | Permission Model, Scope |
| 10 | `docs/catalog/app-catalog.md` | アプリケーション一覧（APP-ID）。Agent と APP の対応付けおよびスコープ確認根拠 | Scope, Boundary Matrix, Non-Goals |
| — | `docs/agent/agent-application-definition.md` | **Step 1 成果物（必須前提）** | Step 3 参照用 |
| — | `docs/agent/agent-architecture.md` | **Step 2 成果物（必須前提）**。Agent Catalog の入力 | Step 3 全体 |

### 推奨ファイル（存在すれば参照。なくても設計は進められる）

| # | ファイル | 用途 |
|---|---------|------|
| 11 | `docs/catalog/service-catalog-matrix.md` | 画面→API→データの完全マッピング（AAS 実行済みの場合のみ存在）。Tool 定義の補強 |
| 11.1 | `docs/azure/azure-services-data.md` / `docs/azure/azure-services-additional.md` | Azure 構成（ASDW-WEB / AAD-WEB 実行済みの場合のみ存在）。LLM バックエンド・検索インデックスの設計根拠 |
| 11.2 | `docs/catalog/screen-catalog-APP-*.md` | 画面一覧（AAD-WEB 実行済みの場合のみ存在）。Agent が UI 内で動作する場合の Conversation Design 根拠 |
| 12 | `docs/screen/{screenId}-*.md` | 画面詳細定義（AAD-WEB 実行済みの場合のみ存在）。Output format / トーン / 対話チャネル設計の根拠。**ADA 経由の場合は存在しないので `TBD` 扱いにしない** |
| 13 | `src/data/sample-data.json` | サンプルデータ。System Prompt の Examples（Few-shot）作成用 |
| 14 | `.github/skills/agent-common-preamble/references/agent-playbook.md` | 社内テンプレ/語彙/表現ルール（存在する場合のみ） |

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
1) Agent 詳細設計書（fan-out 子毎、1 ファイル、`{key}` = `AG-*`）
   - `docs/agent/agent-detail-{key}.md`（例: `docs/agent/agent-detail-AG-01.md`）
   - Agent 名はファイル名に含めない（`_make_child` は `{key}` のみを置換するため、`{AgentName}` 等他のプレースホルダは使用しない）。

2) Agent 一覧（作成/更新）
   - `docs/ai-agent-catalog.md`

3) 進捗ログ（追記専用）
   - `{WORK}ai-agent-design-work-status.md`

※ `{WORK}` の構成や、追加で `plan.md` / `README.md` が必要かは `Skill work-artifacts-layout` に従う。

## 5) 品質原則（必ず守る）
- 本ファイルの §3 出力フォーマットと §5.1 の完成判定チェックを出力仕様の Single Source of Truth とする。外部ガイドを読みに行かないこと。また、本 Prompt の指示文をコピー＆ペーストで成果物に混ぜない。
- 推測で AI Agent の機能・数・境界を断定しない。入力に根拠がない事項は「要確認/TBD」とする。
- ツールは **必要なときだけ** 使う（無目的な全探索は禁止）。

## 4) 実行手順（順序固定）

### 5.1 Step 3: Agent 詳細設計
- 本ファイル §3 の出力フォーマットに従い、以下を実施する：
  - Step 2 の Agent Catalog の **各 Agent** について詳細設計書を作成する
  - 出力形式テンプレ（12セクション: Agent Overview〜System Prompt Instruction Format）に厳密に従う
  - Section 2.1 `Goal Contract` に Mission / Mutation Intent / Criterion / Evaluator / Evidence / Failure・Partial・Handoff を確定する
  - Section 6.1 `Runtime Goal Loop` に有限のPLAN / ACT / OBSERVE / EVALUATE / REPLAN、反復上限、deadline、budget、停止条件を確定する
  - Section 7.0 `Knowledge & Structured Data Routing` にRequest class、Preferred / Fallback / Blocked、runtime probe、permission、citationを確定する
  - **Agentic Retrieval 方針（`auto` / `yes` / `no`）に従う**。方針は Prompt 冒頭に注入される。注入が無ければ `auto` とし、**3 値以外は推測で丸めず blocked とする**
    - `auto`: 経路選択は下記の決定表に委ねる（強制しない）
    - `yes`: `enterprise-unstructured` の Request class を持つ場合、Preferred route に **Foundry IQ / Azure AI Search Agentic Retrieval** を選ぶ
    - `no`: Foundry IQ / Azure AI Search Agentic Retrieval を選ばない。AR-CAP-01〜05 も追加しない
  - Section 7.0 のPreferredまたはFallbackに **Foundry IQ / Azure AI Search Agentic Retrieval** を選んだ場合は、Skill `agentic-retrieval-contract` に従い次の見出しを Section 7.0 の直後へ追加する。選ばなかった場合は追加しない。**12セクションの番号・順序は変えない**
    - `7.0.1 Knowledge Base Contract (AR-CAP-01)` / `7.0.2 Knowledge Source Matrix (AR-CAP-02)` / `7.0.3 Retrieval Budget (AR-CAP-03)` / `7.0.4 Evidence & Observability (AR-CAP-04)` / `7.0.5 MCP Exposure (AR-CAP-05)`
    - **見出しレベルは Section 7.0 と同じレベルにする**（子レベルにしない）。子レベルにすると Section 7.0 の範囲が後続ブロックを取り込み、AG-CAP-03 の判定が壊れる
    - 同 Skill の整合ルール R1〜R15 を自己検査する。`Retrieval reasoning effort` の正本は AR-CAP-01 だけとし、AR-CAP-03 へ重複記載しない
    - **AR-CAP-02 の Knowledge Source は 2 件以上 10 件以下**にする（R14）。1 件だけならファンアウト先が 1 つしかなく、クラシックな単一クエリ検索と等価になる。横断が不要なら Agentic Retrieval を選ばず Section 7.0 で別経路にする
    - **AR-CAP-01 に `Index semantic configuration` を記載する**（R15）。各サブクエリは semantic rerank を通るため索引側の構成が検索品質の上限を決める。確定できない場合も確認予定と確認手段を書き、単語だけの `TBD` にしない
    - SKU / API version / model / region / tier 上限は本文へ確定値として埋めず、`Design status` と `Checked at` を記録する
  - Section 7.1 `REST CRUD Matrix` にC/R/U/D、REST method/path、HITL、RBAC、冪等性、error、auditを確定する。C/U/Dのprimary経路はREST Function Toolだけにする
  - Section 7.3 `MCP Integration Plan` にclient利用、Tool allowlist、auth、failure behavior、Remote adapter ownerを確定し、REST mutationを迂回させない
  - Section 7.4 `Skill Packaging Decision` をrequired / not-requiredで確定する。required時だけ配置先・resources・明示load・validationを記載する
  - Skill `ai-agent-capability-contract` に従い、Section 7.4 の後（TB-CAP を追加する場合は 7.5.x の後）へ次の見出しを追加する。**12セクションの番号・順序は変えない**
    - `7.6 Agent Identity & Authorization (AG-CAP-07)` / `7.7 Observability Contract (AG-CAP-08)` / `7.8 Distribution & Packaging (AG-CAP-09)` / `7.9 Evaluation & Route Right-sizing (AG-CAP-10)`
    - **見出しレベルは Section 7.0〜7.4 と同じレベルにする**（子レベルにしない）。子レベルにすると前のセクションの範囲が後続ブロックを取り込み、判定が壊れる
    - **AG-CAP-07 / AG-CAP-08 / AG-CAP-10 は N/A にできない**。確定できない項目は単語だけの `TBD` にせず、確認予定と確認手段を書く
    - AG-CAP-09 は配布先が無い場合だけ、`Contract ID / 理由 / Decision source / 再判定条件` を伴う**理由付きN/A**にできる
  - **Tool 総数を数える**。`Section 7.1 の Required: yes 行数` + `Section 7.3 の Tool allowlist に列挙した Tool 名数（重複排除）` + `Section 7.0 の異なる検索経路数（Preferred と Fallback。同じ経路が複数行にあっても 1 と数える）`
  - **Tool Search 方針（`auto` / `yes` / `no`）に従う**。方針は Prompt 冒頭に注入される。注入が無ければ `auto` とし、**3 値以外は推測で丸めず blocked とする**
    - `auto`: 総数が **15 を超える**場合だけ TB-CAP-01〜05 を追加する（超えない場合は追加しない）
    - `yes`: **Tool 総数に関係なく** TB-CAP-01〜05 を追加し、TB-CAP-02 の `Tool search` は `enabled` にする
    - `no`: **Tool 総数に関係なく** Toolbox を採用しない。TB-CAP-01 / TB-CAP-02 だけを追加して `Tool search` は `disabled` とし、TB-CAP-03〜05 は `Status: N/A` + `Reason` / `Decision source` / `Recheck condition` を持つ**理由付き N/A** とする
  - TB-CAP を追加する場合は、Skill `foundry-toolbox-contract` に従い次の見出しを Section 7.4 の直後へ追加する。**12セクションの番号・順序は変えない**
    - `7.5.1 Tool Inventory (TB-CAP-01)` / `7.5.2 Toolbox Decision (TB-CAP-02)` / `7.5.3 Pinning Policy (TB-CAP-03)` / `7.5.4 Search Metadata (TB-CAP-04)` / `7.5.5 Discovery Budget (TB-CAP-05)`
    - **見出しレベルは Section 7.0〜7.4 と同じレベルにする**（子レベルにしない）。子レベルにすると前のセクションの範囲が TB-CAP ブロックを取り込み、判定が壊れる
    - 同 Skill の整合ルール R1〜R10 を自己検査する。TB-CAP-01 の `Total tools` は上記の算出値と一致させる
    - **TB-CAP-04 の Tool 表は、上記で数えた Tool ID を過不足なく 1 行 1 件で列挙する**。欠落・余剰・重複を作らない。`Pinned` 列は **TB-CAP-03 の pin 一覧と一致**させる
    - 中核 Tool（ポリシー・頻用データアクセス）は TB-CAP-03 で pin し、検索に依存させない
    - 未 pin Tool の `additional_search_text` は、語彙が自明なものだけ埋め、残りは `deferred（実測後に追加）` と記す。行自体を省略しない
    - SDK シンボル名はプレビューで変動するため本文へ確定値を埋めず、`Checked at` と SDK パッケージ名を記録する
  - 各AG-CAPが非該当の場合は Contract ID / 理由 / Decision source / 再判定条件を持つN/Aとし、単語だけのN/Aを禁止する
  - Step 1 / 2から引き継いだMutation Intent、Required flag、Request class、owner、MCP、SkillのTBDを解消する。provider固有値を確認できない場合は`Design status: unknown`、確認日、確認した公式根拠、runtime probe、Blocked条件を確定し、値自体は推測しない
  - 完成判定チェック（15項目・後述）を実施する
  - `docs/agent/agent-detail-{key}.md`（`{key}` = `AG-*`、Agent 名はファイル名に含めない）を作成する
- **量が多い場合の分割**: Agent 数が多い場合は Skill task-dag-planning の分割ルールに従い、Agent ごとに Sub Issue に分割する
- **完成判定チェック（15項目・出力前に必ず実施）**:
  1. Missionが1文
  2. Doneが検証可能
  3. 8境界が埋まっている
  4. I/Oスキーマがある
  5. 状態遷移が図で定義
  6. Tool入出力・失敗時が定義
  7. Write/外部送信に承認・監査
  8. 例外/縮退/エスカレーションが決定
  9. 評価（最終＋遷移判断）が定義
  10. Goal Contractのrequired criteriaが決定的に評価可能
  11. Runtime Goal Loopが有限で停止条件を持つ
  12. 検索routeにPreferred / Fallback / Blocked / citationがある
  13. C/U/DがREST Function Toolだけをprimary経路にする
  14. MCP client / Remote adapterの責務が分離される
  15. Agent別Skillのrequired / not-required / TBDが根拠付きで決定される
- **完了判定**: 全 Agent の詳細設計書がある / 各設計書が12セクション全て埋まっている / 上記の完成判定15項目を全てパスしている / AG-CAP-01〜10が確定または理由付きN/Aである / Foundry IQ経路を選んだAgentはAR-CAP-01〜05が揃っている / Tool Search 方針に応じて TB-CAP-01〜05 が揃っている（`auto` は Tool 総数 15 超のとき、`yes` は常時、`no` は TB-CAP-01/02 と理由付き N/A の TB-CAP-03〜05） / Step 1・2由来TBDが残っていない

### 5.2 Agent 一覧の出力
- Step 2 と Step 3 の成果物を元に、`docs/ai-agent-catalog.md` を作成/更新する。
- 出力形式は以下の固定フォーマットに従う：

```markdown
# AI Agent 一覧

## 概要
- ユースケースID: {ユースケースID}
- 生成日: YYYY-MM-DD
- Agent 数: N

## Agent 一覧

| # | Agent ID | Agent Name | 種別 | Mission（1文） | 入力 | 出力 | Tools | Knowledge Source | 詳細設計書 |
|---|----------|------------|------|----------------|------|------|-------|------------------|------------|
| 1 | AGT-XX-01 | ... | Single/Multi | ... | ... | ... | ... | ... | ... | [リンク] |

## アーキテクチャ概要図
（Mermaid図をここに転記）

## 補足
- 設計ガイドライン: .github/prompts/Arch-AIAgentDesign-Step3.prompt.md
- アプリケーション定義: docs/agent/agent-application-definition.md
- アーキテクチャ設計: docs/agent/agent-architecture.md
```

### 5.3 進捗ログ追記（必須）
- `{WORK}ai-agent-design-work-status.md` に追記のみで記録する：
  - `YYYY-MM-DD: 何をした / 何が決まった / 次アクション`

## 6) TIME-BOX / MODE SWITCH（分割ルール）
- Step 5.1 を 1 回の応答で全章を高品質に書き切れない場合は、次のいずれかで分割する：
  - A) 章単位で分割して順に出力する（今回の応答では「章1〜章6」など範囲を明示）
  - B) 先に分割実行用 Prompt を複数作る
- 分割時も、各 Prompt は「どの入力を読むか・どの章を出すか・出力先ファイル」を明示し、単体で実行可能にする。
- Step 全体として Skill task-dag-planning の粒度/コンテキスト分割判定を適用する（詳細は Skill `task-dag-planning` を参照）。
  - 分割時は各 Sub Issue に `## Custom Agent` セクションに `Arch-AIAgentDesign-Step3` を含める

## 7) 書き込み失敗/巨大出力への対策
- まず `large-output-chunking` スキルのルールに従う。
- 設計書が長い場合は見出し境界で分割して追記する。

## 8) 最終品質レビュー（単回インライン・セルフチェック）

### 8.1 事前チェック
- 全 3 Step の設計書が作成されている
- `docs/ai-agent-catalog.md` が存在し、全 Agent が記載されている
- 各 Agent の詳細設計書に System Prompt の雛形が含まれている
- 各設計書の完成判定チェックをパスしている
- 各設計書にAG-CAP-01〜10の固定見出しがあり、理由なしN/Aと上流TBDが残っていない

### 8.2 ドメイン固有観点

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

- **設計の網羅性・整合性**
  - 全ユースケースがカバーされているか
  - Agent 間の境界（データ/権限/SLA）が矛盾していないか
  - 詳細設計の I/O 契約がアーキテクチャ設計と一致しているか
  - AC がすべて満たされているか

- **実装可能性・運用視点**
  - System Prompt が実装に十分な具体性を持っているか
  - Tool/Knowledge Source の定義が実装チームに伝わるレベルか
  - Runtime Goal Loop、検索route、REST CRUD、MCP、Skill loadingが実装可能な契約になっているか
  - エラーハンドリング・エスカレーション方針が明確か
  - 評価計画が実行可能か

- **保守性・拡張性・セキュリティ**
  - Agent 追加時の変更容易性
  - Guardrails（禁止行為/PII/権限分離）が十分か
  - REST mutationがMCP/SQL/direct DBで迂回されず、Tool allowlistとHITLが維持されるか
  - Observability（ログ/メトリクス/監査）が運用可能か
  - ドキュメント保守性と見直し周期の妥当性

### 8.3 反映方法
確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。
