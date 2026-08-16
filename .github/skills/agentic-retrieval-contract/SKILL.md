---
name: agentic-retrieval-contract
description: >
  Foundry IQ / Azure AI Search Agentic Retrieval の Knowledge Base・Knowledge Source・検索予算・証跡・MCP 公開を AR-CAP-01〜05 の固定契約として設計・検証する。 USE FOR: agentic retrieval design, Foundry IQ knowledge base, knowledge source selection, retrieval reasoning effort, multi-source retrieval, subquery budget, knowledge base MCP exposure. DO NOT USE FOR: classic single-query search index tuning, vector index design only, non-search agent capabilities, generic Azure deployment scripting. WHEN: AI Agent または Web アプリの検索経路として Foundry IQ / Azure AI Search Agentic Retrieval を選択したとき。
category: planning
metadata:
  origin: user
  version: 1.0.0
---

# agentic-retrieval-contract

## 目的

Foundry IQ（Azure AI Search の Agentic Retrieval）を採用する Agent / サービスが、**複数データソースの横断**と**クエリ回数・トークン消費の最小化**を、設計・実装・デプロイで同じ契約 ID を使って決定・検証できるようにする。

Agentic Retrieval は「1 リクエストで Knowledge Base が全 Knowledge Source へサブクエリをファンアウトし、統一ランキングでマージする」多クエリパイプラインである。この特性を活かすか殺すかは、本 Skill が定義する 5 契約の設計値で決まる。

## Non-goals（このスキルの範囲外）

- **製品非依存の機能要件詳細への適用** — `docs/services/{serviceId}-agentic-retrieval-spec.md` は Azure 固有名禁止の成果物であり、本 Skill の用語・パラメータ名を書き写してはならない（§製品非依存成果物へのガード）。
- **クラシック検索（単一クエリ）のインデックス設計・チューニング** — Agentic Retrieval を採用しない場合は対象外。
- **ベクトルインデックスの次元・アルゴリズム設計** — 索引側の設計は既存の検索設計に委ねる。
- **Azure リソース作成スクリプトの記法** — `azure-cli-deploy-scripts` の責務。
- **AI Agent の Goal Loop / REST mutation / Skill 梱包** — `ai-agent-capability-contract`（AG-CAP-01〜06）の責務。
- **provider 抽象化層・汎用コネクタ framework の新設** — 要件に根拠がある場合を除いて作らない。
- **SKU / API version / model / region / tier 上限の固定** — 実行時に公式情報で確認する。

## 製品非依存成果物へのガード

本 Skill は Azure 固有の用語とパラメータを扱う。製品非依存を要求される成果物（`docs/services/{serviceId}-agentic-retrieval-spec.md` 等）へは、**本 Skill のパラメータ名・製品名・ SKU ・ API version を转記してはならない**。

製品非依存成果物では、本 Skill の契約を**業務的な問いに変換**して使う。

| 本 Skill の契約 | 製品非依存成果物での問い方 |
|---|---|
| AR-CAP-01 `Retrieval reasoning effort` | 「クエリ拡張をどこまで行うか。レイテンシ・コストと検索深度のどちらを優先するか」 |
| AR-CAP-01 `Index semantic configuration` | 「どの項目を優先して関連度を決めるか。その方針をどこで確定するか」 |
| AR-CAP-02 `Kind` / `Locality` | 「どのデータを事前取り込みし、どのデータを問い合わせ時に取得するか」 |
| AR-CAP-02 の行数下限 | 「この問いに答えるには何種類の情報源を同時に見る必要があるか」 |
| AR-CAP-02 `Always query` | 「常に参照しなければならない情報源はどれか」 |
| AR-CAP-03 | 「1 回の問い合わせにかけられる時間・費用の上限はどれか」 |
| AR-CAP-04 | 「回答にどの出典を付ける必要があるか」 |
| AR-CAP-05 | 「この知識基盤を他システムへ公開する必要があるか」 |

AR-CAP-01〜05 の**固定見出しとパラメータ名を使うのは Azure 実装設計以降**とする。

## 適用手順

