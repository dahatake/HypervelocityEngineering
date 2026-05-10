# Agentic Retrieval 利用ガイド

← [README](../README.md)

---

## 目次

- [対象読者・前提・次のステップ](#対象読者前提次のステップ)
- [概要](#概要)
- [どのワークフローで何が追加されたか](#どのワークフローで何が追加されたか)
- [入力項目（Q1〜Q6）](#入力項目q1q6)
- [Indexer と Push API の選び方](#indexer-と-push-api-の選び方)
- [Microsoft Foundry 連携の考え方](#microsoft-foundry-連携の考え方)
- [生成される成果物](#生成される成果物)
- [用語表](#用語表)
- [注意事項](#注意事項)

---

## 対象読者・前提・次のステップ

- 対象読者: AAD-WEB / ASDW-WEB で Agentic Retrieval を有効化する設計・実装担当者
- 前提: `.github/ISSUE_TEMPLATE/web-app-design.yml` / `web-app-dev.yml` の入力項目を使って起票できること
- 次のステップ:
  - 全体の AI Agent 設計・実装: [08-ai-agent.md](./08-ai-agent.md)
  - プロンプト実例: [prompt-examples.md](./prompt-examples.md)

## 概要

- Agentic Retrieval は、Chat-Bot / AI Agent / RAG / 対話型応答を
  要件に含むサービス向けの拡張機能です。
- 本リポジトリでは、設計フェーズと実装フェーズで役割を分けます。
  - AAD-WEB: 製品非依存の機能要件詳細を作成
  - ASDW-WEB: Azure 実装設計と実 Azure デプロイを実施

## どのワークフローで何が追加されたか

### AAD-WEB

- 既存 Step.2.2 の後段観点として
  `Arch-AgenticRetrieval-Detail`（Step.2.2.1 相当）を扱います。
- 実装上は Step.2.2（`Arch-Microservice-ServiceDetail`）内で
  Agentic Retrieval 要件を委譲・反映します。

### ASDW-WEB

- Step.2.2 は `Dev-Microservice-Azure-AddServiceDesign`
  （AgenticRetrievalDesign 相当）で扱います。
- Step.2.3 は `Dev-Microservice-Azure-AddServiceDeploy`
  （AgenticRetrievalDeploy 相当）で扱います。

### スキップ条件

- `enable_agentic_retrieval=no` の場合、関連 Step はスキップされます。

## 入力項目（Q1〜Q6）

以下は `web-app-design.yml` / `web-app-dev.yml` と `hve/template_engine.py` の項目定義に準拠しています。

| 項目 | 説明 | 既定値 | 適用 |
| --- | --- | --- | --- |
| Agentic Retrieval を使用する | `auto` は自動判定、`yes` は明示有効、`no` は明示無効 | `auto` | AAD / ASDW |
| データソース投入方式 | Indexer（Pull）優先、非対応は Push API、必要に応じて併用 | `Indexer` | ASDW |
| Microsoft Foundry 連携 | Foundry プロジェクト + モデル + MCP 接続を扱う | `する` | AAD / ASDW |
| 想定データソース | 起点となるデータソースを自由記述（1 行 1 件） | 空 | ASDW |
| 既存設計の差分更新 | 既存設計を全上書きせず差分で更新する | OFF | ASDW |
| Foundry モデル SKU フォールバック | `Global 必須` か `Standard 許容` を選択 | `Standard 許容` | ASDW |

## Indexer と Push API の選び方

- Indexer 優先:
  - 標準コネクタで安定運用したい
  - 定期クロールで十分
- Push API を使う:
  - アプリ側イベントで即時反映したい
  - Indexer 非対応ソースを扱う
- 併用する:
  - 基本データは Indexer、速報データは Push API で運用したい

> [!IMPORTANT]
> 対応データソースの最新一覧、具体的 SKU / モデル名 / API バージョンは
> 本ガイドに固定値を記載しません。実行時に Microsoft Learn MCP または
> 公式ドキュメントを参照してください。

## Microsoft Foundry 連携の考え方

- Foundry 連携を ON にすると、Foundry プロジェクト連携と
  MCP 接続設定（例: `azure_ai_search`）の設計・構成対象が有効化されます。
- Remote MCP Server は、外部ツールや知識ベースを
  Agent 実行コンテキストに接続するための構成概念です。
- `Global 必須` は Global SKU 前提で厳格に扱う方針、
  `Standard 許容` は Standard SKU へのフォールバックを許可する方針です。
- 機密情報管理、認証・認可、秘密情報注入は既存 Skill /
  既存運用基盤に委譲してください。

## 生成される成果物

- `docs/services/{serviceId}-agentic-retrieval-spec.md`
- `docs/azure/agentic-retrieval/{serviceId}-design.md`
- `infra/azure/create-azure-agentic-retrieval/...`
  （Agent 実行時に生成）
- `work/.../artifacts/cli-evidence.md`
- `work/.../artifacts/created-resources.json`
- `work/.../artifacts/ac-verification.md`

## 用語表

| 英語 | 日本語 | 本リポジトリでの意味 |
| --- | --- | --- |
| Knowledge Source | ナレッジソース | 取り込み元データソース／インデックスの論理参照 |
| Knowledge Base | ナレッジベース | Agentic Retrieval が問い合わせる知識基盤 |
| Indexer | インデクサー | Pull 型取り込み |
| Push API | Push API | アプリ側が直接投入する方式 |
| Vector Search | ベクトル検索 | 類似検索 |
| Semantic Search | セマンティック検索 | 意味ベースのランキング |
| MCP | Model Context Protocol | 外部ツール／知識ベース連携のためのプロトコル |
| Foundry | Microsoft Foundry | モデル・エージェント・接続管理基盤 |

## 注意事項

- SKU / モデル名 / API バージョン / 対応データソース一覧は固定値を書かない
- Microsoft Learn MCP / 公式 Learn URL を都度参照する
- `enable_agentic_retrieval=no` の場合、関連 Step は生成されない
- 参照導線としてのみ利用し、ルート `/README.md` は変更していません
