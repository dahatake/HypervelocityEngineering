# Dataflow（バッチ処理）の Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `adfd`（設計） / `adfdv`（実装・デプロイ）

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## 設計と実装の境界

| Workflow | やること | 前提 |
|---|---|---|
| `adfd` | バッチ処理の設計書を作る | `aas` の成果物（`docs/catalog/app-catalog.md` / `docs/catalog/domain-analytics.md`）。soft 依存のため、無くても計画できる場合がある |
| `adfdv` | バッチを実装し、Azure へデプロイする | `adfd` の成果物（`docs/dataflow/` 配下）。hard 依存 |

---

## `adfd` — Dataflow 設計

主な成果物: `docs/dataflow/dataflow-domain-analytics.md` / `docs/dataflow/dataflow-data-model.md` /
`docs/dataflow/dataflow-app-catalog.md` / `docs/dataflow/dataflow-service-catalog.md` /
`docs/dataflow/dataflow-test-strategy.md` / `docs/dataflow/apps/*.md`

Step ID: `0.1`, `0.2`, `1`, `2`, `3`, `4`, `5`

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN のバッチ処理（日次集計）の設計書を作りたい
- Workflow: adfd
- パラメータ: app_ids=APP-NNN
- 制約: Azure リソースの作成・変更はしないこと。設計書の生成まで
- 期待する成果物: docs/dataflow/ 配下の設計書一式

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## `adfdv` — Dataflow の実装とデプロイ

主な成果物: `src/` / `src/test/` / `src/infra/azure/dataflow/`

Step ID: `1.1`, `1.2`, `2.1`, `2.2`, `3`, `4.1`, `4.2`, `4.3`

### 実装だけを行う（デプロイしない）

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN のバッチ処理を実装したい
- Workflow: adfdv
- Step: 1.1, 1.2
- パラメータ: app_ids=APP-NNN
- 制約: Azure へのデプロイは含めないこと
- 期待する成果物: src/ と src/test/ 配下のコード

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

### デプロイまで行う

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN のバッチ処理を実装して Azure にデプロイしたい
- Workflow: adfdv
- パラメータ:
  - app_ids=APP-NNN
  - resource_group=<resource-group>
- 制約: 既存の権限ゲート・承認ゲートを緩めないこと
- 期待する成果物: src/、src/test/、src/infra/azure/dataflow/、および Azure 上のリソース

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
計画に含まれる Step の範囲を、私が読んで確認します。
```

> **デプロイを含む計画は、承認前に Step の範囲を必ず確認してください。**

---

## 関連

- 詳細ガイド: [04-app-design-dataflow.md](../04-app-design-dataflow.md) / [06-app-dev-dataflow-azure.md](../06-app-dev-dataflow-azure.md)
- 設計 → 実装をまとめて計画する: [cross-workflow.md](cross-workflow.md)
