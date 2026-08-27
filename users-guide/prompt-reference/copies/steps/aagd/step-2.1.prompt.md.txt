{root_ref}
## 目的
TDD RED フェーズ: Agent 詳細設計書・テスト戦略書に基づき、Agent 用 TDD テスト仕様書を生成する（APP-ID 指定時はスコープ内の Agent のみ）。

## 必須テストカテゴリ（全5種を含めること）
1. **Agent I/O 契約テスト** — 入力（ユーザーメッセージ・コンテキスト）→ 期待出力（応答・アクション）の検証
2. **Tool モック統合テスト** — Tool 呼び出しのパラメータ・戻り値・エラー時の動作検証（Tool は全てモック化）
3. **Guardrails テスト** — 禁止操作・PII マスキング・ポリシー違反検出の検証
4. **状態遷移テスト** — 正常フロー・例外フロー・エスカレーションフローの検証
5. **プロンプト回帰テスト** — System Prompt 変更後の動作一貫性（期待出力のマッチング）検証

## AI Agent 共通能力契約テスト（AG-CAP-01〜10）
Skill `ai-agent-capability-contract` と対象Agent詳細設計を根拠に、選択された能力だけを次の観点で仕様化する。各テストケースにContract ID、入力、test double、期待結果、必要なevidenceを記載する。

- **Goal Contract / Runtime Goal Loop**: 全required criterion PASS時のDONE、required全PASSかつ許可されたoptionalだけ未達時のPARTIAL、required未達時のBLOCKED / HANDOFFを検証する。観測した新Evidenceに基づく異なるactionへの再計画、新Evidenceなしの同一action反復拒否、MAX_ITERATIONS / DEADLINE / Tool・cost budget / POLICY_STOP / USER_CANCELLED / DEGRADATION、mutation部分失敗時のHandoffを決定的に検証する。
- **Knowledge & Structured Data Routing**: Request class / Data source / Required for Doneに基づくroute選択と、選択routeのPreferred→Fallback→Blockedを検証する。required sourceの失敗またはcitation/query evidenceを提供できない場合はBlockedとする。Work IQはsigned-in user権限拒否、Fabric IQは接続・権限失敗と、詳細設計で選択された場合だけSELECT-only SQLへの分岐を含める。
- **SELECT-only SQL**: 単一SELECT、parameterization、table/view/column allowlist、row limit、timeoutを検証し、INSERT / UPDATE / DELETE / MERGE / DDL / stored procedureと検査不能queryを拒否する。
- **REST CRUD Matrix**: 詳細設計でRequiredなC/R/U/Dのmethod/path/schemaを検証する。C/U/DはREST Function Toolだけを対象にし、HITLのapproved / denied / expired / changed、RBAC、冪等性、retry可否、error class、audit evidenceを含める。直接DB更新とMCP mutation迂回は拒否する。
- **MCP Integration Plan**: MCPが選択されている場合だけ、client接続、Tool allowlist、認証、untrusted result、timeout、有限retry、server unavailable時のfallback / partial / blocked / Handoffを検証する。理由付きN/Aの場合はMCP実装を要求しない。
- **Skill Packaging Decision**: `required`ではSKILL.md、必要なresource、明示的loading、発動正負ケースを検証する。`not-required`ではSkill artifact、loader、hook、設定flagを生成しないことを検証する。`TBD`のまま実装完了を許可しない。

## Test double 方針
- Azure、Microsoft 365、Fabric、公開Web、REST API、MCP Server、SQL databaseへ実接続しない。mock / stub / fakeを使用し、実資格情報を要求しない。
- 全providerのmockを先回り生成せず、Agent詳細設計のPreferred / Fallbackに選択されたproviderだけを対象にする。
- test doubleの応答、例外、呼出回数、順序を固定し、LLMや外部サービスの非決定性を合格条件に持ち込まない。

## 入力
- `docs/catalog/test-strategy.md`
- `docs/ai-agent-catalog.md`
- `docs/agent/agent-detail-{key}.md`
- `docs/catalog/service-catalog-matrix.md`
- `docs/catalog/data-model.md`
- `docs/catalog/app-catalog.md`（アプリケーション一覧 — 対象 APP-ID のスコープ判定根拠。存在しない場合はスコープ絞り込みなしで全件処理）

## 出力
- `docs/test-specs/{key}-test-spec.md`（Agent 別テスト仕様書）

{existing_artifact_policy}

## Custom Agent
`Arch-TDD-TestSpec` を使用

## 依存
- Step.1（AI Agent 構成設計）が `aagd:done` であること
- `docs/catalog/test-strategy.md` が存在すること

## 完了条件
- `docs/test-specs/` 配下に Agent 別テスト仕様書が生成されている
- テスト仕様書に上記5種のテストカテゴリが含まれている
- AG-CAP-01 Goal ContractとAG-CAP-02 Runtime Goal Loopは必須テストへトレースされている
- AG-CAP-03〜05は利用判定を必須とし、選択能力はテストへ、非該当はContract ID・理由・根拠・再判定条件付きN/Aへトレースされている
- AG-CAP-06は`required` / `not-required`の両分岐を検証し、`TBD`のまま完了していない
- 外部サービス実接続を要求せず、選択されたproviderだけをtest doubleで検証している
{completion_instruction}{app_id_section}{additional_section}