1. 検索経路として Foundry IQ / Azure AI Search Agentic Retrieval を選んだことを `ai-agent-capability-contract` の AG-CAP-03 で確定する。
2. 下表に従い、対象フェーズに必要な reference だけを読む。
3. AR-CAP-01〜05 を設計書へ記載する。非該当は理由付き N/A とし、単語だけの N/A は認めない。
4. `§整合ルール` を自己検査してから次フェーズへ渡す。
5. 実行時に確認が必要な値（API version / tier 上限 / region / model）は Microsoft Learn MCP で再確認し、根拠を `cli-evidence.md` へ記録する。

## Progressive Disclosure

| 対象 | 読む reference | 用途 |
|---|---|---|
| 製品非依存の機能要件詳細 | （本 Skill を適用しない） | §製品非依存成果物へのガード の変換表だけを使う |
| Azure 実装設計 | 3 reference すべて | AR-CAP-01〜05 の確定 |
| TDD テスト仕様 / テストコード | `references/retrieval-tuning.md`, `references/mcp-exposure-and-evidence.md` | 予算・引用・allowlist の検証観点 |
| Deploy / AC 検証 | 3 reference すべて | 設計値と実リソース設定の一致確認 |
| AI Agent 実装（AAGD） | `references/mcp-exposure-and-evidence.md` | Tool allowlist と per-user 権限の実装境界 |

## 契約一覧

| ID | 固定見出し | 必須内容 |
|---|---|---|
| AR-CAP-01 | `Knowledge Base Contract` | KB 名・知識ドメイン・query planning LLM・retrieval reasoning effort と選定根拠・output mode・retrieval instructions・索引の semantic configuration・KS 件数 |
| AR-CAP-02 | `Knowledge Source Matrix` | 1 行 1 Knowledge Source（**2 行以上 10 行以下**）。種別・indexed/remote・always query・選択記述・取り込み方式・鮮度・権限境界 |
| AR-CAP-03 | `Retrieval Budget` | 想定サブクエリ本数・retrieval token 予算・LLM token 予算・latency 目標・最大実行時間・超過時の縮退・測定方法 |
| AR-CAP-04 | `Evidence & Observability` | source references / activity log の有効化可否・citation 必須項目・blocked 条件・秘密情報の扱い |
| AR-CAP-05 | `MCP Exposure` | KB の MCP 公開可否・project connection・認証方式・Tool allowlist・per-user 権限伝播の可否 |

見出しは `### Knowledge Base Contract (AR-CAP-01)` のように、**固定見出しで始まり Contract ID を含む**形式にする（後続 validator が識別する）。

### AG-CAP-03 との境界

`ai-agent-capability-contract` の AG-CAP-03 `Knowledge & Structured Data Routing` とは次のとおり分ける。二重記載しない。

| 項目 | 正本 |
|---|---|
| どの Request class でどの経路を使うか（Preferred / Fallback / Blocked） | AG-CAP-03 |
| 経路ごとの Citation requirement（何を引用するか） | AG-CAP-03 |
| 選んだ Foundry IQ 経路を**どう構成するか** | AR-CAP-01〜05 |
| source references / activity log を**有効化するか** | AR-CAP-04 |

AG-CAP-03 で `enterprise-unstructured` の Preferred に Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合に限り、AR-CAP-01〜05 を必須とする。

### 記載形式

- AR-CAP-01 / 03 / 04 / 05: `- ラベル: 値` の定型キー行。
- AR-CAP-02: Markdown 表（1 行 1 Knowledge Source）。
- 全契約: N/A とする場合は `Status: N/A` に加えて `Reason` / `Decision source` / `Recheck condition` を書く。

### 見出しレベル規約（必須）

AR-CAP の 5 見出しは、**それを内包する親セクションと同じ見出しレベル**にし、番号で従属関係を表す。

- 良い例: 親が `#### 7.0 Knowledge & Structured Data Routing（AG-CAP-03）` なら `#### 7.0.1 Knowledge Base Contract（AR-CAP-01）`
- 悪い例: 親が `####` で AR-CAP を `#####` にする

理由: validator はセクションを「次の同レベル以上の見出し」までで区切る。AR-CAP を子レベルにすると親セクションの範囲が AR-CAP ブロックを取り込み、親側の `Status` を誤読して **N/A と誤判定する**。

## 整合ルール（自己検査必須）

