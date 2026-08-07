# AI Agent 共通能力契約

## 1. 目的

HVE の AAG / AAGD で設計・実装するアプリケーション AI Agent が、ユーザー目的、検索、業務操作、MCP、Skill、自己改善を一貫した契約として扱うための最小要件を定義する。

本契約は新しい Agent framework を定義しない。既存の Agent 詳細設計、Tool Catalog、State Machine、TDD、HVE gate に不足項目を追加する。

## 2. 適用範囲

### MUST

- AAG の Step 1〜3 で生成する Agent 設計。
- AAGD の Step 2.1〜3 で生成するテスト、Agent実装、デプロイ成果物。
- AAG / AAGD の成果物を検証する HVE Self-Improve と runtime gate。

### 対象外

- HVE 内部の全 Custom Agent への一括適用。
- AAG / AAGD 以外の workflow の既存成果物変更。
- Agentごとの専用Skillの無条件生成。
- 新しいhook framework、provider registry、Strategy / Factory層の追加。

## 3. 規範語

| 語 | 意味 |
|---|---|
| MUST | 対象Agentで必須。欠落は設計または実装gateのFAIL |
| SHOULD | 該当条件では実施。不採用時は理由と代替を記録 |
| MAY | 要件に根拠がある場合だけ採用 |
| N/A | 非該当。理由と判断根拠が必要。空欄の代替には使わない |

## 4. 必須契約ブロック

各 Agent 詳細設計は、既存12セクション内に次の契約を含める。見出し名は後続validatorが識別できる形で固定する。

| Contract ID | 固定見出し | 必須内容 |
|---|---|---|
| AG-CAP-01 | `Goal Contract` | Mission、Done、成功条件、評価方法、証跡、失敗・部分成功 |
| AG-CAP-02 | `Runtime Goal Loop` | Plan / Act / Observe / Evaluate、再計画条件、反復上限、timeout、停止条件、Handoff |
| AG-CAP-03 | `Knowledge & Structured Data Routing` | Read-only取得のデータ種別、preferred/fallback/blocked経路、設計時状態、実行時probe、権限、出典 |
| AG-CAP-04 | `REST CRUD Matrix` | Create / Update / Deleteとoperational Readの必要性、REST method/path、承認、冪等性、失敗分類 |
| AG-CAP-05 | `MCP Integration Plan` | Read-only検索・外部Tool用client接続、Remote MCP adapter境界、認証、承認、失敗時動作 |
| AG-CAP-06 | `Skill Packaging Decision` | Skill要否、3回ルール、配置先、必要なresources、不要時理由 |

既存セクション番号を不要に変更してはならない。これらは Step 3 の Tooling Design と System Prompt Instruction Format へ統合する。

## 5. MUST / SHOULD / N/A 判定

### 5.1 全AgentでMUST

- `Goal Contract`。
- `Runtime Goal Loop`。単純な1回処理でも1 iterationでDone判定し、無制限に反復しない。
- データアクセスの有無を含む `Knowledge & Structured Data Routing` の判定。
- 業務操作の有無を含む `REST CRUD Matrix` の判定。
- MCP利用の有無を含む `MCP Integration Plan` の判定。
- Agent別Skillの要否を含む `Skill Packaging Decision` の判定。
- 各判断の根拠となる入力文書パスまたはユーザー決定。

`Runtime Goal Loop` の反復上限は AG-CAP-02 だけを正本とする。AG-CAP-01 は成功・失敗・部分成功の判定条件を定義し、AG-CAP-02 はその判定を各 iteration で参照する。両ブロックに別々の上限値を記載してはならない。

### 5.2 条件付きMUST

| 条件 | 必須となる能力 |
|---|---|
| 非構造化データを検索する | Read-only search routing、引用、fallback、権限境界 |
| **Foundry IQ / Azure AI Search Agentic RetrievalをPreferredまたはFallbackに選ぶ** | **Skill `agentic-retrieval-contract` のAR-CAP-01〜05** |
| 公開Webを検索する | Web経路のavailability判定と承認済みfallback |
| Microsoft 365を検索する | Work IQ経路とユーザー権限境界 |
| Fabricを利用できる | Fabric IQ経路の適合判定 |
| 構造化数値を取得する | Fabric IQ優先判定または読取専用SQL契約 |
| 業務状態を永続的に作成・更新・削除する | REST Tool、HITL、RBAC、監査、冪等性 |
| MCP接続を使う | client設定、認証、承認、timeout、失敗時縮退 |
| 同じ手順連鎖が3回以上現れる、または明確な再利用要件がある | Agent別Skillと必要なresources |

