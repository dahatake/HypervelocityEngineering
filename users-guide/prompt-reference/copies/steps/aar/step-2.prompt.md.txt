{root_ref}

{app_arch_scope_section}
## 目的
Step.1 の製品非依存 Agentic Retrieval 仕様を入力に、サービス単位の **Azure 実装設計書**を作成する。

## 検索契約（AR-CAP-01〜05・必須）
Skill `agentic-retrieval-contract` に従い、設計書の第 8 章に AR-CAP-01〜05 の固定見出しを記載する。

- `8.1 Knowledge Base Contract (AR-CAP-01)` / `8.2 Knowledge Source Matrix (AR-CAP-02)` / `8.3 Retrieval Budget (AR-CAP-03)` / `8.4 Evidence & Observability (AR-CAP-04)` / `8.5 MCP Exposure (AR-CAP-05)`
- 見出しレベルは第 8 章と同じにする（子レベルにしない）。同 Skill の「見出しレベル規約」に従う。
- 整合ルール R1〜R12 を自己検査し、結果を完了報告の検証結果へ含める。
- **複数データソース横断**は 1 つの Knowledge Base に複数 Knowledge Source を束ねて表現する。Knowledge Source ごとに別 Tool を作って Agent に複数回呼ばせる設計にしない。
- **クエリ回数とトークンの最小化**は `Retrieval reasoning effort` と `alwaysQuery` / `retrievalInstructions` で制御し、根拠を AR-CAP-01 / AR-CAP-03 に残す。

## 入力
- リソースグループ名: `{resource_group}`
- `docs/catalog/app-catalog.md`
- `docs/catalog/service-catalog.md`
- `docs/services/{serviceId}-agentic-retrieval-spec.md`（Step.1 出力）

## 出力
- `docs/azure/agentic-retrieval/{serviceId}-design.md`
- `docs/azure/agentic-retrieval/{serviceId}-design.md`

本 Step はサービス単位で並列実行される。`docs/azure/azure-services-additional.md` のような
共通カタログへは**書き込まないこと**（並列実行時に他サービスの追記を破壊するため）。

## 本ワークフロー固有の前提
- 既存の API / データストアへ**接続する**設計にする。データストアの新規作成を前提にしない。
- 既存資産を Knowledge Source 化する方式（Indexer / Push / 直接参照）の選択根拠を残す。

- Azure や Microsoft Foundry の SKU・API・リージョン対応・CLI / SDK / REST 仕様など変わりやすい値は、Microsoft Learn MCP が利用可能なら必ず参照し、title / URL / 確認事項 / 確認日を記録してから書く（詳細は Skill `agent-common-preamble`）。参照できない値は `要確認（Microsoft Learn MCP 未取得）` と記録し、推測で確定しない。

{existing_artifact_policy}

## Custom Agent
`Dev-Microservice-Azure-AgenticRetrievalDesign` を使用

## 依存
- Step.1（Agentic Retrieval 機能要件詳細）が `aar:done` であること

## 完了条件
- 対象サービスごとに `docs/azure/agentic-retrieval/{serviceId}-design.md` が作成されている
- AR-CAP-01〜05 が固定見出しで記載され、R1〜R12 の自己検査結果が報告されている
{completion_instruction}{app_id_section}{additional_section}