Microsoft Learn 確認日 2026-08-04。tier 上限・region・API version は実行時に再確認する。

| # | ルール | 根拠 |
|---|---|---|
| R1 | `Retrieval reasoning effort` は `minimal` / `low` / `medium` のいずれか。未記載は既定 `low` として扱わず FAIL | reasoning effort levels |
| R2 | `minimal` のとき `Output mode` は `extractiveData` でなければならない | minimal の Limits |
| R3 | `minimal` のとき answer synthesis と web knowledge source を選択してはならない（AR-CAP-02 に web 種別の行を置かない） | minimal の Limits |
| R4 | `minimal` のとき AR-CAP-02 の `Always query` は検索挙動へ影響しない。全 KS が常に検索される前提で予算を積む | minimal の Description |
| R5 | AR-CAP-02 の行数は 10 以下。上限は tier 依存のため実行時に再確認する | KB あたりの KS 上限 |
| R6 | `low` / `medium` のとき、全 KS 行に `Selection description` が必要（LLM の KS 選択根拠になる） | KS 選択の 3 要因 |
| R7 | `medium` を選ぶ場合、対象 region で利用可能であることを確認した記録が必要 | medium は select regions 限定 |
| R8 | AR-CAP-03 の token 予算・latency 目標・最大実行時間は有限値。`無制限` / `unlimited` は FAIL | 課金が token 単位 |
| R9 | `Retrieval reasoning effort` の正本は AR-CAP-01 のみ。AR-CAP-03 に別値を重複記載してはならない | 契約の単一情報源原則 |
| R10 | AR-CAP-05 で Foundry Agent Service へ**直結**する場合、`Tool allowlist` は `knowledge_base_retrieve` だけにする。Toolbox 経由の場合は適用しない（下記参照） | Foundry Agent Service がサポートする唯一の tool |
| R11 | per-user 権限が必須で、対象 runtime が per-request header を伝播できない場合は blocked にする。application 権限へ置換しない | Foundry Agent Service は preview 時点で MCP tool の per-request header 非対応 |
| R12 | `Checked at` は `YYYY-MM-DD`。設計時の提供状態と実行時の可用性を同一視しない | availability の記録原則 |
| R13 | AR-CAP-05 に `Connection topology` を記載する。`direct-kb` / `via-toolbox` のいずれか | R10 の適用範囲を確定するため |
| R14 | AR-CAP-02 の行数は **2 以上**。1 行だけの Knowledge Base はファンアウト先が 1 つしかなく、クラシックな単一クエリ検索と等価になる。横断が不要なら Agentic Retrieval を採用せず AG-CAP-03 で別経路を選ぶ | 1 リクエストで全 KS へファンアウトするパイプラインであること |
| R15 | AR-CAP-01 に `Index semantic configuration` を記載する。各サブクエリは semantic rerank を通るため、索引側の構成が検索品質の上限を決める。確定できない場合も確認予定と手段を書き、単語だけの `TBD` は FAIL | semantic configuration は Agentic Retrieval の索引で必須 |

### 接続トポロジと R10 の適用範囲

Knowledge Base の公開には 2 経路があり、**Tool 制約が異なる**。

| `Connection topology` | 接続先 | Tool 制約 |
|---|---|---|
| `direct-kb` | Knowledge Base 自身の MCP エンドポイント<br>`{search_endpoint}/knowledgebases/{kb}/mcp` | `knowledge_base_retrieve` のみ（**R10 適用**） |
| `via-toolbox` | Toolbox の MCP エンドポイント | KB を含む複数 Tool を同居可（**R10 非適用**） |

Toolbox は「Web Search / Code Interpreter / File Search / Azure AI Search / MCP servers / OpenAPI tools /
Agent-to-Agent connections を単一の MCP 互換エンドポイントへ束ねる」ものであり、
Knowledge Base を Toolbox へ載せる公式手順が存在する
（Learn「Quickstart: Add a Foundry IQ knowledge base to a hosted agent with a toolbox」）。

`via-toolbox` を選ぶ場合は `foundry-toolbox-contract`（TB-CAP-01〜05）を併用する。

## 入出力例

### 例1: 社内文書と Web を横断し、引用付きで回答する Agent

**入力:** 社内ポリシー文書（Blob）と公開 Web の最新情報を根拠付きで回答する。