「3回」は `users-guide/08-ai-agent.md` の既存HVEルールであり、Anthropic仕様上の必須値ではない。Anthropic型Skillのbundled resourcesが任意であることを前提に、Skill乱造を防ぐためのHVE固有の選択閾値として使う。

業務状態の永続変更有無は AAG Step 1 で、ユースケースの主要フロー・例外・権限から判定する。判定結果を `Mutation Intent: required | none | TBD` として Goal Contract に記録し、AAG Step 3 の AG-CAP-04 はその値と根拠を参照する。`TBD` のまま変更Toolを実装してはならない。

### 5.3 Read、REST mutation、MCPの境界

- AG-CAP-03 は検索、分析、数値取得などの Read-only 経路を所有する。
- AG-CAP-04 の Create / Update / Delete は REST API Function Tool だけを実行経路とする。
- AG-CAP-04 の Read は、検索ではない既存業務APIの `GET` 等を呼ぶ場合だけ記載する。検索・SQL・IQ経路のReadはAG-CAP-03を参照し、二重実装しない。
- Remote MCP Server が業務APIを公開する場合も、mutationは同じRESTビジネスロジックのadapterであり、REST認可・HITL・監査・冪等性を迂回しない。
- Agentが同じmutationをRESTとMCPの2経路から直接選べる設計は禁止する。Agent実装のprimary mutation経路はREST Function Toolとする。

### 5.4 Availabilityの記録

AG-CAP-03の各経路は次を分けて記録する。

| 項目 | 記録内容 |
|---|---|
| Design status | `supported` / `preview` / `limited-access` / `unavailable` / `unknown` と確認日（`YYYY-MM-DD`）・公式根拠 |
| Runtime probe | 実行時に確認する認証、接続、権限、health条件 |
| Preferred route | 前提を満たす場合に使うRead-only経路 |
| Fallback route | Preferredが利用不可の場合に使う承認済み経路 |
| Blocked condition | どの条件で取得を中止し、捏造せずHandoffするか |

設計時の提供状態を、実行時の一時的な可用性と同一視しない。

### 5.3 N/Aの条件

N/Aには次の全項目を記録する。

- 対象 Contract ID。
- 非該当理由。
- 根拠となる設計書、要件、またはユーザー決定。
- 後から該当へ変わる条件。

`N/A`、`該当なし`、`不要`だけの記載はFAILとする。

## 6. フェーズ別責務

| Phase | 責務 | 禁止 |
|---|---|---|
| AAG Step 1 (`Arch-AIAgentDesign-Step1`) | ユーザー目的、成功条件、Mutation Intent、制約、未決事項を抽出 | 根拠のないKPI・閾値の生成 |
| AAG Step 2 (`Arch-AIAgentDesign-Step2`) | Agent境界、data/tool/MCP境界、候補経路を決定 | 全providerの無条件採用 |
| AAG Step 3 (`Arch-AIAgentDesign-Step3`) | AG-CAP-01〜06を実装可能な契約として確定 | 不明項目の黙示補完 |
| AAGD Step 2.1 (`Arch-TDD-TestSpec`) | 各契約の正常・境界・失敗テストを仕様化 | 実サービス接続を前提とするunit test |
| AAGD Step 2.2 (`Dev-Microservice-Azure-AgentTestCoding`) | mock/stubでREDテストを作成 | Azure/M365/Fabric/Webへの実接続 |
| AAGD Step 2.3 (`Dev-Microservice-Azure-AgentCoding`) | 設計で選択された能力だけを実装しGREEN化 | 未選択providerの先回り実装 |
| AAGD Step 3 (`Dev-Microservice-Azure-AgentDeploy`) | 選択providerのpreflight・接続・smoke test | Preview値やAPI versionの推測固定 |
| HVE runtime gate | 必須契約と対応成果物を決定的に検証 | LLMの自己申告だけでPASS |
| HVE Post-DAG Self-Improve | AAG/AAGDが生成した設計・テスト・コードを対象に、静的解析とテスト証跡で未達を検出・修正・再検証 | 生成Agentの本番利用ログを必須入力にすること、scan→plan→無変更scanを改善成功扱いすること |

