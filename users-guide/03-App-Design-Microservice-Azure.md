# Web Application 設計（AAD-WEB）

← [02-app-architecture-design.md](./02-app-architecture-design.md) | [05-app-dev-microservice-azure.md](./05-app-dev-microservice-azure.md) →

> [!IMPORTANT]
> 本文の Step ID・依存・入出力は、2026-08-07 時点の
> [`hve/workflow_registry.py`](../hve/workflow_registry.py) に登録された **CLI / GUI 共通の AAD-WEB** を正本とします。
> GitHub Actions の Cloud AAD-WEB は dispatch 可能ですが、後述のとおり別の旧 Step 体系です。
> 現行 AAD-WEB → ASDW-WEB を連続実行する場合は CLI または GUI を使用してください。

## 対象読者

- AAS の成果物から画面・サービス・TDD テスト仕様を生成したい開発者
- AAD-WEB の Step、Prompt、テンプレート、I/O 契約、Skill、テストを保守する開発者
- AAD-WEB の完了成果物を [ASDW-WEB](./05-app-dev-microservice-azure.md) へ引き渡す担当者

## AAS から ASDW-WEB までの連続経路

```text
ARD / 既存要件
    └─ docs/catalog/use-case-catalog.md
                ↓
AAS
    ├─ app-arch-catalog / app-catalog
    ├─ domain-analytics / service-catalog / data-model
    └─ service-catalog-matrix / test-strategy
                ↓
AAD-WEB（本ガイド）
    ├─ screen-catalog-APP-*.md / docs/screen/*
    ├─ docs/services/*
    ├─ docs/test-specs/*-test-spec.md
    └─ screen-service-consistency-report.md
                ↓
ASDW-WEB
```

### 前提成果物

| 用途 | 必須成果物 |
|---|---|
| APP スコープ解決 | `docs/catalog/app-arch-catalog.md`, `docs/catalog/app-catalog.md` |
| 画面・サービス設計 | `docs/catalog/domain-analytics.md`, `docs/catalog/service-catalog.md`, `docs/catalog/data-model.md`, `docs/catalog/service-catalog-matrix.md` |
| TDD 仕様 | `docs/catalog/test-strategy.md` |
| 追加 Azure サービス選定を実行する場合 | `docs/catalog/use-case-catalog.md` |

- 対象 APP-ID は `docs/catalog/app-arch-catalog.md` から実装の分類器が `web-cloud` と判定する必要があります。
    標準表記は `Webフロントエンド + クラウド` です。
- APP-ID 未指定時は一致する APP-ID を自動選択します。カタログが存在して一致が 0 件なら DAG は実行されません。
- CLI / GUI のセットアップは [CLI ガイド](./hve-cli-orchestrator-guide.md) / [GUI ガイド](./hve-gui-orchestrator-guide.md) を参照してください。
- `knowledge/` の活用は [km-guide.md](./km-guide.md) を参照してください。

## 実行経路

| 経路 | 状態 | 実装 |
|---|---|---|
| CLI | **現行 AAD-WEB を実行可能** | `python -m hve orchestrate --workflow aad-web` → `workflow_registry` → `template_engine` → `DAGExecutor` / `StepRunner` |
| GUI | **現行 AAD-WEB を実行可能** | `python -m hve`。ワークフローと Step は `workflow_registry.list_workflows()` / `get_workflow()` から動的表示 |
| GitHub Actions Cloud | **旧 Cloud AAD-WEB として dispatch 可能。現行 registry とは非同期** | `web-app-design.yml` → `auto-orchestrator-dispatcher.yml` → `auto-app-detail-design-web-reusable.yml` |

### CLI

まず dry-run で APP スコープ、fan-out、依存関係を確認します。

```bash
python -m hve orchestrate --workflow aad-web --app-ids APP-009 --dry-run
```

dry-run はパラメータ、APP フィルタ、fan-out、DAG の計画表示までで終了し、後段の
runtime 入力成果物チェック、必須 Skill チェック、Prompt 実行は行いません。

計画が正しければ実行します。

```bash
python -m hve orchestrate --workflow aad-web --app-ids APP-009
```

- `--steps 1,2.1,...` で部分実行できますが、選択していない前段 Step は自動追加されません。
    前段成果物が既に存在する場合だけ部分実行してください。
