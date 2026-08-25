---
name: foundry-toolbox-contract
description: >
  Microsoft Foundry Toolbox と tool search による Tool 集約・遅延公開を TB-CAP-01〜05 の固定契約として設計・検証する。 USE FOR: tool inventory count, toolbox decision, tool search enablement, tool pinning, additional search text, tool discovery budget, large tool catalog. DO NOT USE FOR: individual REST tool schema design, MCP server implementation, knowledge base retrieval tuning, agent goal loop design. WHEN: AI Agent の Tool 総数が 10〜15 個を超えるとき、または 1 つの Agent が複数ワークフローを担うとき。
category: planning
metadata:
  origin: user
  version: 1.0.0
---

# foundry-toolbox-contract

## 目的

Tool 数が増えた Agent が、**全 Tool 定義を毎ターン渡す**ことによるトークン浪費と Tool 選択精度低下を避けられるようにする。

Foundry Toolbox の tool search は、初回の `tools/list` から全 Tool を隠し、`tool_search` と `call_tool` の 2 つの meta-tool だけを公開する。モデルは必要な能力を自然言語で述べ、該当 Tool 定義だけを受け取ってから呼び出す。

本 Skill は「いつ有効化するか」「何を pin するか」「検索に何を載せるか」を、設計・実装・デプロイで同じ契約 ID を使って決定・検証できるようにする。

## Non-goals（このスキルの範囲外）

- **個々の REST Tool の I/O スキーマ設計** — `ai-agent-capability-contract` の AG-CAP-04 の責務。
- **MCP Server 自体の実装** — `mcp-server-design` の責務。
- **Knowledge Base の検索チューニング** — `agentic-retrieval-contract`（AR-CAP-01〜05）の責務。
- **Agent の Goal Loop / Skill 梱包** — `ai-agent-capability-contract`（AG-CAP-01 / 06）の責務。
- **Tool を減らすための機能統合** — AG-CAP-03 は検索 Tool の統合を明示的に禁止している。本 Skill は「統合せずに増えた Tool を扱う」ための契約であり、統合を推奨しない。
- **SDK シンボル名・API version の固定** — プレビュー中で変動するため実行時に確認する（§既知の不確実性）。
- **検索ランキングアルゴリズムの独自実装** — Foundry の BM25 に委ねる。

## 製品非依存成果物へのガード

本 Skill は Azure / Foundry 固有の用語を扱う。製品非依存を要求される成果物へは、**パラメータ名・製品名を転記してはならない**。

| 本 Skill の契約 | 製品非依存成果物での問い方 |
|---|---|
| TB-CAP-01 | 「この Agent が扱う操作は何種類あるか」 |
| TB-CAP-02 | 「利用可能な操作の一覧を毎回すべて提示するか、必要なものだけ探して提示するか」 |
| TB-CAP-03 | 「常に即座に使える必要がある操作はどれか」 |
| TB-CAP-04 | 「利用者はその操作をどんな言葉で呼ぶか」 |
| TB-CAP-05 | 「1 回の依頼で操作を探す回数の上限はどれか」 |

## 適用手順

1. AG-CAP-03 / 04 / 05 を確定させ、Tool 総数を数えられる状態にする。
2. TB-CAP-01 に Tool 総数と内訳を**実数**で記載する。
3. §判定基準 に従い TB-CAP-02 で Toolbox / tool search の採否を決める。
4. tool search を有効にする場合のみ TB-CAP-03〜05 を記載する。無効なら理由付き N/A。
5. §整合ルール を自己検査してから次フェーズへ渡す。
6. SDK シンボル名・API version は Microsoft Learn MCP で確認し、根拠を `cli-evidence.md` へ記録する。

## Progressive Disclosure

