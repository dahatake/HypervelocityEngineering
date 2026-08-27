# 要求定義・アーキテクチャ設計の Prompt 例

← [スニペット索引](README.md)

対象 Workflow: `ard` / `aas` / `ada`

> どの例も実行計画（plan）を先に提示し、あなたが承認してから実行します。コマンドの実行は Copilot が代行するため、あなたが入力する必要はありません。

---

## `ard` — 企業・業務分析から要求定義まで

企業と対象業務の分析から、ユースケース候補・アプリケーション一覧・APP 別要求定義書までを整理します。

主な成果物: `docs/company-business-requirement.md` / `docs/business-requirement.md` /
`docs/catalog/use-case-catalog.md` / `docs/catalog/app-catalog.md` /
`docs/architectural-requirements-app-NNN.md`

```text
HVE の Prompt 版で作業してください。

- 目的: 自社の会員向けロイヤリティ事業について、業務分析からユースケース候補と
  アプリケーション一覧までを整理したい
- Workflow: ard
- パラメータ:
  - company_name=<会社名>
  - target_business=<対象事業・業務の説明>
  - target_region=<対象地域>
  - analysis_purpose=<この分析で決めたいこと>
- 制約: Azure リソースには一切触れないこと
- 期待する成果物: docs/business-requirement.md と docs/catalog/app-catalog.md

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

Step を絞りたい場合（`ard` の Step ID は `1`, `1.1`, `1.2`, `2`, `2.1`, `3.1`, `3.2`, `3.3`, `4.1`, `4.2`）:

```text
- Workflow: ard
- Step: 1, 1.1, 1.2
- 制約: ユースケース候補の整理までで止めること
```

> KPI / OKR の定義（Step `2.1`）は任意です。実行したい場合は Step に `2.1` を含めてください。
> CLI の `--include-kpi-okr` に相当する `include_kpi_okr` パラメータは Prompt 版 v1 では指定できず、
> 指定すると計画時に拒否されます。Step `2.1` を選ぶ方法を使ってください。

---

## `aas` — アプリケーションアーキテクチャ設計

`ard` が作った `docs/catalog/app-catalog.md` などを入力に、アプリ構成・ドメイン分析・
データモデル・サービス一覧・テスト戦略を設計します。

主な成果物: `docs/catalog/app-arch-catalog.md` / `docs/catalog/domain-analytics.md` /
`docs/catalog/data-model.md` / `docs/catalog/service-catalog.md` /
`docs/catalog/service-catalog-matrix.md` / `docs/catalog/test-strategy.md`

```text
HVE の Prompt 版で作業してください。

- 目的: 既存の app-catalog.md をもとにアプリケーションアーキテクチャを設計したい
- Workflow: aas
- 制約: 実装コードは生成しないこと。設計ドキュメントのみ
- 期待する成果物: docs/catalog/ 配下の設計カタログ一式

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

> `aas` は Workflow 固有パラメータを持ちません（対象は入力ドキュメントで決まります）。
> `ard` の成果物が無い状態でも `plan` は提示されます（`--dry-run` は前提不足を検出しません）。
> 先に `ard` を実行してください。

---

## `ada` — AI Agent 向けデータ設計

画面を持たないデータ中心の AI Agent を作る前段として、データ資産・ペルソナ・
非構造化データを整理します（`aag` の前段）。

主な成果物: `docs/catalog/data-catalog.md` / `docs/catalog/persona-catalog.md` /
`docs/catalog/unstructured-data-catalog.md`

```text
HVE の Prompt 版で作業してください。

- 目的: APP-NNN の AI Agent が使うデータ資産とペルソナを整理したい
- Workflow: ada
- パラメータ: app_ids=APP-NNN
- 制約: Azure へのデプロイはしないこと
- 期待する成果物: docs/catalog/data-catalog.md と docs/catalog/persona-catalog.md

まず実行計画だけを見せてください。
私が「実行してください」と書くまで、実行はしないでください。
```

---

## 関連

- 詳細ガイド: [01-business-requirement.md](../01-business-requirement.md) / [02-app-architecture-design.md](../02-app-architecture-design.md) / [09-agent-data-architecture.md](../09-agent-data-architecture.md)
- Workflow / Step の正本: `hve/workflow_registry.py`、一覧は [workflow-reference.md](../workflow-reference.md)
- 複数 Workflow をまとめて計画する: [cross-workflow.md](cross-workflow.md)
