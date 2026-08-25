# ADA — Agent Data Architecture（画面を持たないデータ中心 AI Agent 向けアーキテクチャ設計）

← [README](../README.md)

---

## 目次

- [対象読者・前提・次のステップ](#対象読者前提次のステップ)
- [ADA とは](#ada-とは)
- [AAS との違い](#aas-との違い)
- [Step 一覧](#step-一覧)
- [起動方法（Cloud / GUI / CLI）](#起動方法cloud--gui--cli)
- [成果物と後続ワークフローへの接続](#成果物と後続ワークフローへの接続)

---

## 対象読者・前提・次のステップ

- 対象読者: 画面を持たない **データ中心の AI Agent** を設計する担当者
- 前提: `knowledge/` に業務要件が整備済み、または `docs-original/` に元設計書があること
- 次のステップ: ADA 完了後に [08-ai-agent.md](./08-ai-agent.md)（AAG → AAGD）へ進む

## ADA とは

ADA は `ARD → ADA → AAG → AAGD` のチェーンの 2 番目に位置し、AI Agent が扱う
**データ資産（構造化・非構造化）とサービス境界** を確定するワークフローです。

チャットや API から呼ばれる AI Agent は画面を持たないため、AAS（Web アプリ向け
アーキテクチャ設計）が前提とする画面カタログ・画面設計が不要です。ADA はそれらを
除外し、代わりに **非構造化データ資産カタログと検索経路候補** を追加します。

> [!NOTE]
> ADA は Step.2〜Step.9 の **9 Step ID**（`2`, `3`, `4.1`, `4.2`, `5`, `6`, `7`, `8`, `9`）で構成されます。
> 旧 Step.1（アプリケーションリストの作成）は ARD（Auto Requirement Definition）ワークフローの
> Step 4.1 へ移設され、`docs/catalog/app-catalog.md` は ADA 起動前に ARD が生成します。

## AAS との違い

| 観点 | AAS（Web アプリ） | ADA（データ中心 AI Agent） |
|---|---|---|
| 画面カタログ / 画面設計 | あり | **なし**（画面を持たないため） |
| サービスカタログ・マトリクス | あり | **なし**（画面×サービスの交差が存在しないため） |
| Azure サービス選定 | あり | **なし**（AAGD の Deploy 側で決定するため） |
| 非構造化データ資産カタログ | なし | **あり**（`Arch-AgentDataAsset`） |
| 検索経路候補（コスト階段） | なし | **あり**（Skill `ai-agent-capability-contract`） |

除外した 3 系統の Step は `hve/workflow_registry.py` の ADA 定義ヘッダーコメントに
理由付きで記録しています。

## Step 一覧

| Step | Custom Agent | 主な成果物 |
|---|---|---|
| 2 | `Arch-Microservice-DomainAnalytics` | `docs/catalog/domain-analytics.md` |
| 3 | `Arch-Microservice-ServiceIdentify` | `docs/catalog/service-catalog.md` |
| 4.1 | `Arch-DataModeling` | `docs/catalog/data-model.md`（常に必須）。単一ファイル版が 50,000 文字を超える見込みのときは `docs/catalog/data-model-service-stores.md` / `docs/catalog/data-model-consistency-events.md` / `docs/catalog/data-model-diagrams.md` を併せて生成し、親を索引/統合版として維持します（分割不要に戻った再実行では 3 件を削除） |
| 4.2 | `Arch-DataModeling` | `src/data/sample-data.json` |
| 5 | `Arch-DataCatalog` | `docs/catalog/data-catalog.md` |
| 6 | `Arch-PersonaCatalog` | `docs/catalog/persona-catalog.md` |
| 7 | `Arch-Microservice-ServiceDetail` | `docs/services/{serviceId}-*-description.md`（サービス数だけ fan-out） |
| 8 | `Arch-AgentDataAsset` | `docs/catalog/unstructured-data-catalog.md` |
| 9 | `Arch-TDD-TestStrategy` | `docs/catalog/test-strategy.md` |

Step 8 は ADA で新規追加した唯一の Agent です。非構造化データ資産ごとに、
Skill `ai-agent-capability-contract` の「検索経路コスト階段」から
**2 つ以上の候補**を挙げ、除外した経路とその理由を必ず残します。これにより
Agentic Retrieval のような高コスト経路がオーバーエンジニアリングになっていないか、
後続の AAG / AAGD で検証できます。

## 起動方法（Cloud / GUI / CLI）

### Cloud（GitHub Issue）

1. Issue テンプレート **`.github/ISSUE_TEMPLATE/agent-data-architecture.yml`** から起票する
2. ラベル `auto-agent-data-architecture` が付くと
   `auto-orchestrator-dispatcher.yml` が
   `auto-agent-data-architecture-reusable.yml` を起動する
3. 進行状況は `ada:initialized` / `ada:ready` / `ada:running` / `ada:done` / `ada:blocked` で追える

### GUI

ワークフロー選択画面の `AI Agent` カテゴリから `Agent Data Architecture` を選ぶ。

### CLI

```powershell
.venv\Scripts\python.exe -m hve orchestrate --workflow ada --app-ids APP-001
```

特定 Step だけを再実行する場合は `--steps 8` のように指定します。

## 成果物と後続ワークフローへの接続

AAG / AAGD は ADA の以下 4 つを**必須入力**として参照します。

- `docs/catalog/data-model.md`（Step 4.1）
- `docs/catalog/data-catalog.md`（Step 5）
- `docs/catalog/persona-catalog.md`（Step 6）
- `docs/catalog/unstructured-data-catalog.md`（Step 8）

AAS 経由で来た場合にのみ存在する画面カタログ・サービスカタログマトリクス・
Azure サービス選定書は **任意入力**へ緩和済みのため、ADA 経由でも AAG / AAGD は
そのまま実行できます。