| 対象 | 読む reference | 用途 |
|---|---|---|
| Tool 数の算出と採否判定 | （本ファイルのみ） | TB-CAP-01 / 02 |
| pin と検索メタデータの設計 | `references/pinning-and-search-metadata.md` | TB-CAP-03 / 04 |
| 実装・デプロイ・実測 | `references/toolbox-implementation.md` | TB-CAP-05 と検証 |

## 判定基準（Tool 数）

Microsoft Learn と Foundry 開発チームのブログが**独立に同じ閾値**を示している。

| 出典 | 記述 |
|---|---|
| Microsoft Learn `tool-search` | 「Use tool search when: Your toolbox has more than **10–15 tools**」 |
| Command Line ブログ（2026-07-29） | 「If your toolbox has more than **10–15 tools** ... tool search is worth testing」 |

### 実測されたトークン削減（ToolRet ベンチマーク: 44,000+ tools / 7,000 queries）

| Tool 数 | 削減率 |
|---|---|
| 50 | 60% 超 |
| 1,000 | 97% 超 |

prompt caching を有効にしたベースラインとの比較である。キャッシュ済みトークンは通常入力の約 90% 安いだけで無料ではなく、かつモデルの注意を奪う。

### 判定表

| Tool 総数 | 判定 |
|---|---|
| 〜10 | tool search 不要。理由を TB-CAP-02 に記載 |
| 11〜15 | 任意。異なるタスクが異なる Tool 部分集合を使うなら有効化を推奨 |
| 16〜 | **有効化を既定とする**。無効にする場合は TB-CAP-02 に理由必須 |

### 有効化が向かないケース（公式明記）

- ほぼ常に同じ数個の Tool しか使わない Agent
- description が曖昧すぎて改善の余地がない catalog

> 「Search is for the long tail. It is not a good default for tools the model constantly needs.」
> 中核 Tool は TB-CAP-03 で pin し、検索に依存させない。

## 契約一覧

| ID | 固定見出し | 必須内容 |
|---|---|---|
| TB-CAP-01 | `Tool Inventory` | Tool 総数（実数）・内訳（REST / MCP / 検索ルート / 組み込み）・算出根拠 |
| TB-CAP-02 | `Toolbox Decision` | Toolbox 採否・tool search 有効/無効・判定に用いた Tool 数と閾値・接続トポロジ |
| TB-CAP-03 | `Pinning Policy` | pin する Tool と理由・pin しない long tail の範囲 |
| TB-CAP-04 | `Search Metadata` | 1 行 1 Tool。`additional_search_text` と想定ユーザー語彙 |
| TB-CAP-05 | `Discovery Budget` | `limit` 値・1 ターンあたりの想定 `tool_search` 回数・超過時の挙動 |

### 記載形式

- TB-CAP-01 / 02 / 03 / 05: `- ラベル: 値` の定型キー行。
- TB-CAP-04: Markdown 表（1 行 1 Tool）。**列名は次の 3 つを必ず含める**（validator が識別する）。

  | 列名 | 内容 |
  |---|---|
  | `Tool ID` | AG-CAP-04 / AG-CAP-05 と同じ Tool 名 |
  | `Pinned` | `yes` / `no` |
  | `Additional search text` | 検索専用の語彙。未 pin なら必須（初回は `deferred（実測後に追加）` 可） |

  補足列（`想定ユーザー語彙` 等）は自由に追加してよい。

- TB-CAP-01 の必須キー行: `Total tools` / `REST tools` / `MCP allowlist tools` / `Distinct search routes` / `Counting source` / `Checked at`
- TB-CAP-02 の必須キー行: `Tool search` / `Connection topology`（`disabled` かつ 16 Tool 以上なら `Reason` も）
- TB-CAP-03 の必須キー行: `Pinned tools` / `Wildcard pin`
- TB-CAP-05 の必須キー行: `limit` / `Expected tool_search calls per turn` / `Overflow behavior`
- 全契約: N/A とする場合は `Status: N/A` に加えて `Reason` / `Decision source` / `Recheck condition` を書く。

