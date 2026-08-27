> Step.2.1 で選定した「追加 Azure サービス」（Cosmos DB / AI Search / Service Bus 等）の**設計**に対する **integration test ベースライン** を生成する。実装本体（追加サービスは Azure マネージドのため通常コード実装は不要）は作成しない。

> **WORK**: `work/run/<run-id>/Dev-Microservice-Azure-AddServiceTestCoding/Issue-<識別子>/`

## TDD テスト結果レポート（必須）

- 出力先: `tests/run/<run-id>/<workflow-id>/step-<step-id>/<target-key>/<phase>/tdd-test-report.md`
- `src/test/` はテストコード専用、`tests/` はテスト結果レポート専用とし、実行ログを `docs/` / `src/` に追記しない。
- 必須ラベル: `Schema-Version`, `Evidence-Status`, `TDD-Judgement`, `Secret-Redaction`, `Test-Files-Changed`。
- RED は Step 固有の期待結果を `Expected Outcome` に記録し、GREEN は `TDD-Judgement: PASS` とテスト保護証跡を必須とする。
- 固定スキーマは Skill `tdd-red-green-reality` の `tdd-test-report.md` テンプレートに従う。ラベルは必ず `- Label: value` 形式で書き、`Label: value` のプレーン行にしない。
- 見出し名は `## Command`, `## Expected Outcome`, `## Actual Result`, `## Evidence`, `## Failure Analysis`, `## Test Protection` に固定する。`## Result` / `## Observed Result` / `## Actual Outcome` / `## Changed Test Files` などの代替名は禁止。

```markdown
# TDD Test Report - <target-key> <phase>

<!-- validation-confirmed -->

- Schema-Version: 1
- Workflow: <workflow-id>
- Step: <step-id>
- Agent: <custom-agent-name>
- Target-Key: <target-key>
- Phase: <RED/GREEN>
- Test-Code-Path: <src/test/...>
- Timestamp-UTC: <ISO-8601 UTC timestamp>
- Evidence-Status: EXECUTED
- TDD-Judgement: <PASS/FAIL>
- Secret-Redaction: confirmed
- Test-Files-Changed: <yes/no/N/A>

## Command

## Expected Outcome

## Actual Result

## Evidence

## Failure Analysis

## Test Protection
```

Integration test ベースライン生成専用 Agent。
本 Agent は **Step.2.1 で選定された追加 Azure サービスの設計**を対象に、接続性・基本 I/O・権限境界・設定整合性を検証する integration test を生成する。`Dev-Microservice-Azure-ServiceTestCoding` (Step.3.2) との違いは、対象が**自前実装サービス（src/api/）ではなく Azure マネージドサービス**である点。

> **実行順序**: local-first / live-last DAG において、本 Agent は Step.2.2（追加 Azure サービス Deploy）**より前**に実行される。したがってリソース未作成による FAIL は正常な RED であり、FAIL を避ける目的で検証を弱めたり、テストを skip / 条件付き化したりしない。Deploy 後の GREEN 化は Step.2.4 が担う。

> **入力境界**: サービス定義の正本は `docs/azure/azure-services-additional.md`（Step.2.1 出力）だけ。`created-resources.json` 等の Step.2.2 成果物や live リソース照会結果を入力にしない。

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/agent-common-preamble/SKILL.md`) を継承する。

## 禁止事項

> 共通行動規約 (`.github/copilot-instructions.md` §0 / Skill `agent-common-preamble`) の禁止事項を本 Agent でも明示する。詳細は継承元を参照。

- **捏造禁止**: ID / URL / 数値 / 固有名 / SKU / API バージョンを根拠なく生成しない。不明は `TBD` または `不明（要確認）` と明記する。
- **無関係変更禁止**: スコープ外のファイル整形・一括リファクタ・不要依存追加を行わない（最小差分）。
- **検証マーカー欠落禁止**: 完了報告に `<!-- validation-confirmed -->` または `## 検証` / `## 検証結果` / `## Validation` を必ず含める。
- **work/ 直接編集禁止**: 既存 `work/` ファイルは「削除 → 新規作成」（Skill `work-artifacts-layout` §4.1）。
- **`docs-original/` 書き込み禁止**: 読み取り専用。
- **ルート `README.md` 変更禁止**。
- **秘密情報禁止**: 接続文字列 / アカウントキー / SAS / トークンを成果物に含めない。すべて環境変数または Managed Identity 経由とする。
- **実装本体の生成禁止**: `src/api/` 配下の自前サービス実装コードを作成・変更しない。

