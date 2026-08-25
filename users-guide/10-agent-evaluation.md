# AI Agent の評価 — 検索経路の適正化実測（AAGD Step.6）

← [README](../README.md)

---

## 目次

- [対象読者・前提](#対象読者前提)
- [なぜ評価が必須なのか](#なぜ評価が必須なのか)
- [Step.5 との違い](#step5-との違い)
- [検索経路のコスト階段](#検索経路のコスト階段)
- [レポートの読み方](#レポートの読み方)
- [よくある誤り](#よくある誤り)

---

## 対象読者・前提

- 対象読者: AAGD で AI Agent をデプロイした担当者
- 前提: AAGD Step.3（Deploy）が完了していること
- 関連: [08-ai-agent.md](./08-ai-agent.md) / [agentic-retrieval-guide.md](./agentic-retrieval-guide.md) / 次の Step.7 は [11-agent-m365-publish.md](./11-agent-m365-publish.md)

## なぜ評価が必須なのか

Agentic Retrieval のように **反復検索と推論を伴う経路** は、単一クエリ検索や
データストア native 検索よりコストと応答時間が大きくなります。

設計時に「高度な検索が必要そうだ」と判断して高コストな経路を選んでも、
**それが本当に必要だったか**は設計文書からは分かりません。
より安い経路を実際に動かして比べない限り、過剰かどうかは判定できません。

このため AG-CAP-10 は「**候補経路を 2 段以上実測しない評価は受理しない**」と定めています。
AAGD Step.6 はこの契約を実行する Step です。

## Step.5 との違い

| 観点 | Step.5 要件適合実測 | Step.6 検索経路の適正化実測 |
|---|---|---|
| 問い | デプロイした構成は目標を満たすか | もっと安い経路でも足りたのではないか |
| 測る対象 | デプロイ済み構成 1 つ | 採用段 + より安い段（**2 段以上**） |
| 判定語彙 | `PASS` / `FAIL` / `NOT_MEASURED` / `NO_TARGET` | `KEEP` / `DOWNGRADE` / `INSUFFICIENT` / `NOT_MEASURED` |
| 出力 | `docs/agent/requirements-conformance-report.md` | `docs/agent/route-rightsizing-report.md` |

Step.5 で目標をすべて満たしていても、Step.6 で `DOWNGRADE` になることがあります。
「目標は満たしているが過剰」という状態は Step.5 だけでは検出できません。

## 検索経路のコスト階段

Skill `ai-agent-capability-contract` の
`references/search-routing.md` §4.1 が 5 段のコスト階段を定義しています。

| 段 | 経路 | 段を下げると失うもの |
|---|---|---|
| 1 | Agentic Retrieval（反復あり） | 複数ソース横断とサブクエリ分解 |
| 2 | Agentic Retrieval（既定） | クエリ計画の自動化 |
| 3 | LLM を使わない最小構成 | 意図解釈とリランク |
| 4 | データストア native 検索 | 横断検索と統合スコアリング |
| 5 | 自前実装 | マネージド機能全般（6 機能を自前で補う必要） |

Step.6 では **採用段と、それより下の段を最低 1 つ**測ります。
どの段を比較対象に選ぶかは、ADA が生成した
`docs/catalog/unstructured-data-catalog.md` の「第2候補」「除外した経路と理由」を根拠にします。

## レポートの読み方

`docs/agent/route-rightsizing-report.md` は次の固定フォーマットです。

```markdown
- Schema-Version: 1
- Workflow: aagd
- Step: 6
- Agent: QA-AgentRouteRightsizingEval
- Measured-At: 2026-08-18T10:00:00Z
- Dataset: 業務問い合わせ 実記録からの抽出
- Dataset-Size: 120
- Secret-Redaction: confirmed

| Rung | Route | Accuracy | Tokens | Latency | Judgement | Evidence |
|---|---|---|---|---|---|---|
| 2 | Agentic Retrieval（既定） | 0.91 | 4200 | 3.1s | KEEP | run-2026-08-18-a |
| 4 | Cosmos DB ハイブリッド検索 | 0.72 | 900 | 0.6s | KEEP | run-2026-08-18-b |

- Conclusion: KEEP
- Rationale: 段 4 は正答率が目標 0.85 を下回り、要件を満たさない。
- Recommended-Route: Agentic Retrieval（既定）
```

判定の意味:

| 値 | 意味 | 次にすること |
|---|---|---|
| `KEEP` | 安い段では要件を満たせず、採用段が妥当 | そのまま運用 |
| `DOWNGRADE` | 安い段でも要件を満たし、採用段は過剰 | 経路の見直しを検討 |
| `INSUFFICIENT` | 比較が 1 段しかできず判定不能 | 比較対象を用意して再測定 |
| `NOT_MEASURED` | 当該段を実行できなかった | `Evidence` の理由を確認 |

## よくある誤り

- **1 段だけ測って「適正」と結論する** — 比較表が 1 行のレポートは
  HVE の artifact gate が拒否します。測れなかった段も `NOT_MEASURED` の行として残し、
  `Conclusion` を `INSUFFICIENT` にします。
- **段ごとに違う評価データセットを使う** — 比較になりません。全段で同一データセットを使います。
- **未実測を `KEEP` にする** — `KEEP` / `DOWNGRADE` は正答率・トークン・応答時間の
  3 指標がすべて揃っている行にしか使えません。
- **測定のために本番構成を変更する** — Step.6 は測定と推奨までが責務で、
  構成変更・再デプロイは行いません。
