# Foundry Toolbox / Tool Search 利用ガイド

生成する AI Agent に Microsoft Foundry の **Toolbox** と **tool search**（ツール定義の遅延ロード）を
適用するための手引き。

> **注意**: 本ガイドの「tool search」は、生成される AI Agent 側の設定を指す。
> HVE 自身の Copilot SDK セッション設定（`--tool-search`）とは**別物**。

---

## 1. そもそも何のための機能か

Agent に登録した Tool の定義は、既定では**毎ターン全件**モデルへ送られる。
Tool が増えるほど入力トークンが膨らみ、モデルが選ぶべき Tool を見失いやすくなる。

tool search を有効にすると、Tool 定義はカタログに置かれ、
モデルが必要と判断した時点で検索して取り出す形になる。

## 2. 有効化の目安は Tool 何個からか

**16 個以上で検討**（HVE の既定閾値は 15 超）。

ただしこの数字の性格を理解しておく必要がある。

| 事実 | 出典の性格 |
|---|---|
| 10〜15 個あたりから検討、という指針 | Microsoft Learn / 公式ブログ |
| 50 Tool で 60 パーセント超、1,000 Tool で 97 パーセント超のトークン削減 | **ToolRet ベンチマーク**（44,000+ tools / 7,000 queries）の値 |

削減率は **Tool の description 品質に強く依存する**。
description が不揃いなカタログでは、検索が正しい Tool を返さず、
トークンは減っても Tool 選択精度が落ちる。

→ **閾値 15 は出発点であり、確定値ではない**。AAGD Step.4 の実測で裏付ける。

## 3. Tool 数の数え方

二重計上しやすいので、Skill `foundry-toolbox-contract` の R1 に従う。

| 区分 | 数え方 |
|---|---|
| 検索経路 | AG-CAP-03 の **distinct な経路数**。1 行 = 1 Request class なので、同じ経路が複数行に現れる |
| REST Tool | AG-CAP-04 の CRUD マトリクスに現れる Tool |
| MCP Tool | AG-CAP-05 の allowlist に列挙された Tool |

「行数」で数えると過大になる。

## 4. 使い方

### CLI

```pwsh
hve orchestrate --workflow aagd --enable-tool-search auto
```

| 値 | 意味 |
|---|---|
| `auto`（既定） | 設計 Prompt が Tool 総数から判定する |
| `yes` | Tool 数に関係なく Toolbox と tool search を使う |
| `no` | tool search を使わない（全 Tool を毎ターン渡す）。実測 Step も走らない |

### GUI

設定画面の「Foundry Toolbox / tool search」セレクタで同じ 3 値を選ぶ。

### Cloud

**設問は無い**。Cloud では設計 Prompt が Tool 総数から自動判定する。
そのため Cloud では `no` を選んで実測 Step を落とすことができない。

## 5. 設計書に何が書かれるか

`docs/agent/agent-detail-{key}.md` の Section 7.5 に、以下が固定契約として出力される。

| 見出し | 契約 | 内容 |
|---|---|---|
| 7.5.1 | TB-CAP-01 | Tool Inventory — 経路別の内訳と総数 |
| 7.5.2 | TB-CAP-02 | Toolbox Decision — 有効化するか、しないなら理由 |
| 7.5.3 | TB-CAP-03 | Pinning Policy — 常時公開する Tool |
| 7.5.4 | TB-CAP-04 | Search Metadata — `additional_search_text` |
| 7.5.5 | TB-CAP-05 | Discovery Budget — `limit`（1〜10） |

### よくある失敗

- **見出しレベルを Section 7.5 より深くする**
  → セクション抽出が後続を飲み込み、検証がスキップされる。**同じレベル**にすること。
- **`additional_search_text` を推測で埋める**
  → 公式は反復的な改善を推奨している。初期は `deferred` と書いてよい。
  ただし**行そのものを省略すると FAIL** する。
- **pin に `"*"` を書く**
  → tool search を有効にしながら全件 pin するのは矛盾。FAIL。

## 6. デプロイ時に何が起きるか

`Dev-Microservice-Azure-AgentDeploy` が

1. `create-azure-agent-resources.sh` で **Agent 登録より前に** Toolbox を作成する
2. `verify-agent-resources.sh` で `tools/list` を叩き、期待どおりの公開状態かを確認する

Toolbox が Agent より後だと、Agent が空の Toolbox を参照した状態で登録されてしまう。

## 7. 実測（AAGD Step.4）

`QA-ToolSearchEval` が tool search の on / off を同一クエリ集合で比較する。

### 測定条件

- 評価クエリ 10 件以上。うち**複数 Tool の組み合わせを要するものを 3 件以上**
- **該当 Tool が存在しないタスク**を含める（過剰呼び出しの検出）
- 期待 Tool 集合は**事前に**記録する
- prompt caching はベースラインでも有効のまま（切ると削減率が過大に出る）

### 記録する指標

初期 `tools/list` トークン数 / 1 ターンあたり総入力トークン / Tool 選択正解率 /
`tool_search` 呼び出し回数 / 追加レイテンシ（p50・p95）/ 過剰呼び出し率

### 判定

| 観測 | 次にやること |
|---|---|
| トークン削減 20 パーセント未満 | `additional_search_text` を整備して再測定 |
| 正解率がベースラインより 10 パーセント以上低下 | pin 対象を見直す |
| 特定 Tool が繰り返し外れる | その Tool の description を改善対象として列挙 |
| いずれも問題なし | TB-CAP-02 の判定を妥当と結論づける |

出力先は `docs/agent/tool-search-eval/{key}-eval-report.md`。

> `docs/agent/` **直下**に置いてはならない。`docs/agent/*.md` は
> `aagd` ← `aag` のメタ依存ゲートの判定 glob であり、
> 評価レポートが直下にあると設計書が無くてもゲートが通ってしまう。

## 8. Cloud と registry の Step 採番

定義（SSoT）と実行（Cloud 再利用 YAML）の両方が registry と**一致済み**。

| 層 | 実体 |
| --- | --- |
| 定義（SSoT） | `hve/workflow_registry.py`（CLI/GUI）/ `.github/scripts/bash/lib/workflow-registry.sh`（Cloud） |
| 実行 | `.github/workflows/auto-ai-agent-dev-reusable.yml` |

`aagd` はどの面でも `1 / 2.1 / 2.2 / 2.3 / 3 / 4`。tool search の実測評価は **`Step.4`**。

> Cloud の Issue 上では、見やすさのため `Step.2` のコンテナ Issue を 1 つ作る（`2.1`/`2.2`/`2.3` の親）。
> これは表示上のもので、SSoT には存在しない。

この一致は `hve/tests/test_cloud_reusable_workflow_parity.py` で固定してある。

## 9. Agentic Retrieval との関係

Knowledge Base への接続には 2 つの位相がある。AR-CAP と TB-CAP の両方で
`Connection topology` を宣言し、食い違わせないこと。

| 値 | 意味 |
|---|---|
| `direct-kb` | Agent が Knowledge Base へ直接つながる |
| `via-toolbox` | Toolbox 経由で Knowledge Base 検索を Tool として公開する |

詳細は [agentic-retrieval-guide.md](agentic-retrieval-guide.md) を参照。

## 10. 参照

- Skill: `.github/skills/foundry-toolbox-contract/SKILL.md`
