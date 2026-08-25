# Web Application の作成（ASDW-WEB）

← [README](../README.md) | ← [03-app-design-microservice-azure.md](./03-app-design-microservice-azure.md) | [06-app-dev-dataflow-azure.md](./06-app-dev-dataflow-azure.md) →

> [!IMPORTANT]
> 本文の Step ID・依存・入出力は、2026-08-07 時点の
> [`hve/workflow_registry.py`](../hve/workflow_registry.py) に登録された **CLI / GUI 共通の ASDW-WEB** を正本とします。
>
> - GitHub Actions Cloud は registry parity 検証済みの reusable workflow から起動できます。
> - full run の DataDeploy Step 1.3 は `APP-009` 単一スコープだけをサポートします。
> - APP-009 の既存 `docs/azure/azure-services-compute.md` は Azure Container Apps / Container Apps Jobs を選定していますが、
>   current Step 3.3 / 3.4 は Azure Functions 固定です。選定済み Compute を実装する汎用経路ではありません。
> - Step 4.3 が必須入力とする `.github/workflows/azure-static-web-apps-app009.yml` は、現リポジトリの HEAD に存在しません。
>   また、Step 4.3 の scoped I/O contract が required とする `knowledge/D15-非機能-運用-監視-DR-仕様書.md` も存在しません。
>   したがって **現状の full run は Compute 契約不整合を解消できず、遅くとも Step 4.3 の workflow pre-flight で fail-closed** します。
>   エンドツーエンド完了可能とは扱いません。
>   本ガイドは local checkpoint と実装済み Step の実行・検証方法、およびこのブロッカーを正直に記載します。

## 対象読者

- [AAD-WEB](./03-app-design-microservice-azure.md) の設計成果物から Web アプリを実装する開発者
- Data / Compute / UI の RED → GREEN → Deploy → Post-deploy を運用する担当者
- ASDW-WEB の Step、Prompt、テンプレート、I/O 契約、Skill、テストを保守する開発者

<a id="asdw-web-start-conditions"></a>

## AAD-WEB からの前提

ASDW-WEB は AAS、ARD／既存要件、AAD-WEB の成果物を再生成せず、入力として使用します。

| 分類 | 必須成果物 |
|---|---|
| AAS カタログ | `docs/catalog/app-arch-catalog.md`, `docs/catalog/app-catalog.md`, `docs/catalog/domain-analytics.md`, `docs/catalog/service-catalog.md`, `docs/catalog/data-model.md`, `docs/catalog/service-catalog-matrix.md`, `docs/catalog/test-strategy.md` |
| ARD／既存要件 | `docs/catalog/use-case-catalog.md` |
| AAD-WEB 画面 | `docs/catalog/screen-catalog-APP-*.md`, `docs/screen/*-description.md` |
| AAD-WEB サービス | `docs/services/*-description.md` |
| AAD-WEB TDD 仕様 | `docs/test-specs/{serviceId}-test-spec.md`, `docs/test-specs/{screenId}-test-spec.md` |
| データ件数契約 | `src/data/sample-data.json` |
| Agentic Retrieval を有効にする場合 | `docs/services/{serviceId}-agentic-retrieval-spec.md` |

前提不足時は、成果物の生成元に応じて次の完了確認へ戻ってください。

