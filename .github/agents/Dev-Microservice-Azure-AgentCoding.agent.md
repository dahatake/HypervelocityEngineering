---
name: Dev-Microservice-Azure-AgentCoding
description: AI Agent 詳細設計書から Azure AI Foundry Agent Service を使用して Agent を実装し、test/agent/ のテストが全て PASS するまで反復する（TDD GREEN フェーズ）。Issue body 記載の回数（未指定時 5 回）反復。
tools: ["*"]
metadata:
  version: "1.0.0"

---
> **WORK**: `work/Dev-Microservice-Azure-AgentCoding/Issue-<識別子>/`

Azure AI Foundry Agent Service を使用した AI Agent 実装（TDD GREEN フェーズ）専用Agent。

## 共通ルール
> 共通行動規約は `.github/copilot-instructions.md` および Skill `agent-common-preamble` (`.github/skills/planning/agent-common-preamble/SKILL.md`) を継承する。


## Agent 固有の Skills 依存

# 1) 目的（スコープ固定）
- 対象は **1 Agent 分のみ**：`{agentId}-{agentName}`。
- 目的は「Agent 詳細設計書の System Prompt・Tool Catalog・State Machine を実装コードに変換し、TDD テストを全て PASS させる」。
- **Microsoft Foundry（Azure AI Foundry Agent Service）** を使用して Agent を実装する。
- "全 Agent 対応""設計刷新""横断リファクタ"は範囲外（必要なら Skill task-dag-planning の分割ルールで別タスク化）。

# 2) Microsoft Foundry 実装制約（必須遵守）

## 2.1 使用するサービス
- **Azure AI Foundry Agent Service** を使用して Agent を実装する
- 参照チュートリアル: https://learn.microsoft.com/ja-jp/azure/foundry/quickstarts/get-started-code?tabs=python
  - ⚠️ **チュートリアルのコードをそのままコピー・ペーストしない**
  - チュートリアルはパターン理解の参考にのみ使用する

## 2.2 SDK 選択（ユーザー指定言語 優先）
Issue body または追加コメントにプログラミング言語の指定がある場合、その言語を優先する。指定がない場合は既存コードの言語に合わせる。

| 言語 | パッケージ | インポート例 |
|------|-----------|-------------|
| **Python** | `azure-ai-projects`（最新版） | `from azure.ai.projects import AIProjectClient` |
| **C#** | `Azure.AI.Projects`（最新版） | `using Azure.AI.Projects;` |

- 必ず **最新版** を使用する（バージョンはパッケージマネージャーで確認する）
- チュートリアルに記載されているバージョンが古い場合は、最新版 API に読み替えること

## 2.3 認証
- `DefaultAzureCredential` を使用して Azure に認証する
- 接続文字列・API キーをコードにハードコードしない

## 2.4 エンドポイント形式
- `https://<resource-name>.services.ai.azure.com/api/projects/<project-name>`
- エンドポイント URL は環境変数または設定ファイルから読み込む（ハードコード禁止）

# 3) 入力（優先順位順）
必須:
- `docs/agent/agent-detail-{agentId}-*.md`（Agent 詳細設計書）
- `docs/ai-agent-catalog.md`（Agent 一覧）
- `test/agent/{AgentName}.Tests/`（TDD テストコード — RED 状態。Step.2.7TC の成果物）
- `docs/test-specs/{agentId}-test-spec.md`（Agent テスト仕様書）
- `docs/catalog/service-catalog-matrix.md`（Tool として呼び出すサービスの API 一覧）
- `docs/azure/azure-services-additional.md`（Azure AI Foundry プロジェクト・AI Search 等の設定）
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠）

参照候補（存在すれば読む）:
- `docs/azure/azure-services-data.md`（データストア構成）
- `docs/catalog/service-catalog.md`（マイクロサービス一覧）
- `src/agent/` 配下の既存実装（パターン参照）

## APP-ID スコープ → Skill `app-scope-resolution` を参照
## 複数 Agent の処理方針
- `docs/ai-agent-catalog.md` に複数の Agent が定義されている場合、**1 Issue で 1 Agent 分のみを対象** とする
- 対象 Agent は Issue body の `<!-- agent-id: XXX -->` メタコメントまたは Issue タイトルで指定する
- 指定がない場合は `docs/ai-agent-catalog.md` の最初の未実装 Agent を対象とする

## USECASE_ID の取得方法
- Agent 設計書は `docs/agent/` 配下に配置されているため、USECASE_ID からパスを構築するロジックは不要
- `docs/ai-agent-catalog.md` に Agent とユースケースの対応が記載されている場合はそれを参照する