### 見出しレベル規約（必須）

TB-CAP の 5 見出しは、**それを内包する親セクションと同じ見出しレベル**にし、番号で従属関係を表す。

- 良い例: 親が `#### 7.5 Toolbox & Tool Discovery` なら `#### 7.5.1 Tool Inventory（TB-CAP-01）`
- 悪い例: 親が `####` で TB-CAP を `#####` にする

理由: validator はセクションを「次の同レベル以上の見出し」までで区切る。子レベルにすると親セクションが TB-CAP ブロックを取り込み、親側の `Status` を誤読して **N/A と誤判定する**。

### AG-CAP との境界

| 項目 | 正本 |
|---|---|
| 個々の Tool の I/O スキーマ・冪等性・承認 | AG-CAP-04 |
| MCP Server 単位の allowlist・認証・失敗挙動 | AG-CAP-05 |
| どの Request class でどの検索経路を使うか | AG-CAP-03 |
| Tool を**まとめて公開するか、探させるか** | TB-CAP-02 |
| どの Tool を常時見せるか | TB-CAP-03 |

TB-CAP は AG-CAP の Tool 定義を**再掲しない**。総数と公開方式だけを扱う。

### AR-CAP-05 との境界（接続トポロジ）

Knowledge Base の公開には 2 つの経路があり、**Tool 制約が異なる**。

| 経路 | 接続先 | Tool 制約 |
|---|---|---|
| 直結 | Knowledge Base 自身の MCP エンドポイント | `knowledge_base_retrieve` のみ（Foundry Agent Service の制約） |
| Toolbox 経由 | Toolbox の MCP エンドポイント | KB を含む複数 Tool を同居可。tool search / pin が使える |

Toolbox は「Web Search / Code Interpreter / File Search / Azure AI Search / MCP servers / OpenAPI tools / Agent-to-Agent connections を単一の MCP 互換エンドポイントへ束ねる」ものであり、Knowledge Base を載せる公式手順が存在する。

**したがって AR-CAP-05 の単一 Tool 制約は直結経路にのみ適用する。** TB-CAP-02 の `Connection topology` で経路を明示すること。

## 整合ルール（自己検査必須）

Microsoft Learn 確認日 2026-08-04。プレビュー中のため SDK シンボル名・上限は実行時に再確認する。

| # | ルール | 根拠 |
|---|---|---|
| R1 | TB-CAP-01 の Tool 総数は「AG-CAP-04 の `Required: yes` 行数 + AG-CAP-05 の allowlist Tool 数 + AG-CAP-03 の**異なる**検索経路数」と一致する。内訳の合計が総数と合わない場合は FAIL | 総数の単一情報源原則 |
| R2 | Tool 総数が 16 以上のとき TB-CAP-02 の `Tool search` は `enabled`。`disabled` にする場合は `Reason` 必須 | 10〜15 を超えたら推奨（Learn / ブログ一致） |
| R3 | TB-CAP-05 の `limit` は 1〜10 の整数。既定は 5 | `limit` は既定 5・最大 10 |
| R4 | TB-CAP-03 で**手動 pin** した Tool は TB-CAP-04 の `additional_search_text` 記載を免除する。プラットフォームの自動 pin は免除根拠にならない | 自動 pin は warmup 前に検索経由で発見されるため |
| R5 | 未 pin Tool は TB-CAP-04 に `additional_search_text` を記載する。初回設計に限り `deferred` を許容するが、TB-CAP-05 の実測で検索にヒットしなかった Tool は次イテレーションで必須化する。空欄（記載なし）は FAIL | 調整でヒット率 +約56%。ただし公式指針は「外れたケースを見てから編集する」反復型 |
| R6 | `"*"` による全 Tool pin は tool search 無効化と等価。TB-CAP-02 が `enabled` のとき `"*"` pin を置いてはならない | 全 pin すると `tools/list` に全 Tool が出る |
| R7 | TB-CAP-02 に `Connection topology` を記載する。`direct-kb` の場合、AR-CAP-05 の単一 Tool 制約が適用される | §AR-CAP-05 との境界 |
| R8 | TB-CAP-03 に pin する Tool を最低 1 つ挙げるか、`なし` とした理由を書く。空欄は FAIL | 中核 Tool を検索に依存させると prompt cache が不安定になる |
| R9 | `Checked at` は `YYYY-MM-DD`。SDK パッケージ名と version を併記する | プレビュー（`Foundry-Features: Toolboxes=V1Preview`）で API が変動する |
| R10 | TB-CAP-04 の `additional_search_text` に、モデルへ見せたい説明を書かない。検索専用テキストでありモデルには渡らない | search-only field |

