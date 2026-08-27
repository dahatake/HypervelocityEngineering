# AI Agent の Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `aag`（設計） / `aagd`（実装・デプロイ） / `aar`（Agentic Retrieval Add-on）

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## 3 つの Workflow の前提の違い

| Workflow | やること | 前提 |
|---|---|---|
| `aag` | AI Agent の設計書を作る | `aas` の `docs/catalog/service-catalog.md`、`aad-web` の `docs/screen/*.md` / `docs/services/*.md` / `docs/test-specs/*-test-spec.md` |
| `aagd` | AI Agent を実装・デプロイする | `aag` の `docs/agent/*.md`（hard）、`asdw-web`（soft） |
| `aar` | 既存サービスへ Agentic Retrieval を後付けする | `ard` の `docs/catalog/app-catalog.md` / `docs/catalog/use-case-catalog.md` / `docs/architectural-requirements-app-*.md` |

Azure / Microsoft Foundry のリソース名やモデル名は **推測で埋めないでください**。
未確定の値は書かずに残せば、Copilot が質問し、既存の preflight が検証します。

---

## `aag` — AI Agent 設計

主な成果物: `docs/agent/` 配下の Agent 設計書

Step ID: `1`, `2`, `3`

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の問い合わせ対応 AI Agent の設計書を作りたい
- Workflow: aag
- パラメータ:
  - app_ids=APP-NNN
  - usecase_id=<UC-ID>
- 制約: Azure リソースの作成・変更はしないこと。設計書の生成まで
- 期待する成果物: docs/agent/ 配下の設計書

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## `aagd` — AI Agent の実装・デプロイ

主な成果物: `docs/agent/` / `src/test/agent/` / Azure Agent 関連成果物

Step ID: `1`, `2.1`, `2.2`, `2.3`, `3`, `4`, `5`, `6`, `7`

### 実装だけを行う

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の AI Agent を実装したい
- Workflow: aagd
- Step: 1, 2.1, 2.2, 2.3
- パラメータ: app_ids=APP-NNN
- 制約: Azure へのデプロイと評価は含めないこと
- 期待する成果物: src/test/agent/ 配下のコード

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

### デプロイ・評価まで行う

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の AI Agent を実装して Azure にデプロイしたい
- Workflow: aagd
- パラメータ:
  - app_ids=APP-NNN
  - resource_group=<resource-group>
  - usecase_id=<UC-ID>
- 制約: 既存の権限ゲート・承認ゲートを緩めないこと。モデル名やエンドポイントを
  推測で決めないこと（不明なら私に質問すること）
- 期待する成果物: Azure 上にデプロイされた Agent と評価結果

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
計画に含まれる Step の範囲を、私が読んで確認します。
```

---

## `aar` — Agentic Retrieval Add-on

既存サービスに検索基盤を後付けします。

主な成果物: `docs/services/<serviceId>-agentic-retrieval-spec.md` /
`docs/azure/agentic-retrieval/` / `src/infra/azure/create-azure-agentic-retrieval/`

Step ID: `1`, `2`, `3`, `4`, `5`, `6`, `7`

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の既存サービスに Agentic Retrieval を追加したい
- Workflow: aar
- パラメータ:
  - app_ids=APP-NNN
  - usecase_id=<UC-ID>
  - resource_group=<resource-group>
- 制約: Azure AI Search のインデックス名やモデル名を推測で決めないこと
- 期待する成果物: docs/services/ の agentic-retrieval-spec と
  src/infra/azure/create-azure-agentic-retrieval/ のスクリプト

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## 関連

- 詳細ガイド: [07-ai-agent-simple.md](../07-ai-agent-simple.md) / [08-ai-agent.md](../08-ai-agent.md) / [agentic-retrieval-guide.md](../agentic-retrieval-guide.md)
- 前段のデータ設計（`ada`）: [requirements-architecture.md](requirements-architecture.md)