## 7. 設計と実装のトレーサビリティ

各実装・テストは Contract ID を参照する。

| 成果物 | 必須トレース |
|---|---|
| Agent detail | AG-CAP-01〜06の各ブロック |
| Agent test spec | 対象 Contract ID、テストケースID、期待結果 |
| Agent test code | テスト仕様パスとテストケースID |
| Agent implementation | 対応 Contract ID または設計セクション |
| Deploy evidence | 選択provider、確認事項、公式根拠、実行結果 |
| Self-Improve evidence | criterion、改善前結果、対象 Contract ID、変更ファイル、改善後結果、変更差分または改善不要理由 |

生成Agentの Runtime Goal Loop は、1リクエスト内の目的達成を AG-CAP-01 の evaluator で評価する。HVE Post-DAG Self-Improve は、開発成果物のlint/test/contract gateを改善する。両者は別の状態、上限、証跡を持ち、一方のPASSを他方のPASSとして流用しない。

## 8. 検証レベル

### 8.1 設計gate

- AG-CAP-01〜06がすべて存在する。
- N/Aは理由と根拠を持つ。
- 選択経路とfallbackが矛盾しない。
- REST C/U/Dと直接DB更新が混在しない。
- AG-CAP-01に反復上限を重複記載せず、AG-CAP-02に正本がある。
- AG-CAP-03のDesign status、Runtime probe、Preferred、Fallback、Blockedが揃う。
- AG-CAP-03でFoundry IQ / Azure AI Search Agentic Retrievalを選んだ場合、AR-CAP-01〜05が揃い、Skill `agentic-retrieval-contract` の整合ルールR1〜R12を満たす。
- AG-CAP-04のmutationがREST Function Toolへ一意に対応し、MCPが迂回経路になっていない。

### 8.2 実装gate

- 設計で選択した各 Contract ID に対して、実装ファイルとテストケースIDの対応が§7のトレース表にある。
- 未選択providerの不要な依存がない。
- Runtime Goal Loopに上限と停止条件がある。
- secretがコード・設定・ログへ固定されていない。

### 8.3 デプロイgate

- providerのavailability、認証、権限、data boundaryを確認している。
- 実smoke testまたは明示的なblocked証跡がある。
- 未実行をPASSとしていない。

### 8.4 Gateの所有者

| 検証対象 | 所有者 |
|---|---|
| Skill frontmatter / routing | `validate-skill-routing.py` |
| AAG detailのAG-CAP-01〜06、N/A、境界 | `hve.artifact_validation` のAI Agent設計validator |
| AAGD実装と設計の対応 | `hve.artifact_validation` のAI Agent実装validator |
| Step終了時のfail判定 | `hve.runner` のAAG/AAGD allowlist gate |
| MUST/条件付きMUST/N/Aの回帰 | 後続Subで作成する `hve/tests/test_ai_agent_capability_contract.py` |
| HVE Self-Improveの変更前後証跡 | Self-Improve unit/integration tests |

このreference作成時点では、後続Subが `hve/tests/test_ai_agent_capability_contract.py`、`hve.artifact_validation` のvalidator、`hve.runner` のgateを実装する。契約文の存在だけを実装完了とはしない。

## 9. 不確実性と公式情報

- Web IQ、Fabric IQ、Azure AI Search Agentic Retrieval等の提供状態は実行時に公式情報で確認する。
- API version、SKU、model、region availabilityを本契約で固定しない。
- `v1`、`preview`、具体的SKU、model、regionの値は、公式根拠と確認日を伴わない限り設計・実装gateで確定値として受理しない。
- 公式情報を取得できない場合は、確定値を捏造せず `要確認` またはblockedとして記録する。
- Preview機能をGAとして記載しない。

## 10. 完了条件

本契約の導入は次を満たしたとき完了する。

1. AAG Step 1〜3がAG-CAP-01〜06を生成する。
2. AAGD Step 2.1〜3が契約をテスト・実装・検証する。
3. HVE gateが欠落・理由なしN/A・実装不整合を検出する。
4. 生成AgentのRuntime Goal LoopとHVE開発時Self-Improveを別々に検証する。
5. 既存TDD contract tests、`hve/tests/test_artifact_validation_deploy_gate.py`、`hve/tests/test_workiq.py`、`hve/tests/test_runner.py` のWork IQ QA-only契約がPASSする。