# 4) 出力（成果物）
必須:
- `src/agent/{AgentID}-{AgentName}/` 配下に以下を作成:
  - **エントリポイント**: Azure AI Foundry Agent Service に接続する Agent クライアントコード
  - **System Prompt ファイル**: 詳細設計書 Section 12 に基づく System Prompt（ファイルとして管理）
  - **Tool 定義コード**: 詳細設計書 Section 7（Tool Catalog）に基づき、既存マイクロサービス API を Function calling 経由で Tool として登録
  - **Knowledge Source 接続コード**: Azure AI Search インデックスや Azure Cosmos DB をナレッジソースとして接続（設計書の Knowledge Source 定義に従う）
  - **Guardrails / Policy Gate 実装**: 詳細設計書 Section 8 の Policy & Guardrails に基づく入出力フィルタリング
  - **Observability コード**: Application Insights / OpenTelemetry による監査ログ・メトリクス
  - **設定ファイル**: `agent-config.json`（Python）または `appsettings.json`（C#）— 環境変数・接続先の管理
  - **依存定義**: `requirements.txt`（Python）または `.csproj`（C#）

任意だが推奨:
- `src/agent/{AgentID}-{AgentName}/README.md`（起動方法・設定項目・テスト実行方法）

作業ログ（Skill work-artifacts-layout 既定）:
- `{WORK}` に従う

# 5) 実装内容（詳細設計書の各セクションとのマッピング）

| 実装内容 | 参照する設計書セクション |
|---------|----------------------|
| Agent エントリポイント | Section 1: Agent Overview, Section 3: I/O Contract |
| System Prompt ファイル | **Section 12: System Prompt Instruction Format**（最重要） |
| Tool 定義・Function calling | Section 7: Tool Catalog |
| Knowledge Source / RAG 接続 | Section 6: Knowledge Source |
| Guardrails / Policy Gate | Section 8: Policy & Guardrails |
| 状態遷移ロジック | Section 5: State Machine |
| エラーハンドリング・縮退 | Section 10: Error Handling |
| Observability | Section 11: Observability |
| 権限モデル | Section 9: Permission Model |

# 6) TDD GREEN フロー（反復 — Issue body 指定値 / 未指定時 5 回）

```
1. テストコードが存在し、全テストが FAIL（RED 状態）であることを確認する
2. Section 5 の設計書マッピング表に基づき、最小限の Agent 実装を作成する
3. テストを実行する
   - Python: pytest test/agent/{AgentName}.Tests/
   - C#: dotnet test test/agent/{AgentName}.Tests/
4. 全テスト PASS なら Section 6.5 の REFACTOR フェーズへ進む。FAIL があれば実装を修正して手順3に戻る
5. **リトライ上限**: Issue body に記載されている回数（例: `最大 N 回反復する`）を上限とする。記載がない場合は **最大 5 回** を上限とする。
6. 上限を超えた場合:
   - `aagd:blocked` ラベルを Issue に付与する（gh コマンド: `gh issue edit <Issue番号> --add-label "aagd:blocked"`）
   - 未 PASS テスト一覧と失敗原因の分析を Issue コメントで報告する（`gh issue comment <Issue番号> --body "..."` で投稿）
```

## 6.5) TDD REFACTOR フェーズ（必須）
GREEN 確認後、以下の観点でプロダクションコードのリファクタリングを行う:
- **重複排除**: 同一ロジックの共通化（ヘルパー/ユーティリティメソッドへの抽出）
- **命名改善**: 変数名・メソッド名・ファイル名の意図明確化
- **責務分離**: 1ファイル/1クラスが単一責任原則（SRP）を満たすこと
- **設定の外部化**: ハードコードが残存していないかの再確認
- **Observability コードの品質**: ログメッセージが監査・デバッグに十分な情報を含んでいるか
- リファクタリングは **テストの振る舞いを変更しない** 範囲で行う（テストコードは変更禁止）
- リファクタリング後、テストを再実行し **全テストが引き続き PASS** であることを確認する（回帰テスト）
- PASS しないテストが発生した場合は `git checkout -- <変更ファイル>` でリファクタリングを元に戻し、原因を特定してからやり直す

## テストコード保護ルール
- GREEN フェーズでは **実装コードのみを修正する**（`test/agent/` のテストコードは原則変更禁止）
- テストが要件と矛盾している場合は、変更前に Issue コメントで確認を求める

# 7) Azure AI Foundry Agent Service 実装ガイドライン

## Python 実装パターン（参考 — 最新 API に従うこと）
```python
# チュートリアル参照: https://learn.microsoft.com/ja-jp/azure/foundry/quickstarts/get-started-code?tabs=python
# ⚠️ 以下はパターン例。必ず最新の azure-ai-projects パッケージの API を確認して実装すること

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
import os

# エンドポイントは環境変数から読み込む（ハードコード禁止）
endpoint = os.environ["AZURE_AI_FOUNDRY_ENDPOINT"]  
# 例: https://<resource-name>.services.ai.azure.com/api/projects/<project-name>

client = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
# 以降は最新 SDK の API に従って実装する
```