| 不足している成果物 | 復旧先 |
|---|---|
| AAS カタログ、データ件数契約 | [AAS の完了確認](./02-app-architecture-design.md#completion-next-aas) |
| ARD／既存要件 | [ARD の完了条件](./01-business-requirement.md#完了条件) |
| AAD-WEB 画面、サービス、TDD 仕様、Agentic Retrieval 仕様 | [AAD-WEB の完了確認](./03-app-design-microservice-azure.md#aad-web-completion) |

## 実行経路と現在状態

| 経路 | 状態 | 実装 |
|---|---|---|
| CLI | **現行 registry を実行可能** | `python -m hve orchestrate --workflow asdw-web` |
| GUI | **現行 registry を実行可能** | `python -m hve`。Step 一覧は registry から動的取得 |
| GitHub Actions Cloud | **実行可能**（ただし CLI / GUI と同じ Step 4.3 ブロッカーを踏みます） | `web-app-dev.yml` から Issue を作成し、dispatcher が `auto-app-dev-microservice-web-reusable.yml` を起動 |
| SDK Cloud Session | CLI / GUI 内の任意のセッション配置 | GitHub Actions Cloud Orchestrator とは別機能。詳細は [cloud-session.md](./cloud-session.md) |

Cloud では [`web-app-dev.yml`](../.github/ISSUE_TEMPLATE/web-app-dev.yml) と
[`auto-app-dev-microservice-web-reusable.yml`](../.github/workflows/auto-app-dev-microservice-web-reusable.yml) を使用します。
Step ID と依存は registry parity test で同期されます。

## 実行方法

### full run の計画確認

現行 DataDeploy 契約が対応する `APP-009` で dry-run します。

```bash
python -m hve orchestrate --workflow asdw-web --app-ids APP-009 --resource-group <RESOURCE_GROUP> --dry-run
```

dry-run は必須パラメータ、APP フィルタ、fan-out、DAG の計画表示までで終了し、
後段の runtime 入力成果物チェック、必須 Skill チェック、Prompt 実行は行いません。
Azure live 操作も行いません。通常実行時の hard pre-check を警告へ降格させない場合は `--strict` を使用します。
ルート Step の `consumed_artifacts` 不足も停止対象にする場合は、別設定 `HVE_REQUIRE_INPUT_ARTIFACTS=true` が必要です。

### local checkpoint まで

Azure live 操作前に、設計・テスト・API/UI 実装を生成できます。

```bash
python -m hve orchestrate --workflow asdw-web --app-ids APP-009 --resource-group <RESOURCE_GROUP> --steps 1.1,1.2,2.1,2.3,2.5,3.1,3.2,3.3,4.1,4.2 --strict
```

Step 4.2 完了が local generation checkpoint です。Agentic Retrieval を使わない場合は
`--enable-agentic-retrieval no` を追加でき、Step 2.5 / 2.6 は設定に従って無効化されます。

> [!WARNING]
> Step 2.1 の template / scoped I/O contract は `docs/azure/azure-services-compute.md` を必須入力としますが、
> current DAG でこのファイルを生成するのは後段の Step 3.1 です。本リポジトリの HEAD には既存ファイルがあるため
> 現在の APP-009 実行では参照できますが、AAD-WEB 成果物だけの clean な入力からは自己完結しません。
> registry / template / I/O contract が同期するまでは、この compute design を Step 2.1 の明示的な既存前提として扱い、
> 欠落時に追加サービス選定を完全実行できたと報告しないでください。

さらに、その既存 compute design の第一候補は Azure Container Apps / Container Apps Jobs です。
一方、Step 3.3 と Step 3.4 の Agent は `*-AzureFunctions` で固定されています。
この drift を解消するまでは、Step 3.3 / 3.4 を「compute design を実装した」と判定しないでください。

### full run

```bash
python -m hve orchestrate --workflow asdw-web --app-ids APP-009 --resource-group <RESOURCE_GROUP> --strict
```

> [!CAUTION]
> 現在は required static input `.github/workflows/azure-static-web-apps-app009.yml` が欠落しているため、
> Step 4.3 の workflow pre-flight で停止するのが正しい結果です。
> このファイルを Step 4.3 自身に生成させたり、missing secret を無視して GREEN 扱いしたりしないでください。

GUI は `python -m hve` から **Web App Dev & Deploy (ASDW-WEB)**、APP-ID、Resource Group、Step を選びます。
full run では APP-ID を `APP-009` 1件にしてください。Step 1.3 は runner の pre-session gate で他 APP-ID を拒否します。

## local-first / live-last DAG

ASDW-WEB は `max_parallel=1` です。DAG 上で同時に ready になる Step があっても、
初期実装は同一 worktree の競合を避けるため逐次実行します。

### local phase

```text
1.1 -> 1.2
1.1 -> 2.1 -> 2.3 -> 3.1 -> 3.2 -> 3.3 -> 4.1
2.1 -> 2.5
1.2 + 2.5 + 4.1 -> 4.2 checkpoint
```

local Step は `1.1, 1.2, 2.1, 2.3, 2.5, 3.1, 3.2, 3.3, 4.1, 4.2` です。

### live phase

```text
1.2 + 4.2 ─► 1.3
1.3 + 2.1 -> 2.2
2.2 + 2.3 -> 2.4
2.2 + 2.5 -> 2.6（設定で無効化可）
2.4 + 3.3 -> 3.4 -> 3.5
3.5 + 4.2 -> 4.3 -> 4.4
4.4 -> 5.1
4.4 -> 5.2
5.1 -> 5.3
5.2 -> 5.3
```

live Step は `1.3, 2.2, 2.4, 2.6, 3.4, 3.5, 4.3, 4.4, 5.1, 5.2, 5.3` です。
live Step だけが失敗した PR-enabled run では、HVE は local checkpoint 成果物を保持し、
auto-merge 対象外の draft PR として残せます。

## 現行 Step と成果物

| Phase | Step | Prompt | 主入力 | 主出力 / 完了判定 | 依存 |
|---|---|---|---|---|---|
| local / Data | 1.1 データストア選定 | `Dev-Microservice-Azure-DataDesign` | AAS data / service / domain / app catalog | `docs/azure/azure-services-data.md` | なし |
| local / Data RED | 1.2 verifier 生成 | `Dev-Microservice-Azure-DataTestCoding` | data design、app catalog、任意 sample data | `verify-data-resources.sh` + RED report + static log | 1.1 |
| live / Data GREEN | 1.3 DataDeploy | `Dev-Microservice-Azure-DataDeploy` | design、matrix、sample data、verifier | HVE-owned `prep → create → registration → verify`、AC-1 GREEN | 1.2, 4.2 |
| local / Additional | 2.1 追加サービス選定 | `Dev-Microservice-Azure-AddServiceDesign` | use case / service / data design、既存 compute design（既知 drift） | `docs/azure/azure-services-additional.md` | 1.1 |
| live / Additional | 2.2 追加サービス Deploy | `Dev-Microservice-Azure-AddServiceDeploy` | additional design、app catalog | prep/create scripts、reality AC | 1.3, 2.1 |
| local / Additional RED | 2.3 テスト生成 | `Dev-Microservice-Azure-AddServiceTestCoding` | additional design、app catalog | `src/test/integration/add-service/` | 2.1 |
| live / Additional GREEN | 2.4 テスト実施 | `Dev-Microservice-Azure-AddServiceTesting` | deployed service + integration tests | 実 integration test 結果 | 2.2, 2.3 |
| local / Retrieval | 2.5 Azure 実装設計 | `Dev-Microservice-Azure-AgenticRetrievalDesign` | AAD retrieval spec / additional design | `docs/azure/agentic-retrieval/{serviceId}-design.md` | 2.1、設定で無効化可 |
| live / Retrieval | 2.6 Deploy | `Dev-Microservice-Azure-AgenticRetrievalDeploy` | retrieval design | KB / KS deploy scripts、AC4B reality gate | 2.2, 2.5、設定で無効化可 |
| local / Compute | 3.1 コンピュート選定 | `Dev-Microservice-Azure-ComputeDesign` | planned data design + AAS catalogs | `docs/azure/azure-services-compute.md` | 2.3 |
| local / API RED | 3.2 サービステスト生成 | `Dev-Microservice-Azure-ServiceTestCoding` | AAD service test spec / service definition | `src/test/api/{serviceId}.Tests/` + RED report | 3.1、サービス fan-out |
| local / API GREEN | 3.3 Azure Functions 実装 | `Dev-Microservice-Azure-ServiceCoding-AzureFunctions` | RED tests + service spec | `src/api/{serviceId}-{serviceNameSlug}/` + GREEN report。compute design の Container Apps 選定とは不一致 | 3.2、サービス fan-out |
| live / Compute | 3.4 Azure Functions Deploy | `Dev-Microservice-Azure-ComputeDeploy-AzureFunctions` | service code / catalogs | API deploy scripts + Step 専用 remote CI/CD。選定済み Compute を動的実装する経路ではない | 2.4, 3.3 |
| live / Compute verify | 3.5 Post-deploy | `Dev-Microservice-Azure-ComputePostDeployTest` | deployed endpoint / API tests | 実 endpoint smoke log、任意 `src/test/post-deploy/` | 3.4 |
| local / UI RED | 4.1 UI テスト生成 | `Dev-Microservice-Azure-UITestCoding` | AAD screen test spec / screen definition | `src/test/ui/{screenId}/` + RED report | 3.3、画面 fan-out |
| local / UI GREEN | 4.2 UI 実装 | `Dev-Microservice-Azure-UICoding` | RED UI tests / screen catalogs | `src/app/` + GREEN report | 1.2, 2.5, 4.1。checkpoint |
| live / UI | 4.3 SWA Deploy | `Dev-Microservice-Azure-UIDeploy-AzureStaticWebApps` | `src/app/package.json`、既存 SWA workflow | create/verify/switch/rollback、AC-1/6/8 | 3.5, 4.2 |
| live / UI verify | 4.4 Playwright E2E | `E2ETesting-Playwright` | SWA URL / screen test specs | Playwright log、失敗時 HTML / trace | 4.3 |
| live / Review | 5.1 WAF review | `QA-AzureArchitectureReview` | Azure design + deployed resources | `docs/azure/azure-architecture-review-report.md` | 4.4 |
| live / Review | 5.2 dependency review | `QA-AzureDependencyReview` | catalogs + `src/api`, `src/app` | `docs/azure/dependency-review-report.md` | 4.4 |
| live / Review | 5.3 requirements conformance measurement | `QA-RequirementsConformanceEval` | 5.1 / 5.2 reports + deployed endpoints + existing test assets | `docs/azure/requirements-conformance-report.md` | 5.1, 5.2 |

Step 3.5 のテンプレートには「Agent は最小スタブ」という古い注記が残っていますが、
現行 [`Dev-Microservice-Azure-ComputePostDeployTest.prompt.md`](../.github/prompts/Dev-Microservice-Azure-ComputePostDeployTest.prompt.md)
には実環境 smoke 契約が実装されています。Category 属性が Step 3.2 のテストに無い場合は、
Prompt 契約どおり Step 3.5 を blocked とし、モックテストを実環境 PASS と偽りません。

## TDD RED / GREEN 契約

### 共通証跡

TDD Step は実行ごとに次へ記録します。

`tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`

- `Workflow`, `Step`, `Agent`, `Target-Key`, `Phase`, `Evidence-Status`, `TDD-Judgement`,
   `Secret-Redaction`, `Test-Files-Changed` を固定ラベル形式で記録します。
- RED の `TDD-Judgement: PASS` は「テストが通った」ではなく、**期待した RED を実出力で証明できた**ことを表します。
- GREEN は RED と同じ検証を緩めず再実行します。テスト側 / 共有設定側の確定ブロッカーだけ
   `BLOCKED` を許容し、自 Step の実装未達は `FAIL` です。
- GREEN Step は原則テストコードを変更せず、実装だけで GREEN 化します。
- 秘密情報、接続文字列、SAS、Function Key、Bearer token をテスト・README・ログへ記録しません。

固定スキーマの正本は
[`tdd-red-green-reality`](../.github/skills/testing/tdd-red-green-reality/SKILL.md)、
gate は [`hve/runner.py`](../hve/runner.py)、契約テストは
[`test_runner_tdd_report_gate.py`](../hve/tests/test_runner_tdd_report_gate.py) です。

### Data Step 1.2 / 1.3

- Step 1.2 は Azure live 操作を行わず、読み取り専用 verifier を生成します。
- RED report は `Artifact-Contract-Status`, `Live-RED-Status`, `Focused-Regression-Status` を分離します。
   controlled / offline 生成では `Live-RED-Status: NOT_RUN` が正しく、static PASS を live RED と偽りません。
- `static-verification.log` の実在と `Raw-Log-Path` 一致が gate されます。
- Step 1.3 は HVE-owned fixed pipeline `prep → create → registration → verify` だけを使い、
   Agent が producer を手修正・直接実行しません。
- GREEN 未達は `ac-verification.md` の AC-1 `❌` と `TDD-Judgement: BLOCKED` を残し、
   reality gate が Step を fail にします。

### API / UI

- Step 3.2 → 3.3: ローカル xUnit の RED → Azure Functions 最小実装 → 同じ `dotnet test` の GREEN。
- Step 4.1 → 4.2: Jest/jsdom 等の canonical UI tests → 最小 UI 実装 → 同じテストの GREEN。
   再実行時に実装が既存なら canonical suite が最初から PASS し得るため、RED 専用の捏造テストを追加しません。
- Step 3.4 / 3.5 と Step 4.3 / 4.4 は外部環境検証です。endpoint / base URL / 認証が未設定なら
   環境ブロッカーであり、未実行を PASS にしません。

## Azure Functions / Static Web Apps / OIDC

- GitHub Actions の Azure OIDC ログインには `permissions: id-token: write` と `azure/login` が必要です。
   `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` は資格情報そのものではありませんが、
   GitHub の secrets / variables と federated credential の subject を一致させます。
- Azure Functions の CD は、OIDC ログイン後に `Azure/functions-action` で package を deploy する構成が公式例です。
- Static Web Apps の `Azure/static-web-apps-deploy` は deployment token を受け取ります。
   HVE の Step 4.3 契約は、OIDC で Azure にログインし、`az staticwebapp secrets list` で token を実行時取得し、
   action へ渡す方式です。**OIDC が deployment token 自体を不要にするわけではありません。**
- deployment token をリポジトリ、ログ、手動固定 Secret に保存しません。
- OIDC trust は repository / branch / environment 等の claim 条件で絞ります。2026-07-15 以降に作成、rename、transfer された
   repository は immutable subject claim を使用し得るため、実際の claim と Azure federated credential を照合します。

## 失敗時の対応

| 症状 | 原因 / 判定 | 対応 |
|---|---|---|
| Step 1.3 が session 前に停止 | APP-ID が `APP-009` 単一スコープでない | full run は `APP-009` 1件で実行。他 APP 汎用化済みとみなさない |
| dry-run で parameter blocked | Step 1.3 required parameter 不足 | dry-run の最初の不足 parameter を解消。runtime input / Skill の検査結果とはみなさない |
| 通常実行の pre-check が blocked | required input / required Skill 不足 | `--strict` 付き通常実行の最初の欠損を解消。未設定を推測しない |
| Step 2.1 で compute design がない | producer の Step 3.1 が後段にある既知 contract drift | `docs/azure/azure-services-compute.md` を既存前提として確認。欠落時は完全実行を主張せず、registry / template / I/O contract の同期を別変更で行う |
| Step 3.3 / 3.4 が compute design と不一致 | design は Container Apps、Agent 経路は Azure Functions 固定 | Functions を選定済み Compute と偽らない。Container Apps 実装経路または設計との整合を別変更で実装・検証する |
| TDD Step が fail | report 欠落、固定ラベル不正、GREEN が FAIL、Step 1.2 三状態不一致 | 対応 target の report と raw log を修正し、focused contract test を再実行 |
| live Step だけ失敗 | Azure / GitHub / endpoint reality 未達 | local checkpoint を保持し、draft PR の failure evidence から再開。auto-merge しない |
| Step 3.5 blocked | endpoint / auth 不明、または API tests に post-deploy 用 Category がない | Step 3.4 の実 endpoint 根拠を補う。Category 不足は Step 3.2 契約側へフィードバック |
| Step 4.3 が pre-flight / contract 失敗 | SWA workflow が default branch にない、または required D15 がない | deploy へ進まない。repository-managed workflow と D15 契約を別の許可された変更で実装・検証後に再実行 |
| Step 4.4 が blocked | `E2E_BASE_URL` も catalog URL も取得不能 | SWA URL の根拠を補い、秘密情報を除いた Playwright artifact で再試行 |
| Cloud Issue が起動しない | trigger/state ラベルまたは dispatcher routing 不整合 | `auto-app-dev-microservice-web` と `asdw-web:*` ラベル、dispatcher 実行ログを確認 |

<a id="asdw-web-completion"></a>

## 完了確認

### local checkpoint

- Agentic Retrieval 有効時は local Step 10件、無効時は Step 2.5 を除く9件が完了し、`src/api/`, `src/app/`, `src/test/` の成果物が存在する。
- Step 1.2 / 3.2 / 3.3 / 4.1 / 4.2 の target 別 TDD report が gate を通る。
- local Step が live Step の成果物を必須入力にしていない。

### full completion

- Step 3.1 の compute design と Step 3.3 / 3.4 の実装・デプロイ先が一致する。
- Data / Additional / Retrieval（有効時）/ Compute / UI の reality AC が GREEN。
- Post-deploy と Playwright が実 endpoint で PASS。
- `docs/azure/azure-architecture-review-report.md` と `docs/azure/dependency-review-report.md` が存在する。
- CLI 終了コードが 0、failed / blocked Step が 0。

現状は Compute 選定・実装 drift、SWA workflow 欠落、Step 4.3 required D15 欠落により
full completion 条件を満たせません。これらを無視した完了報告は禁止です。

## HVE カスタマイズ正本

| 変更したい内容 | 正本 | 同時に確認するもの |
|---|---|---|
| Step、DAG、local/live、fan-out、必須 parameter、reality AC | [`hve/workflow_registry.py`](../hve/workflow_registry.py) の `ASDW_WEB` | `hve/tests/test_workflow_registry.py`, `test_orchestrator_local_checkpoint_retention.py`, `test_asdw_web_production_path.py` |
| Step 本文 | [`.github/scripts/templates/asdw-web/`](../.github/scripts/templates/asdw-web/) | [`hve/template_engine.py`](../hve/template_engine.py), template dependency tests |
| Agent 行動、禁止、DoD | [`.github/prompts/`](../.github/prompts/) の `Dev-Microservice-Azure-*`, `E2ETesting-Playwright`, `QA-Azure*` | [`hve/prompt_loader.py`](../hve/prompt_loader.py), `hve/tests/test_prompt_loader.py` |
| 座標別 input / output / producer | [`.github/io-contracts/`](../.github/io-contracts/) の `*--asdw-web--<step>.yaml` | `.github/scripts/validate-io-contract.py`, `hve/tests/test_tdd_report_io_contract.py` |
| TDD report / reality gate | [`tdd-red-green-reality`](../.github/skills/testing/tdd-red-green-reality/SKILL.md), [`hve/runner.py`](../hve/runner.py), [`hve/artifact_validation.py`](../hve/artifact_validation.py) | `hve/tests/test_runner_tdd_report_gate.py`, deploy gate tests |
| Required / optional Skill | [`hve/skill_manifest.json`](../hve/skill_manifest.json) と Step の `required_skills` | [`hve/skill_resolver.py`](../hve/skill_resolver.py), `hve/tests/test_skill_resolver.py` |
| Step 単位 remote CI/CD | [`hve/orchestrator.py`](../hve/orchestrator.py), [`github-actions-cicd`](../.github/skills/cicd/github-actions-cicd/SKILL.md) | `hve/tests/test_asdw_web_step_scoped_cicd_contract.py` |
| Cloud parity / dispatch | [`auto-orchestrator-dispatcher.yml`](../.github/workflows/auto-orchestrator-dispatcher.yml), [`auto-app-dev-microservice-web-reusable.yml`](../.github/workflows/auto-app-dev-microservice-web-reusable.yml) | `hve/tests/test_cloud_reusable_workflow_parity.py`, `test_cloud_dispatcher_asdw_dispatch.py` |

Runtime では [`hve/runner.py`](../hve/runner.py) が Step Prompt の先頭へ Agent Prompt を注入し、
manifest と Step 宣言から Skill を解決します。registry / template / Prompt / I/O contract / Skill / test の
どれか1面だけを変更しないでください。

## 公式出典

| Title | URL | 本ガイドで確認した主張 |
|---|---|---|
| Deploy to Azure Functions by using GitHub Actions | <https://learn.microsoft.com/azure/azure-functions/functions-how-to-github-actions> | user-assigned managed identity + federated credential、`id-token: write`、`azure/login`、`Azure/functions-action` |
| Build configuration for Azure Static Web Apps | <https://learn.microsoft.com/azure/static-web-apps/build-configuration> | `.github/workflows` の build/deploy 設定、`Azure/static-web-apps-deploy` と deployment token |
| Deploy a static web app with Azure Static Web Apps CLI | <https://learn.microsoft.com/azure/static-web-apps/static-web-apps-cli-deploy> | `az staticwebapp secrets list` による token 取得、token を公開リポジトリへ保存しないこと |
| Configuring OpenID Connect in Azure | <https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-azure> | Azure OIDC の trust、`id-token: write`、`azure/login` |
| OpenID Connect reference | <https://docs.github.com/en/actions/reference/security/oidc> | `aud` / `sub` 条件、reusable workflow claim、immutable subject claim |
| Reuse workflows | <https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows> | reusable workflow は `on.workflow_call` で定義し、job の `uses` から呼ぶこと |
