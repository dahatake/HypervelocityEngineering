{root_ref}
## 目的
TDD GREEN フェーズ: Agent 詳細設計書から AI Agent を実装し、全テストを PASS させる。
Microsoft Foundry（Azure AI Foundry Agent Service）を使用して Agent を実装する（APP-ID 指定時はスコープ内の Agent のみ）。

## 重要
- **Azure AI Foundry Agent Service** を使用する
- チュートリアル参照: https://learn.microsoft.com/ja-jp/azure/foundry/quickstarts/get-started-code?tabs=python
  - ⚠️ チュートリアルのコードをそのままコピーしない
- **ユーザーが指定したプログラミング言語で最新の SDK** を使用する
  - Python: `azure-ai-projects`（最新版）
  - C#: `Azure.AI.Projects`（最新版）
- `DefaultAzureCredential` を使用して Azure に認証する

## 入力
- `docs/agent/agent-detail-*.md`（Agent 詳細設計書）
- `docs/AI-Agents-list.md`
- TDD テストコード（RED状態）: `test/agent/{AgentName}.Tests/`
- TDD テスト仕様書: `docs/test-specs/{agentId}-test-spec.md`
- `docs/service-catalog.md`
- `docs/azure/AzureServices-services-additional.md`
- `docs/app-list.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `src/agent/{AgentID}-{AgentName}/`

## TDD GREEN フロー（反復）
1. テストが全て FAIL（RED 状態）であることを確認する
2. 最小限の Agent 実装を作成する
3. テストを実行する
4. 全テスト PASS なら REFACTOR へ進む。FAIL があれば実装を修正して手順3に戻る
5. 最大 5 回反復する
6. 5 回で全 PASS にならない場合: `asdw:blocked` ラベルを付与し、未 PASS テスト一覧を報告する

## Custom Agent
`Dev-Microservice-Azure-AgentCoding` を使用

## 依存
- Step.2.7TC（AI Agent テストコード生成）が `asdw:done` であること

## 完了条件
- `src/agent/` 配下に Agent 実装コードが存在する
- テストの全テストが PASS であること（TDD GREEN 確認）
- 完了時に自身に `asdw:done` ラベルを付与すること{app_id_section}{additional_section}