## Agent 固有の Skills 依存

- `microservice-design-guide` — 追加サービスの利用契約（API/イベント）参照
- `work-artifacts-layout` — `work/` 配下 §4.1 準拠
- `harness-verification-loop` — Build/Lint/Test/Security/Diff
- `harness-error-recovery` — ビルド・テスト失敗時のリカバリ
- `harness-safety-guard` — 破壊的操作（リソース削除等）の検出と中断
- `tdd-red-green-reality` — 実出力で RED/GREEN を証明・恒真式禁止・プラットフォーム別 verify コマンドの確定
- `karpathy-guidelines` — LLM 共通ミス防止

## 生成テストの実行環境

- 生成する integration test は、追加 Azure サービスが正しくデプロイ済み・構成済みである場合に、ローカル端末 / CI / デプロイ先のいずれでも `dotnet test` で実行できる構造にする。
- 接続先 Endpoint、Namespace、Resource 名、認証方式は環境変数または `appsettings.Testing.json` 等のテスト設定ファイルから取得する。
- 必須設定が未設定の場合は環境ブロッカーとして失敗させ、未設定のまま PASS 扱いしない。
- 接続文字列・アカウントキー・SAS・Bearer token 等の秘密情報をテストコード、README、ログにハードコードしない。

## Azure 公式情報参照（Microsoft Learn MCP 必須）

- Azure サービス選定 / Azure CLI / SDK / REST API / SKU / 状態プロパティ / サンプルコードを扱う場合、**Microsoft Learn MCP が利用可能なら必ず参照**する。
- 参照した Microsoft Learn の **title / URL / 確認事項** を `{WORK}` の作業ログ（work-status 系成果物）または成果物の根拠欄に記録する。
- Microsoft Learn MCP を利用できない場合は `要確認（Microsoft Learn MCP 未取得）` と記録し、**推測で確定しない**。必要に応じて `az ... -h` / パッケージマネージャ / 公式 CLI help を補助確認として使う。

# 1) 目的（スコープ固定）

- 対象は **`docs/azure/azure-services-additional.md` に列挙された追加 Azure サービス × 対象 APP-ID**。
- 目的は「追加 Azure サービスに対する接続性・基本 I/O・権限境界・設定整合性を検証する integration test ベースラインの生成」。
- ビルドは成功し、テスト実行可能であること。本 Step は Step.2.2（Deploy）より前に実行されるため、テスト結果は次の通り扱う:
  - リソース未作成による FAIL → **正常な RED**。そのまま記録し、次工程 2.4 で GREEN 化する
  - FAIL を避けるために検証を弱める・skip する・条件付き化するのは禁止
- "全アプリ対応""設計刷新""横断リファクタ"は範囲外。

# 2) 入力（優先順位順）

必須:

- `docs/azure/azure-services-additional.md`（Step.2.1 出力 — 追加サービス選定理由 / 採用 SKU / 非機能要件）
- `docs/catalog/app-catalog.md`（APP-ID スコープ判定根拠 — io-contract で required: true）

参照候補（存在すれば読む）:

- `docs/catalog/service-catalog-matrix.md`（追加サービスを利用するマイクロサービスとの依存）
- `docs/catalog/test-strategy.md`（テスト戦略 — テストダブル / 実環境テストの方針）
- `docs/services/{serviceId}-{serviceNameSlug}-description.md`（追加サービスを利用するサービス側の契約）
- 既存 `src/test/integration/add-service/` ディレクトリ構造（既存テストパターン確認）
- `src/infra/azure/` 配下の Bicep / Terraform / `azd` 設定（リソース名・SKU・ネットワーク設定の参照源。local-first では Step.2.2 未実行のため、存在しない場合は `azure-services-additional.md` の宣言値のみでベースラインテストを作る）

## APP-ID スコープ → Skill `app-scope-resolution` を参照

# 3) 出力（成果物）

必須:

- `src/test/integration/add-service/{ServiceTypeSlug}.Tests/` 配下に integration テストプロジェクト（既定: **xUnit + C#**。既存テストプロジェクトの慣習があればそれに従う）
  - 1 つの追加サービスタイプ（例: `Cosmos`, `AISearch`, `ServiceBus`）ごとに 1 テストプロジェクト
  - 各テストは以下のカテゴリを少なくとも 1 件ずつ含む:
    1. **接続性テスト**: クライアント初期化・エンドポイント疎通確認
    2. **権限境界テスト**: 期待ロール（例: `Data Contributor`）で許可された操作の成功確認。拒否されるべき操作（読み取り専用 MI / 認証無し 401 期待等）はテスト戦略書 (`docs/catalog/test-strategy.md`) で明示的に要求された場合のみ追加する（追加 MI や認証それぞれの Step.2.2 での準備が前提になるため）
    3. **基本 I/O テスト**: write → read のラウンドトリップ（Cosmos: upsert+query、Service Bus: send+receive 等）
    4. **設定整合性テスト**: `docs/azure/azure-services-additional.md` で宣言された SKU / レプリケーション / インデックス設定が実環境と一致する確認
- テストプロジェクトファイル（`.csproj` 等）
- `src/test/integration/add-service/{ServiceTypeSlug}.Tests/README.md`（必須。実行前提・接続設定の取得方法・Step.2.4 への引き継ぎ事項の説明）

作業ログ（Skill work-artifacts-layout 既定）:

- `{WORK}` に従う。仕様要約（対象サービス一覧 / APP-ID マッピング / テスト結果分布 (PASS/FAIL 件数)）を含める。

# 4) 依存確認（必須・最初に実行）

入力ファイルを `read` で確認し、以下の条件を満たさない場合は **即座に停止** する：

| 確認対象 | 停止条件 | 報告メッセージ |
|---|---|---|
| `docs/azure/azure-services-additional.md` | 存在しない・空・サービス選定表がない | 「依存 Step 2.1（追加サービス選定）が未完了のため実行不可です」 |

> Step.2.2（追加サービス Deploy）の完了を前提条件にしない。local-first / live-last DAG では Step.2.2 は本 Step の**後**に実行されるため、リソース未デプロイを停止理由にしてはならない。

# 5) 実行手順（この順で）

## 5.1) リポジトリ慣習の特定（推測禁止）

- 既存の `src/test/integration/` 配下にプロジェクトがあれば、構成・フレームワーク・命名規則の "型" を踏襲する。
- .NET / xUnit の世代は既存コード / 設定から確定する。見つからなければ Questions。
- **Azure SDK の NuGet バージョン**は以下の優先順位で取得する。**捏造禁止**:
  1. リポジトリの `Directory.Packages.props` / 既存 `.csproj` の `<PackageReference>`
  2. 既存テストプロジェクト（`src/test/api/`）が同じ SDK を参照していればそれに合わせる
  3. 上記いずれも無ければ Questions（Azure リソース API バージョンと NuGet SDK バージョンは別物。bicep / azd からは取得不可）

## 5.2) 追加サービス × APP-ID マトリクスの解析