- `--enable-agentic-retrieval no` の場合は Step 2.6 が無効化され、skip 済み依存として扱われます。
- `--strict` は通常実行時の `continue-on-precheck` 降格を無効化しますが、すべての警告をエラー化するフラグではありません。
    ルート Step の `consumed_artifacts` 不足も停止対象にする場合は、別設定 `HVE_REQUIRE_INPUT_ARTIFACTS=true` が必要です。

### GUI

1. `python -m hve` を起動します。
2. **Web App Design (AAD-WEB)** を選びます。
3. APP-ID と実行 Step を選びます。既定は全 Step ON です。
4. プランレビューで `required_input_paths` の欠損を解消してから実行します。

### GitHub Actions Cloud の境界

Cloud dispatcher は AAD-WEB を現在も
[`auto-app-detail-design-web-reusable.yml`](../.github/workflows/auto-app-detail-design-web-reusable.yml)
へ渡します。ただし、次の3面は同期していません。

- Issue Form [`web-app-design.yml`](../.github/ISSUE_TEMPLATE/web-app-design.yml) は Step 1 / 2.1〜2.4 を表示します。
- reusable workflow は旧 Step 1.1〜8.3 の Issue 群を生成します。
- CLI / GUI の registry は Step 1 / 2.1〜2.6 / 3 です。

したがって、Cloud の `aad-web:done` だけを現行 AAD-WEB 完了の証拠にせず、
後述の ASDW-WEB 必須成果物を実ファイルで確認してください。Cloud reusable workflow の仕組み自体は
GitHub Docs **“Reuse workflows”**
(https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) の `workflow_call` 契約に従います。

## 現行 Step と入出力

### 依存グラフ

```text
1 -> 2.1 -> 2.4
1 -> 2.2 -> 2.3
2.2 -> 2.5
2.2 -> 2.6（設定で無効化可）
2.1 + 2.2 + 2.3 + 2.4 -> 3
```

Step 3 は 2.1〜2.4 の整合性レビューです。2.5 / 2.6 は Step 3 の依存ではないため、
DAG 上は独立して完了します。

| Step | Prompt | 主入力 | 主出力 | 依存 / fan-out |
|---|---|---|---|---|
| 1 画面一覧と遷移図 | `Arch-UI-List` | app / data model / domain / service catalog | `docs/catalog/screen-catalog-{APP-ID}.md` | ルート。APP 単位 fan-out |
| 2.1 画面定義書 | `Arch-UI-Detail` | per-APP screen catalog、AAS カタログ群 | `docs/screen/{screenId}-{screenNameSlug}-description.md` | 1。画面単位 fan-out |
| 2.2 マイクロサービス定義書 | `Arch-Microservice-ServiceDetail` | service catalog / matrix、AAS カタログ群 | `docs/services/{serviceId}-{serviceNameSlug}-description.md` | 1。サービス単位 fan-out |
| 2.3 サービス別 TDD テスト仕様 | `Arch-TDD-TestSpec` | test strategy、サービス定義、AAS カタログ群 | `docs/test-specs/{serviceId}-test-spec.md` | 2.2。サービス単位 fan-out |
| 2.4 画面別 TDD テスト仕様 | `Arch-TDD-TestSpec` | test strategy、画面定義、AAS カタログ群 | `docs/test-specs/{screenId}-test-spec.md` | 2.1。画面単位 fan-out |
| 2.5 追加 Azure サービス選定 | `Dev-Microservice-Azure-AddServiceDesign` | use case / service catalog / サービス定義 | `docs/azure/azure-services-additional.md` | 2.2 |
| 2.6 Agentic Retrieval 機能要件 | `Arch-AgenticRetrieval-Detail` | service catalog / サービス定義 / domain | `docs/services/{serviceId}-agentic-retrieval-spec.md` | 2.2。サービス単位 fan-out、設定で無効化可 |
| 3 画面↔サービス整合性レビュー | `QA-DocConsistency` | 画面・サービス・両 TDD 仕様・matrix | `docs/catalog/screen-service-consistency-report.md` | 2.1 / 2.2 / 2.3 / 2.4 |

`{screenNameSlug}` / `{serviceNameSlug}` のように catalog parser だけでは確定できない値は、
registry の `output_paths_template` では成果物 gate 用の確定パスへ展開されません。
実名は各 Prompt と catalog の命名契約で決まります。

<a id="aad-web-completion"></a>

## 完了確認