### R1 の数え方（二重計上の禁止）

AG-CAP-03 は 1 行 1 Request class であり、**同じ検索経路が複数行に現れる**。
行数ではなく**経路の異なり数**を数えること。

例: `Preferred: Foundry IQ` が 3 行、`Fallback: Foundry IQ` が 2 行あっても、
Foundry IQ は Tool として **1** と数える。

### R5 の運用（初回は deferred を許容する理由）

公式指針は「最初のチューニングはアルゴリズムではなく編集作業。外れたケースを見てから直す」である。
未 pin Tool が数十個ある設計で、全件の語彙を事前に推測して埋めるのは根拠のない作業になる。

- 初回設計: `deferred（TB-CAP-05 の実測後に追加）` を許容する。
- 実測後: 検索でヒットしなかった Tool は `additional_search_text` を**必須**とする。
- 記載自体が無い（列も行も存在しない）場合は初回でも FAIL。

## 既知の不確実性（実装時に必ず確認）

| 項目 | 状況 |
|---|---|
| SDK シンボル名 | ブログは `ToolboxSearchToolboxTool` / `client.toolboxes.create_version`、Learn は `ToolSearchToolboxTool` / `client.beta.toolboxes.create_version` と**不一致**。実装時に Learn MCP と package manager で確定する |
| GA 時期・課金 | プレビュー。`Foundry-Features: Toolboxes=V1Preview` ヘッダーが必要 |
| 自動 pin の warmup 期間 | 「warmup period」「stale entries aging out」とのみ記載。具体値は未公開 |
| 自社カタログでの削減率 | ブログの 60〜97% は ToolRet ベンチマーク値。Tool 記述の品質に依存するため**実測で確認する**（推定値で語らない） |

## 検証

- TB-CAP-01 の内訳合計 = 総数 であることを算術確認する。
- TB-CAP-02 の判定が §判定基準 の表と一致することを確認する。
- pin / `additional_search_text` の記載漏れを R4 / R5 で相互チェックする。
- 実測比較（tool search on/off）を行った場合、初期 `tools/list` トークン数・Tool 選択正解率・`tool_search` 呼び出し回数・追加レイテンシを記録する。

## 公式根拠

- Microsoft Learn「Enable tool search in a toolbox」 <https://learn.microsoft.com/azure/foundry/agents/how-to/tools/tool-search>
- Microsoft Learn「What is Toolbox in Foundry?」 <https://learn.microsoft.com/azure/foundry/agents/concepts/toolbox-overview>
- Microsoft Learn「Curate intent-based toolbox in Foundry」 <https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox>
- Command Line「Tool search: Finding the right tool at the right time」（2026-07-29） <https://commandline.microsoft.com/tool-search-toolboxes-foundry/>
- ToolRet ベンチマーク <https://arxiv.org/abs/2503.01763>

## Related Skills

- `ai-agent-capability-contract` — AG-CAP-01〜10。個々の Tool 定義の正本。
- `agentic-retrieval-contract` — AR-CAP-01〜05。Knowledge Base の検索設計。接続トポロジで境界を分ける。
- `mcp-server-design` — MCP Server 自体の設計。