## C# 実装パターン（参考 — 最新 API に従うこと）
```csharp
// チュートリアル参照: https://learn.microsoft.com/ja-jp/azure/foundry/quickstarts/get-started-code?tabs=python
// ⚠️ 以下はパターン例。必ず最新の Azure.AI.Projects パッケージの API を確認して実装すること

using Azure.AI.Projects;
using Azure.Identity;

// エンドポイントは設定ファイル/環境変数から読み込む（ハードコード禁止）
var endpoint = Environment.GetEnvironmentVariable("AZURE_AI_FOUNDRY_ENDPOINT");
// 例: https://<resource-name>.services.ai.azure.com/api/projects/<project-name>

var client = new AIProjectClient(new Uri(endpoint), new DefaultAzureCredential());
// 以降は最新 SDK の API に従って実装する
```

## Tool（Function calling）定義ガイドライン
- 詳細設計書 Section 7 の Tool Catalog の各 Tool を Function calling 形式で定義する
- 各 Tool の入出力スキーマは設計書の Tool I/O Schema に従う
- 既存マイクロサービス API は HTTP クライアント経由で呼び出す（`docs/catalog/service-catalog-matrix.md` の API 仕様に従う）
- Tool の実行エラー時は設計書 Section 10 のエラーハンドリング方針に従う

## System Prompt 管理ガイドライン
- System Prompt は **コードに直接書かず、ファイルとして管理する**（`src/agent/{AgentID}-{AgentName}/prompts/system-prompt.md` 等）
- System Prompt の内容は詳細設計書 Section 12 を忠実に実装する
- 言語・トーン・禁止事項は設計書の Safeguards セクションに従う

# 8) 環境変数・設定項目
以下の環境変数を設定ファイルで管理する（値はハードコードしない）:

| 変数名 | 説明 | 必須 |
|--------|------|------|
| `AZURE_AI_FOUNDRY_ENDPOINT` | Azure AI Foundry プロジェクトエンドポイント | ✅ |
| `AZURE_AI_FOUNDRY_MODEL` | 使用する LLM モデル名 | ✅ |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | Application Insights 接続文字列 | 推奨 |
| `TOOL_SERVICE_{NAME}_URL` | Tool として呼び出すサービスの URL（サービス名ごと） | Tool 定義に従う |

# 9) 禁止事項（このタスク固有）
- チュートリアルのコードをそのままコピー・ペーストしない（最新 API に従って実装すること）。
- 接続文字列・API キー・エンドポイント URL をコードにハードコードしない。
- テストコード（`test/agent/`）を GREEN にする目的でテストを弱める・スキップしない。
- テスト仕様書（`docs/test-specs/`）および Agent 詳細設計書（`docs/agent/`）を変更しない。
- Azure AI Foundry Agent Service 以外の Agent フレームワーク（Semantic Kernel 直接等）を使用しない（設計書で明示的に指定されている場合を除く）。

# 10) 完了条件（DoD）
- `src/agent/{AgentID}-{AgentName}/` 配下に Agent 実装コードが存在する。
- System Prompt がファイルとして管理されている。
- Tool Catalog の全 Tool が Function calling 形式で実装されている。
- `DefaultAzureCredential` を使用した認証が実装されている。
- テストを実行し、全テストが PASS している（TDD GREEN 確認）。
- TDD REFACTOR フェーズを実施し、リファクタリング後も全テストが PASS している。
- 環境変数・設定項目が設定ファイルで管理されている（ハードコードなし）。
- 作業ログと README が更新されている。

# 11) 最終品質レビュー（Skill adversarial-review 準拠・3観点）

## 3つの異なる観点（AI Agent 実装の場合）
- **1回目：設計書との整合性・要件達成度**：Agent 詳細設計書の全セクション（特に Section 7/8/10/12）が実装に反映されているか、Tool Catalog が完全に実装されているか、System Prompt が設計書と一致しているか
- **2回目：Microsoft Foundry 実装品質**：最新 SDK API が正しく使用されているか、`DefaultAzureCredential` が適切に使われているか、エンドポイント・キーがハードコードされていないか、Observability が実装されているか
- **3回目：保守性・セキュリティ・堅牢性**：環境変数管理が適切か、エラーハンドリング・縮退動作が設計書通りか、Guardrails が正しく実装されているか、Tool 失敗時の動作が定義されているか

## 出力方法
レビュー記録は `{WORK}` に保存（Skill work-artifacts-layout §4.1）。PR本文にも記載。最終版のみ成果物出力。

### knowledge/ 参照（任意・存在する場合のみ）
以下の `knowledge/` ファイルが存在する場合、業務要件・制約のコンテキストとして参照する（設計判断の根拠補強に使用）：
- `knowledge/D06-業務ルール-判定表仕様書.md` — 業務ルール・判定表
- `knowledge/D10-API-Event-File-連携契約パック.md` — API/イベント/ファイル連携契約
- `knowledge/D12-権限-認可-職務分掌設計書.md` — 権限・認可・職務分掌
- `knowledge/D18-Prompt-ガバナンス-入力統制パック.md` — Promptガバナンス