ASDW-WEB へ進む前に、対象 APP-ID について次を確認します。

- `docs/catalog/screen-catalog-{APP-ID}.md` が存在する。
- catalog に列挙された各画面の `docs/screen/*-description.md` が存在する。
- 対象サービスの `docs/services/*-description.md` が存在する。
- 各対象サービスの `docs/test-specs/{serviceId}-test-spec.md` が存在する。
- 各対象画面の `docs/test-specs/{screenId}-test-spec.md` が存在する。
- `docs/catalog/screen-service-consistency-report.md` に未解消の Critical がない。
- Step 2.5 を実行した場合は `docs/azure/azure-services-additional.md` が存在する。
- Agentic Retrieval を有効にした場合は対象サービスごとの spec、または適用外理由が記録されている。
- CLI の終了コードが 0、GUI の対象 workflow が完了である。

この確認後に [ASDW-WEB の開始条件](./05-app-dev-microservice-azure.md#asdw-web-start-conditions) へ進みます。

## 失敗時の確認順

| 症状 | 確認箇所 | 対応 |
|---|---|---|
| APP-ID が 0 件 | `docs/catalog/app-arch-catalog.md` の `A) サマリ表（全APP横断）` | 推薦アーキテクチャと APP-ID を修正し、dry-run を再実行 |
| 通常実行の pre-check で blocked | Step の `required_input_paths` / `required_skills` | 欠損成果物または Skill を補い、`--strict` 付き通常実行で再確認。`--dry-run` は runtime pre-check を実行しない |
| fan-out が 0 件 | screen / service catalog parser の入力 | catalog の ID と APP-ID 紐付けを確認 |
| Step は成功したが成果物がない | registry の `output_paths` / `output_paths_template` と Prompt 出力契約 | Prompt、テンプレート、I/O 契約を同時に修正し契約テストを実行 |
| Cloud の Step が本文と違う | Cloud reusable の旧 Step 体系 | 現行 AAD-WEB は CLI / GUI で再実行。Cloud 側を current registry と同等とみなさない |

## HVE カスタマイズ正本

| 変更したい内容 | 正本 | 同時に確認するもの |
|---|---|---|
| Step ID、タイトル、依存、fan-out、入出力、必須 Skill | [`hve/workflow_registry.py`](../hve/workflow_registry.py) の `AAD_WEB` | `hve/tests/test_workflow_registry_agentic.py`, `hve/tests/test_fanout.py` |
| Step Issue / main task の本文 | [`.github/scripts/templates/aad-web/`](../.github/scripts/templates/aad-web/) | [`hve/template_engine.py`](../hve/template_engine.py), `hve/tests/test_template_engine.py` |
| Agent の行動・禁止事項・DoD | [`.github/prompts/`](../.github/prompts/) の `Arch-UI-*`, `Arch-Microservice-ServiceDetail`, `Arch-TDD-TestSpec`, `Arch-AgenticRetrieval-Detail`, `QA-DocConsistency` | [`hve/prompt_loader.py`](../hve/prompt_loader.py), `hve/tests/test_prompt_loader.py` |
| 座標別 input / output / producer | [`.github/io-contracts/`](../.github/io-contracts/) の `*--aad-web--<step>.yaml` | `.github/scripts/validate-io-contract.py`, `hve/tests/test_tdd_report_io_contract.py` |
| Workflow 既定 Skill、Step 必須 / optional Skill | [`hve/skill_manifest.json`](../hve/skill_manifest.json) と Step の `required_skills` | [`hve/skill_resolver.py`](../hve/skill_resolver.py), `hve/tests/test_skill_resolver.py` |
| Cloud Issue Form / dispatch / 旧 Step 状態機械 | [`web-app-design.yml`](../.github/ISSUE_TEMPLATE/web-app-design.yml), [`auto-orchestrator-dispatcher.yml`](../.github/workflows/auto-orchestrator-dispatcher.yml), [`auto-app-detail-design-web-reusable.yml`](../.github/workflows/auto-app-detail-design-web-reusable.yml) | current registry とは別契約として差分確認 |

Runtime では [`hve/runner.py`](../hve/runner.py) が Prompt ファイル本文を main task Prompt の先頭へ置き、
Skill guard を付加します。Step 変更時に registry だけ、Prompt だけ、I/O 契約だけを変更すると drift するため、
上表の契約テストまで同じ変更単位で更新してください。