**出力（要点）:**

- AR-CAP-01: `Retrieval reasoning effort: low` / `Output mode: answerSynthesis` / `Retrieval instructions` に「社内ポリシーを優先し、Web は日付が要求されたときだけ使う」。
- AR-CAP-02: 2 行（Blob = indexed / `Always query: true`、Web = remote / `Always query: false`）。
- AR-CAP-03: 想定サブクエリ本数と token 予算、p95 latency、超過時は Web を落として社内文書のみで partial success。
- AR-CAP-04: source references 有効、activity log 有効、citation は source 種別 / 識別子 / path or URL / 取得日時。
- AR-CAP-05: Foundry Agent Service へ `knowledge_base_retrieve` のみ許可。

### 例2: 既存検索 API からの移行で、クエリ計画を自前で持つ

**入力:** 既存の単一クエリ検索を置き換えるが、クエリ生成はアプリ側で行う。

**出力（要点）:**

- AR-CAP-01: `Retrieval reasoning effort: minimal` / `Output mode: extractiveData`（R2）。`Query planning LLM: none`。
- AR-CAP-02: web 種別を置かない（R3）。全 KS が常に検索される前提（R4）。
- AR-CAP-03: LLM token 予算 0、retrieval token 予算のみ。
- AR-CAP-04: activity log は取得可否を確認して記録。
- AR-CAP-05: MCP 公開しないなら理由付き N/A。

## 検証

| フェーズ | 検証内容 |
|---|---|
| 設計 | AR-CAP-01〜05 の存在、理由付き N/A、R1〜R12 の整合 |
| テスト仕様 | 各契約に対する正常・境界・失敗ケース（例: KS 全滅時の blocked、token 予算超過時の縮退） |
| 実装 | reasoning effort / KB 名 / KS 一覧が設定から読まれ、ハードコードされていない |
| Deploy | 実 KB / KS の設定値が設計値と一致し、非破壊 smoke retrieve が複数 KS 由来の reference を返す |

## 公式根拠

確認日: 2026-08-04。値（API version / tier 上限 / region / model）は本 Skill で固定しない。

| タイトル | URL | 本 Skill で確認した事項 |
|---|---|---|
| Agentic retrieval in Azure AI Search | https://learn.microsoft.com/azure/search/agentic-retrieval-overview | パイプライン（query planning → subquery → 並列実行 → semantic rerank → マージ）、token 課金、コスト低減策 |
| Set the retrieval reasoning effort (preview) | https://learn.microsoft.com/azure/search/agentic-retrieval-how-to-set-retrieval-reasoning-effort | `minimal` / `low` / `medium` の挙動と Limits、`retrievalReasoningEffort` の設定箇所、medium の region 制約 |
| What is a knowledge source? | https://learn.microsoft.com/azure/search/agentic-knowledge-source-overview | KS 種別（indexed / remote）、`alwaysQuery`、`retrievalInstructions`、KS 選択の 3 要因、統一ランキング |
| Connect a Foundry IQ knowledge base to Foundry Agent Service | https://learn.microsoft.com/azure/foundry/agents/how-to/foundry-iq-connect | `RemoteTool` + `ProjectManagedIdentity` 接続、`knowledge_base_retrieve` が唯一の対応 tool、per-request header 非対応 |
| Foundry IQ | https://learn.microsoft.com/azure/foundry/agents/concepts/what-is-foundry-iq | Foundry IQ が Azure AI Search を基盤とする managed knowledge layer である位置づけ |

## Related Skills

| Skill | 関係 | 用途 |
|---|---|---|
| `ai-agent-capability-contract` | 先行 | AG-CAP-03 で本 Skill を使う経路を選択する |
| `azure-cli-deploy-scripts` | 後続 | KB / KS を作成する冪等スクリプトの記法 |
| `azure-ac-verification` | 後続 | Deploy 後の AC 検証記法 |
| `mcp-server-design` | 補完 | Remote MCP の責務分離（AR-CAP-05 と併用） |
| `foundry-toolbox-contract` | 補完 | `Connection topology: via-toolbox` を選んだ場合の TB-CAP-01〜05 |
| `test-strategy-template` | 依存 | AR-CAP 別テストの戦略 |
