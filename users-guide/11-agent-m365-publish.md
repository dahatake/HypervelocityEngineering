# AI Agent の配布 — Agent Plugin と Microsoft 365 / Teams 公開

← [README](../README.md)

---

## 目次

- [対象読者・前提](#対象読者前提)
- [なぜ配布が契約になっているのか](#なぜ配布が契約になっているのか)
- [2 つの配布チャネル](#2-つの配布チャネル)
- [Agent Plugin チャネル（plugin.json / mcp.json）](#agent-plugin-チャネルpluginjson--mcpjson)
- [Microsoft 365 / Teams チャネル（AAGD Step.7）](#microsoft-365--teams-チャネルaagd-step7)
- [よくある誤り](#よくある誤り)

---

## 対象読者・前提

- 対象読者: AAGD で AI Agent をデプロイした担当者
- 前提: AAGD Step.3（Deploy）が完了していること
- 関連: [08-ai-agent.md](./08-ai-agent.md) / [plugin-mcp-auth.md](./plugin-mcp-auth.md) / 前の Step.6 は [10-agent-evaluation.md](./10-agent-evaluation.md)

## なぜ配布が契約になっているのか

Agent を Foundry へデプロイしただけでは、利用者のチャットクライアントからは呼べません。
AG-CAP-09 `Distribution & Packaging` は、この
「**実装したが呼び出せない**」状態を防ぐための契約です。

配布物の生成は AAGD Step.2.3（実装）、実際の公開は AAGD Step.7 が担当します。

## 2 つの配布チャネル

| チャネル | 生成物 | 担当 Step | 呼び出し元 |
|---|---|---|---|
| Agent Plugins | `plugin.json` / `skills/` / `mcp.json` | Step.2.3 | 仕様対応クライアント（GitHub Copilot、Claude 等） |
| Microsoft 365 / Teams | Bot 登録・公開設定 | Step.7 | Microsoft 365 Copilot Chat / Teams |

どちらを採るかは詳細設計書 Section 7.8 の `Channels` が正本です。
両方採らない場合だけ AG-CAP-09 全体を理由付き N/A にできます。
その場合も「利用者がこの Agent をどう呼ぶのか」を記録します。

## Agent Plugin チャネル（`plugin.json` / `mcp.json`）

### `plugin.json`（常に生成）

`src/agent/{key}/plugin.json` は Agent Plugins Specification 1.0.0 の
plugin root マニフェストです。これが無いと、仕様対応クライアントは
コンポーネントを一切 discover できません。

- `$schema` は `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json` 固定
- `name` は fan-out キーの **小文字化**（`AG-01` → `ag-01`）
- top-level は **closed schema**。HVE 固有の設定（`max_iterations` 等）を足せません

ランタイム設定は従来どおり `agent-config.json` / `appsettings.json` に置き、
二重管理を作りません。

### `mcp.json`（AG-CAP-09 が採用したときだけ生成）

Agent 自身を MCP Server として公開する場合だけ、
plugin root 直下に `mcp.json` を置きます。

```json
{
  "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
  "mcpServers": {
    "order-agent": {
      "type": "streamable-http",
      "url": "https://example.invalid/mcp",
      "headers": { "X-Client-Id": "${ORDER_AGENT_CLIENT_ID}" }
    }
  }
}
```

HVE の artifact gate が機械検証する制約:

- top-level は `$schema` と `mcpServers` の 2 つだけ。`plugin.json` へインラインできない
- `type` は `stdio` / `streamable-http` / `sse` のいずれか
- `stdio` は `command` / `args` / `env` のみ、リモートは `url` / `headers` のみ（`env` を含め混在不可）
- `url` は絶対 HTTP(S)。**loopback 以外は HTTPS 必須**。user-info と fragment は不可
- **`headers` / `env` に資格情報の値を書けない**（可視のパッケージデータのため）
- `PLUGIN_ROOT` / `PLUGIN_DATA` はクライアントが解決する予約変数。`env` で再定義しない

> **重要**: 仕様 v1 は OAuth 設定も可搬な資格情報参照フィールドも定義していません。
> 認可はクライアント側の管理です。そのため
> **利用者が何を設定すれば接続できるか**を `src/agent/{key}/README.md` に残すことが必須です。

`Plugin components` が `mcp.json: required` と明記していないのに
ファイルが存在する場合、gate はエラーにします（意図しない公開を防ぐため）。
判定は英語の定型語（`required` / `yes`）だけを見ます。日本語で「必要」と書いても採用とは判定されません。

## Microsoft 365 / Teams チャネル（AAGD Step.7）

`Dev-Agent-M365Publish` が担当し、`docs/agent/m365-publish-report.md` を出力します。

設計が当該チャネルを採っていない場合も **Step 自体は実行され**、
採らなかった理由と再判定条件をレポートに残します（判定 `NOT_SELECTED`）。
「公開しない」という判断を無記録にしないためです。

### 判定語彙

| 値 | 意味 |
|---|---|
| `PUBLISHED` | 公開が完了し、対象クライアントから呼べる |
| `PENDING_APPROVAL` | 公開要求は出したが管理者承認待ち |
| `NOT_SELECTED` | 設計が当該チャネルを採っていない |
| `FAILED` | 公開を試みたが失敗した（原因必須） |

### 守るべき制約

- **公開範囲と認可スキームは連動**します。テナント全体への公開は管理者承認を伴います
- **既に公開した版と同じ版を再公開できません**。更新時は版を上げます
- **公開メタデータは利用者に見えます**。secret・API キー・接続文字列・内部 URL を入れません
- 既存の認可スキームとプロトコル設定を**削除しません**。公開のために追加するだけです
- API version / SKU / リージョン / リソース名は Microsoft Learn MCP で確認し、
  参照 URL と確認日をレポートに残します（推測で確定しません）

## よくある誤り

- **`plugin.json` に HVE 固有の設定を足す** — closed schema 違反です。
  ランタイム設定は `agent-config.json` / `appsettings.json` に置きます。
- **`mcp.json` の `headers` にトークンを直書きする** — 可視のパッケージデータです。
  `${...}` 形式の変数参照だけを置き、値はクライアント側で解決させます。
- **`name` に大文字を残す** — 仕様の `name` は `a-z` `0-9` `-` `.` のみです。
  fan-out キー `AG-01` はそのままでは使えません。
- **公開していないのに `PUBLISHED` と書く** — gate は判定と App Version の
  整合性を検査します。承認待ちは `PENDING_APPROVAL` です。
