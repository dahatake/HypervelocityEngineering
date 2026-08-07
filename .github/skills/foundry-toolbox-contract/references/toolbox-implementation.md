# Toolbox の実装・デプロイ・実測（TB-CAP-05 と検証）

Microsoft Learn 確認日 2026-08-04。**プレビュー機能のため API は変動する。**

## 1. 前提条件（公式）

| 項目 | 内容 |
|---|---|
| プロジェクト | 有効な Microsoft Foundry project |
| Toolbox | Tool を 1 つ以上含む toolbox |
| RBAC | 関係する各 ID（開発者・Agent の managed identity・OAuth フローのエンドユーザー）へ Foundry project の **Foundry User** ロール |
| プレビューヘッダー | `Foundry-Features: Toolboxes=V1Preview` |
| トークンスコープ | `https://ai.azure.com/.default` |

## 2. 有効化

toolbox version の tools に `{"type": "toolbox_search"}` を追加する。
これは設定ディレクティブであり、`tools/list` には現れない。

### REST

```http
POST {project_endpoint}/toolboxes/{name}/versions?api-version=v1
Authorization: Bearer {token}
Content-Type: application/json
Foundry-Features: Toolboxes=V1Preview

{
  "description": "...",
  "tools": [
    { "type": "toolbox_search" },
    { "type": "mcp", "server_label": "...", "tool_configs": { ... } }
  ]
}
```

### SDK シンボル名は確定していない

| 出典 | クラス名 | メソッド |
|---|---|---|
| Command Line ブログ | `ToolboxSearchToolboxTool` | `client.toolboxes.create_version` |
| Microsoft Learn | `ToolSearchToolboxTool` | `client.beta.toolboxes.create_version` |

**実装前に Microsoft Learn MCP と package manager 上の version で確定し、
確認日・version・title / URL を作業ログへ記録すること。**
Prompt の静的例や別名パッケージから推測しない。

REST は両者で一致している（`{"type": "toolbox_search"}`）ため、
SDK が不確実な段階では REST を先に検証する選択肢がある。

## 3. TB-CAP-05 `Discovery Budget`

### `tool_search` のパラメータ

| パラメータ | 型 | 必須 | 内容 |
|---|---|---|---|
| `query` | string | Yes | 必要な能力・タスクの自然言語記述 |
| `limit` | integer | No | 返す Tool の最大数。**既定 5 / 最大 10** |

### 予算の考え方

- `limit` を上げると 1 回の検索で候補が増えるが、その分トークンを消費する。
  曖昧なワークフローでは増やし、狭いワークフローでは減らす。
- モデルは 1 ターン内で `tool_search` を複数回呼べる。回数が増えるとレイテンシが増える。
- 「能力が存在しない」と結論づける前に `tool_search` を呼ぶよう、
  Agent の system prompt で指示する必要がある。

### 記載例

```
- Status: selected
- limit: 5
- Expected tool_search calls per turn: 1〜2
- Overflow behavior: 3 回で見つからない場合は「該当機能なし」を返し、推測で近い Tool を呼ばない
- System prompt requirement: 能力が無いと判断する前に必ず tool_search を呼ぶ旨を明記する
- Checked at: 2026-08-04
```

## 4. デプロイ時の検証（AC 観点）

設計値と実 Toolbox の一致を確認する。

| 確認項目 | 方法 |
|---|---|
| tool search が有効か | `tools/list` に `tool_search` / `call_tool` だけが出る（pin した Tool を除く） |
| pin が設計どおりか | `tools/list` の Tool 名集合 = TB-CAP-03 の pin 一覧 |
| 隠れた Tool が呼べるか | `tool_search` で発見 → `call_tool` で実行できる |
| `limit` が設計どおりか | `tool_search` の応答件数 |
| バージョン | 既定 version が意図した version か |

Toolbox は managed resource であり、**Agent コードを変えずに** Tool の追加・削除・更新ができる。
version を昇格させれば消費側の Agent を再デプロイせずに反映される。
このため「実 Toolbox の設定」と「設計書」の乖離が起きやすく、デプロイ時の照合が必要になる。

## 5. 実測評価（推定値で語らないため）

公開されている 60〜97% のトークン削減は ToolRet ベンチマーク（44,000+ tools / 7,000 queries）の値であり、
**自社カタログの Tool 記述品質に依存する**。導入効果は実測する。

### 測定条件

- 同一の評価クエリ集合を使う（最低 10 件、うち 3 件以上は複数 Tool の組み合わせが必要なもの）
- tool search の on / off だけを変え、他は固定する
- 各クエリの期待 Tool 集合を事前に記録する

### 記録する指標

| 指標 | 取得方法 |
|---|---|
| 初期 `tools/list` のトークン数 | クライアント実測 |
| 1 ターンあたりの総入力トークン | 実測 |
| Tool 選択正解率 | 期待 Tool 集合との一致 |
| `tool_search` 呼び出し回数 | 実測 |
| 追加レイテンシ（p50 / p95） | 検索ラウンドトリップ分 |

### 判定

- トークン削減が 20% 未満なら、Tool 数が閾値付近すぎるか description が不揃いである。
  まず `additional_search_text` を整備してから再測定する。
- 正解率がベースラインより 10% 以上落ちたら、pin 対象を見直す。

### 禁止事項

- 測定していない数値をレポートへ書かない。未実施は「未測定（理由）」と記す。
- 公開ベンチマークの数値を自社の実測値として引用しない。

## 6. チューニングの順序

公式の指針は「最初のチューニングはアルゴリズムではなく編集作業」。

1. Tool description を改善する（ユーザー意図の語彙にする）
2. `additional_search_text` にドメイン語彙を足す
3. 中核 Tool を pin する
4. `limit` を調整する

外れたケースを個別に確認してから次の手を打つ。いきなり検索方式を変えようとしない。
