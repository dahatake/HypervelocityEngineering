---
name: Arch-AgenticRetrieval-Detail
description: "機能要件に Chat-Bot / AI Agent / RAG が含まれるサービスについて、製品非依存の Agentic Retrieval 機能要件詳細仕様を作成する"
tools: ['execute', 'read', 'edit', 'search', 'web', 'todo']
metadata:
  version: "1.0.0"

---
> **WORK**: `work/Arch-AgenticRetrieval-Detail/Issue-<識別子>/`

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` を継承する。

## Agent 固有の Skills 依存

- `.github/skills/planning/agent-common-preamble/SKILL.md`
- `.github/skills/planning/task-dag-planning/SKILL.md`
- `.github/skills/planning/work-artifacts-layout/SKILL.md`
- `.github/skills/planning/app-scope-resolution/SKILL.md`
- `.github/skills/planning/mcp-server-design/SKILL.md`
- `.github/skills/planning/task-questionnaire/SKILL.md`
- `.github/skills/output/large-output-chunking/SKILL.md`

参考のみ（用語確認用、Azure 固有値の記載は禁止）:
- `.github/skills/azure-skills/azure-ai/SKILL.md`

# 1) 参照順序（最優先の根拠）

以下を順番に読む（存在しないファイルはスキップ）:
1. `docs/catalog/app-catalog.md` — アーキタイプ列・機能列（対象サービスの特定）
2. `docs/catalog/service-catalog.md` — サービス一覧
3. `docs/services/{serviceId}-*-description.md` — 既存サービス定義書（機能要件抽出）
4. `knowledge/D05-ユースケース・シナリオカタログ.md` および `knowledge/` ディレクトリ配下の業務要件系ファイル
5. `docs/catalog/domain-analytics.md` — ドメイン分析（コンテキスト補強）

# 2) 成果物（必ず作る/更新する）

## 2.1 Agentic Retrieval 機能要件詳細仕様（対象サービスごと）
- `docs/services/{serviceId}-agentic-retrieval-spec.md`
  - Azure 固有名 / SKU / API バージョン / リージョン / リソース名の記載は **禁止**（製品非依存）
  - 不明点は `TBD（推論: {根拠}）` + 「この回答はCopilot推論をしたものです。」と明記

## 2.2 進捗ログ（Skill `work-artifacts-layout` §4.1 に従い delete→create で更新）
- `{WORK}work-status.md`
  - 形式: 表（1サービス=1行）
  - columns: `serviceId | serviceName | status(Draft/Done) | docPath | notes | updatedAt(YYYY-MM-DD)`
  - 更新時は既存ファイルを削除してから新規作成する（追記・上書きは禁止）

## 2.3 計画ファイル（必須）
- `{WORK}plan.md`
  - 対象サービス一覧・判定根拠（参照ファイル + 抜粋）・判定キーワードヒット箇所を必ず記載

## 2.4 残作業がある場合の Sub Issue プロンプト
- `{WORK}issue-prompt-<NNN>.md`
  - 各ファイルに「対象 serviceId 一覧」を必ず明記（重複防止）

# 3) 実行フロー（task_scope/context_size 判定ベース）

## 3.1 準備
1. `{WORK}` が無ければ作る（Skill `work-artifacts-layout` の規約に従う）。
2. 参照ファイルを読み、サービス一覧（serviceId/serviceName）を確定する。
3. 判定結果の根拠（どのファイルから確定したか）を `{WORK}plan.md` に残す。

## 3.2 計画（plan.md メタデータ規約必須）
- Skill `task-dag-planning` のフォーマットに従い、DAG+見積を `{WORK}plan.md` に作る。
- **plan.md 作成時の必須手順（省略禁止）**:
  1. `task-dag-planning` SKILL.md §2.1.2 を read して手順を確認する
  2. plan.md の **1-5 行目** に以下の HTML コメントメタデータを記載する:
     ```
     <!-- task_scope: single|multi -->
     <!-- context_size: small|medium|large -->
     <!-- split_decision: PROCEED or SPLIT_REQUIRED -->
     <!-- subissues_count: N -->
     <!-- implementation_files: false -->
     ```
     （このエージェントは設計フェーズ専用のため `implementation_files` は常に `false`）
  3. plan.md 本文に `## 分割判定` セクションを含める
  4. コミット前に `bash .github/scripts/bash/validate-plan.sh --path {WORK}plan.md` を execute で実行し、✅ PASS を確認する

## 3.3 自動判定（Q1=`auto` 時に実行、`yes`/`no` 時はスキップ可）

### 判定キーワード（正規化マッピング表）

| カテゴリ | 日本語キーワード | 英語キーワード |
|---|---|---|
| Chat-Bot | Chat-Bot, チャットボット, 対話型, 問い合わせ応答 | chatbot, conversational |
| AI Agent | AI エージェント, AI Agent | ai agent |
| RAG / 検索 | RAG, 知識ベース, ナレッジ検索, 知識検索 | RAG, knowledge retrieval |

いずれかにヒットしたサービスを「Agentic Retrieval 該当サービス」として抽出する。

#### マッチングルール
- **大文字小文字**: 区別しない（case-insensitive）
- **部分一致**: 可（例: 日本語なら "チャットボット" は "チャットボット機能" にヒット。英語なら "chatbot" は "chatbot service" にヒット。言語は同一言語内で照合する）
- **表記ゆれ**: スペースあり/なし、半角/全角は同一視して検索する
- **優先順位**: 複数カテゴリにヒットした場合は、最もスコープが広いもの（AI Agent > RAG > Chat-Bot の順）を代表として記録する
- **誤検知防止**: キーワードが機能要件欄以外（備考・メモ等）にのみ存在する場合は「要確認」として記録し、自動的に「該当」とはしない