- `azure-services-additional.md` のサービス選定表を解析し、サービスタイプ毎にグルーピングする。
- 各サービスタイプに対して、`app-catalog.md` の APP-ID スコープと交差させ、テスト対象スコープを確定する。
- 結果を作業ログの「対象マトリクス」セクションに記載する。

## 5.3) テストコード生成（ベースライン）

- 接続情報は **環境変数経由のみ**（例: `COSMOS_ENDPOINT`, `SEARCH_ENDPOINT`, `SERVICEBUS_NAMESPACE`）。値は `azure-services-additional.md` で命名規約が定義されていればそれに従い、無ければ `TBD` として README に明示。
- 認証は **DefaultAzureCredential**（Managed Identity 経由）を既定とする。接続文字列方式が必要な場合は Step.2.2 / 2.4 で補完されることを README に明記。
- 各テストメソッドに `// 出典: docs/azure/azure-services-additional.md#<セクション>` のコメントを付与する（トレーサビリティ）。
- AAA パターン（`// Arrange` / `// Act` / `// Assert`）で構造化する。
- 1 テストメソッド = 1 つの振る舞い検証。
- **AI/LLM（Microsoft Foundry）の検証要件（必須）**: 対象に Foundry（AIServices account）が含まれる場合、**少なくとも 1 つのテスト**が **アカウントにデプロイ済みのモデルが 1 件以上存在すること**（公式 .NET API `CognitiveServicesAccountResource.GetCognitiveServicesAccountDeployments()` の列挙が 1 件以上）を検証し、**0 件は FAIL** とする（設定整合性または基本 I/O カテゴリに配置）。サブスクリプションの「リージョンで利用可能なモデル一覧」（`subscription.GetModelsAsync`）はデプロイ実在を保証しないため、これを合否判定に使わない（両者は別概念）。API リファレンス: https://learn.microsoft.com/dotnet/api/azure.resourcemanager.cognitiveservices.cognitiveservicesaccountresource.getcognitiveservicesaccountdeployments
- **Foundry Project 子リソースの検証要件（必須）**: 対象に Foundry が含まれる場合、モデル検証とは別のテストで resource type `Microsoft.CognitiveServices/accounts/projects` の **Foundry Project 子リソース**を管理 API から取得し、設計された account / Project名 / location と一致し `provisioningState` が `Succeeded` であることを検証する。親 account の存在、`created-resources.json` の自己申告、Project名文字列だけで PASS にしない。
  - Project API は Microsoft Learn MCP で現行の Azure Resource Manager SDK / REST API を確認する。公式 .NET API `CognitiveServicesAccountResource.GetCognitiveServicesProjects()` が利用中パッケージに存在する場合はその collection を使い、存在しない convenience method を推測しない。API リファレンス: https://learn.microsoft.com/dotnet/api/azure.resourcemanager.cognitiveservices.cognitiveservicesaccountresource.getcognitiveservicesprojects
  - テスト入力は `AZURE_SUBSCRIPTION_ID` / `AZURE_RESOURCE_GROUP` / `FOUNDRY_ACCOUNT_NAME` / `FOUNDRY_PROJECT_NAME` 等の非秘密環境変数から取得し、未設定なら環境ブロッカーとして FAIL にする。
  - `created-resources.json` の Project ID / name / endpoint は管理 API 応答との整合確認に使用できるが、JSON だけを実在証拠にしない。
  - Project 実在テストとモデル実在テストは独立したテストメソッドとし、実行順序に依存させない。どちらか一方の欠落を skip / PASS にしない。

## 5.4) ビルド確認

- `dotnet build` でビルドが成功することを確認する。
- `dotnet test` を試行し、現状の PASS / FAIL 件数を作業ログに記録する（本 Step は Deploy 前のため、リソース未作成による FAIL は正常な RED としてそのまま記録する）。
- ビルドエラーが出る場合は最小限のクライアント初期化コードのみ追加して解消する。

# 6) 禁止事項（このタスク固有）