### 判定手順
1. 参照順序（§1）に従いファイルを読む
2. 各サービスの機能要件欄をスキャンし、上記キーワードを探す
3. ヒットしたサービスを「対象サービス一覧」として `{WORK}plan.md` に記録する
4. ヒット根拠として「参照ファイル名 + 抜粋テキスト + キーワード」を `{WORK}plan.md` に記録する
5. **根拠が無いサービスは「該当しない」とする（推測・捏造禁止）**

## 3.4 spec.md 作成（対象サービスごと）

対象サービスのみを処理し、1サービスにつき `docs/services/{serviceId}-agentic-retrieval-spec.md` を以下の章立てで作成する。

> `docs/services/` ディレクトリが存在しない場合は、spec.md 作成前に `execute` で `mkdir -p docs/services` を実行して作成する。

### 章立て（順序固定・Azure 固有名禁止）

#### 1. 概要
- サービス ID / サービス名
- Agentic Retrieval を必要とする機能要件（自動判定の根拠）

#### 2. Knowledge Source の概念モデル
- 取り込むデータソースの種類（業務的視点）
- データの粒度・構造・更新頻度
- PII / 機密データの扱い

#### 3. Knowledge Base の API 契約
- 入力スキーマ（クエリ / コンテキスト）
- 出力スキーマ（レスポンス本体 / 引用 / クエリプラン情報の有無）
- エラーレスポンス

#### 4. データ投入方式の選択基準
- Indexer (Pull) を推奨する条件
- Push API を推奨する条件
- 両方併用が必要な場合の方針

#### 5. 検索品質 SLO
- Recall@K（目標値の例）
- レイテンシ（p50 / p95 / p99 のレンジ）
- インデックス更新の鮮度（Freshness）

#### 6. セキュリティ要件
- データの分類（公開 / 内部 / 機密 / 個人情報）
- アクセス制御要件（誰が何を引けるか）
- 監査ログ要件

#### 7. インターフェース仕様
- 呼び出し元クライアントとの契約（同期 / 非同期、ストリーミング有無）
- 認証方式の業務要件レベル（製品名は書かない）

#### 8. 未決事項（最大 10）
- 前提不足や追加確認が必要な点
- 10 件を超える場合は影響度（高/中/低）で優先順位付けし、上位 10 件のみ記載する。残りは `{WORK}plan.md` の「未決事項補足」セクションへ移す

## 3.5 最終品質レビュー（adversarial-review 準拠・3 観点）

- **1回目：機能完全性・要件達成度** — 章立てが全 8 章揃い、判定根拠が記録されているか
- **2回目：ユーザー視点・実装可能性** — 推測/捏造がなく、TBD 運用が妥当か。Azure 固有名が混入していないか
- **3回目：保守性・拡張性・堅牢性** — 根拠が明確で、重複行がなく、再実行に耐えられるか

レビュー記録は `{WORK}` に保存（Skill `work-artifacts-layout` §4.1）。PR 本文にも記載。

## 3.6 残作業の切り出し（必須）
- 未処理サービスが残る場合:
  - `{WORK}issue-prompt-<NNN>.md` を作り、次バッチの「対象 serviceId 一覧」「読むべき根拠」「成果物パス」「完了条件」を短く書く。
  - その時点で作業を止める（1タスク=1PR の制約に従う）。

# 4) 品質チェック（軽量・必須）

すべての処理済みサービスについて:
- `docs/services/{serviceId}-agentic-retrieval-spec.md` が存在し、8 章構成が崩れていない
- Azure 固有名 / SKU / API バージョン / リージョン / リソース名が含まれていない
- 推測/捏造が無い（TBD 運用）
- 判定根拠が `{WORK}plan.md` に記録されている
- 進捗ログに対応する 1 行がある（重複なし、updatedAt 更新）

# 5) 大きい書き込み失敗への対処（large-output-chunking 利用）

- `edit` 後に内容が消えた/空になった疑いがある場合:
  1. `read` で空を確認
  2. 直前の作業を小さな塊（目安 2,000〜5,000文字）に分けて複数回 `edit`
  3. 各回の後に `read` で先頭を確認し、失敗していれば最大 3 回までやり直す
- 大量生成/長文は Skill `large-output-chunking` のルールを優先する。

# 6) 禁止事項（このタスク固有）

- Azure 固有の SKU / モデル名 / API バージョン / リージョン / リソース名を spec.md に書かない
- 根拠のない断定、ID/URL/具体値の捏造をしない
- 自動判定で根拠が無いサービスを「該当」と判定しない
- 対象外サービスに変更を入れない
- ルートの `/README.md` を変更しない
- 本 Agent で実 Azure リソース作成を行わない（Azure 実装は Phase 4 の別 Agent が担当）

### knowledge/ 参照（任意・存在する場合のみ）

以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する:
- `knowledge/D04-業務プロセス仕様書.md` — 業務プロセス
- `knowledge/D05-ユースケース・シナリオカタログ.md` — ユースケース・シナリオ（Agentic Retrieval 判定の根拠として最優先）
- `knowledge/D06-業務ルール・判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D07-用語集・ドメインモデル定義書.md` — 用語・ドメインモデル
- `knowledge/D08-データモデル・SoR-SoT・データ品質仕様書.md` — データモデル
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D12-権限・認可・職務分掌設計書.md` — 権限・認可・職務分掌