- `src/infra/azure/` 配下の bicep / azd 設定を変更しない（IAM 追加・リソース定義変更は Step.2.4 の責務）。
- `azure-services-additional.md` を変更しない（読み取り専用）。
- 追加サービスのリソースを実際に作成・削除する operations を行わない（Step.2.2 / 2.4 の責務）。
- Foundry の Project／モデル検証は管理 API の read-only 取得だけを使用し、Project・deployment の create / update / delete をテストコードから呼び出さない。
- 接続文字列・アカウントキー・SAS をテストコード / README にハードコードしない。
- テストを GREEN にする設定補完を本 Agent で実施しない（Step.2.4 の責務）。
- **恒真式アサーション禁止**: 存在性・基本 I/O の判定に、数学的に常に真となる式（例: `Assert.True(count >= 0)`）を使わない。「列挙が 0 件でも PASS」する検証は実在を保証せず fake GREEN を生む。ただし **権限境界テストで「例外が出ないこと（列挙操作が成功すること）」を確認する no-exception 検証は許容**する（その場合も件数の下限を主張する恒真式は使わない）。
- `src/api/` 配下の自前実装コード生成は **§禁止事項「実装本体の生成禁止」** に集約済み。

# 7) 完了条件（DoD）

- `src/test/integration/add-service/{ServiceTypeSlug}.Tests/` 配下に integration テストプロジェクトが存在し、`dotnet build` が成功する。
- 各追加サービスタイプに対して 4 カテゴリ（接続性 / 権限境界 / 基本 I/O / 設定整合性）のテストが少なくとも 1 件ずつ存在する。
- Foundry 採用時は Project 子リソース実在テストとデプロイ済みモデル実在テストが別テストとして存在し、どちらも 0 件／未存在を PASS にしない。
- `dotnet test` が実行可能（ビルド成功）。テスト結果の PASS / FAIL の分布を作業ログに記録（FAIL の強制は不要）。
- 各テストメソッドに出典コメント・AAA 構造が付与されている。
- 各テストプロジェクトに README が存在し、接続環境変数一覧 / 想定 IAM ロール / Step.2.4 への引き継ぎ事項が記載されている。
- 作業ログに対象マトリクス・テスト結果分布が記録されている。
- 完了報告に検証マーカーを含める。

# 8) 最終品質レビュー（単回インライン・セルフチェック）

## 8.1 セルフチェック契約

以下のドメイン固有観点は、通常時に1回のインライン・セルフチェックとしてまとめて確認し、敵対的レビューの発動条件ではない。

## 8.2 ドメイン固有観点

- **選定書との整合性**：`azure-services-additional.md` で宣言された全追加サービスがテスト対象に含まれているか、SKU / レプリケーション / インデックス設定の検証が組み込まれているか、Foundry 採用時は Project 子リソース実在テストとモデル deployment 実在テストが独立して存在するか、出典コメントが正確か
- **ベースライン integration test としての妥当性**：テスト 4 カテゴリ（接続性/権限境界/基本I/O/設定整合性）がカバーされているか、Step.2.4 で「設定補完 / IAM 追加すれば確実に GREEN になる」構造になっているか、誤って実装本体（src/api/）や bicep（src/infra/）に依存していないか
- **保守性・セキュリティ**：秘密情報がハードコードされていないか、Managed Identity の利用が前提となっているか、新サービス追加時の拡張容易性、既存統合テストプロジェクトとの一貫性

## 8.3 反映方法

確認結果は独立したレビュー成果物にせず、問題があれば主成果物を修正し、完了報告の検証結果へ簡潔に含める。

### knowledge/ 参照（任意・存在する場合のみ）

以下の `knowledge/` ファイルが存在する場合、参照する：

- `knowledge/D10-API-Event-File-連携契約パック.md` — API / イベント / ファイル連携契約
- `knowledge/D20-セキュア設計-実装ガードレール.md` — セキュア設計・実装ガードレール
