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
| AG-CAP-07 | `Agent Identity & Authorization` | 実行identityの種別、attended / unattended、権限付与範囲、identityの粒度、責任者、secret非固定 |
| AG-CAP-08 | `Observability Contract` | telemetry送信先、準拠規約、必須spanと属性、service識別、redaction、保持とコスト |
| AG-CAP-09 | `Distribution & Packaging` | 公開チャネル、plugin manifestとcomponent、MCP公開、M365公開の範囲と版、可視メタデータの統制 |
| AG-CAP-10 | `Evaluation & Route Right-sizing` | 評価軸、合否基準、指標、コスト・レイテンシの実測、候補経路、経路勧告と採否記録 |

既存セクション番号を不要に変更してはならない。これらは Step 3 の Tooling Design と System Prompt Instruction Format へ統合する。

## 5. MUST / SHOULD / N/A 判定

### 5.1 全AgentでMUST

- `Goal Contract`。
- `Runtime Goal Loop`。単純な1回処理でも1 iterationでDone判定し、無制限に反復しない。
- データアクセスの有無を含む `Knowledge & Structured Data Routing` の判定。
- 業務操作の有無を含む `REST CRUD Matrix` の判定。
- MCP利用の有無を含む `MCP Integration Plan` の判定。
- Agent別Skillの要否を含む `Skill Packaging Decision` の判定。
- 実行identityと権限付与範囲を含む `Agent Identity & Authorization` の判定。
- 必須spanとredactionを含む `Observability Contract` の判定。
- 公開チャネルの有無を含む `Distribution & Packaging` の判定。
- 評価軸と候補経路を含む `Evaluation & Route Right-sizing` の判定。
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

「3回」は HVE 固有の既存ルールであり、Anthropic仕様上の必須値ではない。Anthropic型Skillのbundled resourcesが任意であることを前提に、Skill乱造を防ぐためのHVE固有の選択閾値として使う。

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

### 5.5 AG-CAP-07 `Agent Identity & Authorization`

Agent が「誰として」下流リソースを呼ぶかを固定する。AG-CAP-03 / AG-CAP-04 / AG-CAP-05 の各経路は、ここで確定した identity と権限の範囲内でしか動作しない。

次の項目をすべて記録する。

| 項目 | 記録内容 |
|---|---|
| Identity kind | 実行identityの種別と、その Design status（`supported` / `preview` / `unknown` と確認日 `YYYY-MM-DD`・公式根拠） |
| Authentication mode | `attended` / `unattended` / `both`。両方使う場合は経路ごとの使い分け条件 |
| Permission scope | 付与するrole / scope / consentと、その付与先（identity単位かテンプレート単位か） |
| Identity granularity | identityをAgentインスタンス単位で分けるか、共有するか。共有する場合の理由 |
| Accountability | 責任者（sponsor / owner）と、無効化・失効の手順 |
| Secret handling | 資格情報の保管先。コード・設定ファイル・ログ・成果物へ値を固定しないこと |

#### 5.5.1 attended / unattended

分類と名称は Microsoft Foundry の Agent identity 公式定義に揃える（確認日 2026-08-17、<https://learn.microsoft.com/azure/foundry/agents/concepts/agent-identity>）。

- `attended`（delegated access / on-behalf-of flow）はユーザーの委任権限で動作する。OAuth 2.0 on-behalf-of により、ユーザーが同意し認可されたリソースだけへアクセスする。
- `unattended`（application-only flow）はAgent自身の権限で動作する。OAuth 2.0 client credentials によりアプリケーション権限を使う。
- 1つのAgentが両方を持つ場合、どの経路がどちらを使うかを経路ごとに書き分ける。既定で `unattended` へ寄せてはならない。

#### 5.5.2 他契約との境界

- **検索経路ごとの per-user 権限の要否判定は AG-CAP-03 が正本**とする。AG-CAP-07 で同じ判定を再定義しない。
- Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合、**KB を MCP として公開する際の per-user 権限の伝播可否は Skill `agentic-retrieval-contract` の AR-CAP-05 が正本**とする。
- AG-CAP-07 は「Agent 全体の実行 identity」と「AG-CAP-04 の mutation を実行する権限」を所有する。
- **AG-CAP-03 または AG-CAP-04 のいずれかの経路が per-user 権限を要件とする場合、AG-CAP-07 の `Authentication mode` に `attended` を含めることを必須とする。** ユーザーidentityを伝播できないまま application 権限で代替してはならない。伝播できない場合は当該経路を blocked とし、Handoff する。

#### 5.5.3 N/A の扱い

AG-CAP-07 は全Agentで MUST であり、N/A にできない。外部リソースを一切呼ばないAgentであっても、`Identity kind` に「下流リソース呼び出しなし」と根拠を書き、`Permission scope` を `none` として記録する。

### 5.6 AG-CAP-08 `Observability Contract`

Agent の実行を後から検証できる形で残す。「どこからこの応答が来たか」「どのステップが失敗・遅延を生んだか」を答えられることを最低限の到達点とする。

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Telemetry backend` | ✅ | 送信先と、接続設定を取得する環境変数名または参照先。**接続文字列・キーの値自体は書かない** |
| `Semantic convention` | ✅ | 準拠する規約と確認日（`YYYY-MM-DD`）・公式根拠 |
| `Required spans` | ✅ | 少なくとも次の4種を列挙する。① 1リクエスト全体、② Runtime Goal Loop の各 iteration、③ 各 Tool 呼び出し、④ 各検索呼び出し。不要な span は理由を書いて除外する |
| `Required attributes` | ✅ | 各 span に残す項目。少なくとも 所要時間 / 結果分類（成功・失敗・部分成功）/ iteration 番号 / 停止理由。モデル呼び出しがある span はトークン消費を含める |
| `Service identification` | ✅ | 複数アプリを同じ送信先へ集約したときに区別できるサービス名と、その設定方法 |
| `Redaction` | ✅ | span 属性・ログへ出さない項目と、その担保方法 |
| `Cost & retention` | ✅ | 保持期間と、データ量に応じた課金影響を確認したこと |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

#### 5.6.1 準拠規約の既定

Microsoft Foundry は Application Insights へ OpenTelemetry の semantic conventions で trace を格納し、カスタム Agent にも generative AI 向け semantic conventions への準拠を期待する（確認日 2026-08-17、<https://learn.microsoft.com/azure/foundry/observability/how-to/trace-agent-setup>、<https://learn.microsoft.com/azure/foundry/control-plane/register-custom-agent>、<https://opentelemetry.io/docs/specs/semconv/gen-ai/>）。

このため `Semantic convention` の既定は **OpenTelemetry の generative AI semantic conventions** とする。別規約を選ぶ場合は理由と公式根拠を記録する。

trace が捕捉する対象として公式に列挙されているのは、ユーザー入力と Agent 出力、Tool 呼び出しとその結果、トークン消費、所要時間・レイテンシの4群である（確認日 2026-08-17、<https://learn.microsoft.com/azure/foundry/observability/concepts/trace-agent-concept>）。`Required spans` / `Required attributes` はこの4群を覆うこと。

#### 5.6.2 API version / SKU を固定しない

送信先サービス名、SDK パッケージ名、API version、リージョンは本契約で固定しない。§9 の規定に従い、公式根拠と確認日を伴わない値を確定値として受理しない。

#### 5.6.3 AR-CAP-04 との境界

- **AG-CAP-08 は Agent 実行全体の trace / span を所有する。**
- **検索応答の引用（source references）と activity log の有効化は、Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合 Skill `agentic-retrieval-contract` の AR-CAP-04 が正本**とする。AG-CAP-08 で再定義しない。
- 検索呼び出しそのものの span（所要時間・結果分類・トークン）は AG-CAP-08 側で持つ。
- `Redaction` の禁止項目は AR-CAP-04 の「残してはならないもの」と矛盾させない。具体的には、**検索・Tool 呼び出しの span 属性へ query 本文・response 本文・access token・userinfo / query / fragment を含む raw URL を入れない**。代わりに Tool 名、HTTP status、件数、correlation ID、不可逆ハッシュ、取得日時を残す。

#### 5.6.4 N/A の扱い

AG-CAP-08 は全Agentで MUST であり、N/A にできない。telemetry を外部へ送信しない選択をする場合も、`Telemetry backend` に送信しない理由と、代わりにどこへ span を残すかを記録する。

### 5.7 AG-CAP-09 `Distribution & Packaging`

生成した Agent を、利用者のチャットクライアントから実際に呼べる形で配布するための契約。「実装したが呼び出せない」状態を防ぐ。

配布物の生成は AAGD の実装フェーズ、実際の公開は AAGD の Deploy 以降のフェーズが担う。担当 Step は §6 を正本とする。

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Channels` | ✅ | 採用する公開チャネルの列挙。採らないチャネルは理由付き `not-selected` |
| `Plugin manifest` | ✅ | `plugin.json` の `name` / `version` / `description` の決定方法と、版を上げる条件 |
| `Plugin components` | ✅ | `skills/` と `mcp.json` の要否。**`mcp.json: required` または `mcp.json: not-required` と英語の定型語で書く**（検証器は非 ASCII を落とすため、日本語の否定語を判定できない）。`skills/` の要否は AG-CAP-06 の決定を参照し、再判定しない |
| `MCP exposure` | 条件付き | `mcp.json` を出す場合、transport / エンドポイントの形式 / ホスティング先 / 公開する Tool の範囲 |
| `M365 publish` | 条件付き | Microsoft 365 / Teams へ公開する場合、公開範囲、対応する認可スキーム、承認の要否、版の採番規則 |
| `Metadata visibility` | ✅ | 利用者に見えるメタデータの列挙と、そこへ secret を入れない担保方法 |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

#### 5.7.1 Agent Plugins チャネル

Agent Plugins Specification 1.0.0（確認日 2026-08-17、<https://github.com/agentplugins/agent-plugins-spec/blob/main/spec/1.0.0.md>）に従う。次は仕様上の制約であり、設計で緩めてはならない。

- マニフェストは plugin root の `plugin.json` だけであり、top-level は closed schema（§5.2）。必須は `$schema` と `name`（§5.3）。
- v1 の component は **skills（`skills/`）と MCP servers（`mcp.json`）の2種のみ**（§7）。固定位置を `plugin.json` で上書きできない（§6.1）。
- `mcp.json` は plugin root 固定で、`plugin.json` へのインライン記述は不可。`$schema` の版は `plugin.json` と一致させる（§7.2.1 / §10.1）。
- リモート transport の URL は絶対 HTTP(S) で、**非 loopback は HTTPS 必須**。user-info と fragment を含められない（§7.2.1）。
- **v1 は OAuth 設定も可搬な資格情報参照フィールドも定義しない。認可は client 管理**（§7.2.1）。設計で独自の認証フィールドを `plugin.json` へ追加してはならない。
- **`headers` と `env` は可視のパッケージデータであり、資格情報を埋め込んではならない**（§7.2.1 / §9.2）。

認可が client 管理である以上、**利用者側で何を設定すれば接続できるかを手順として成果物へ残すこと**を `MCP exposure` の必須内容とする。

#### 5.7.2 Microsoft 365 / Teams チャネル

Microsoft Foundry の Microsoft 365 公開経路に従う（確認日 2026-08-17、<https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot>、<https://learn.microsoft.com/azure/foundry/agents/how-to/publish-copilot-virtual-network>）。

- 公開範囲と認可スキームは連動する。テナント全体へ公開する選択は管理者承認を伴う。設計ではどちらを選ぶかと、承認待ちになる場合の扱いを記録する。
- **既に公開した版と同じ版を再公開できない**。版の採番規則と、更新時に誰が上げるかを `M365 publish` へ書く。
- **公開メタデータは利用者に見える。secret・API キー・機密情報をどのフィールドへも入れてはならない**。
- 既存の認可スキームとプロトコル設定を削除しない。公開のために追加するのであって、置き換えてはならない。
- API version、SKU、リージョン、リソース名は本契約で固定しない（§9）。

#### 5.7.3 AG-CAP-05 / AG-CAP-06 との境界

- **AG-CAP-05 は Agent が MCP client として「接続する」側を所有する。**
- **AG-CAP-09 は Agent を「公開する」側を所有する。** 両者を同じブロックで混ぜない。
- Agent を MCP として公開する場合でも、公開する Tool は AG-CAP-04 で Required とされたものだけとし、§5.3 の「同じ mutation を REST と MCP の2経路から直接選べる設計は禁止」を維持する。
- `skills/` の中身の要否は AG-CAP-06 が正本。AG-CAP-09 はそれを plugin として梱包する方法だけを決める。

#### 5.7.4 N/A の扱い

どのチャネルも採用しない場合だけ AG-CAP-09 全体を N/A にできる。その場合は本章の「N/Aの条件」節の全項目に加え、**利用者がこの Agent をどう呼ぶのか**を記録する。

### 5.8 AG-CAP-10 `Evaluation & Route Right-sizing`

選んだ設計が、目的に対して**不足しても過剰でもない**ことを実測で裏付ける。特に、高価な推論を伴う検索手法を選んだ場合に、それが目的に見合うかを判定する。

評価の実行は AAGD の Deploy 以降のフェーズが担う。担当 Step は §6 を正本とする。

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Evaluation axes` | ✅ | 評価する軸と採否理由。少なくとも目的達成と Tool 利用を含める。検索経路を持つ場合は経路のコスト対効果も含める |
| `Quality criteria` | ✅ | 合否基準。AG-CAP-01 の Success criteria のどの Criterion ID に対応するかを明記する |
| `Quality metrics` | ✅ | 使う指標名と取得方法。provider 提供の指標を使う場合は提供状態と確認日を伴う |
| `Cost & latency evidence` | ✅ | コストとレイテンシの実測方法と取得元。推定値だけで埋めない |
| `Candidate routes` | ✅ | 実測する候補経路を **2 段以上** 列挙する。選定経路と、より安い候補を最低 1 つ |
| `Route recommendation rule` | ✅ | 勧告の判定規則。既定は「`Quality criteria` を満たす候補のうち、コストとレイテンシが最小のものを勧告する」 |
| `Decision record` | ✅ | 勧告への採否と理由をどの成果物へ残すか |
| `Blocked condition` | ✅ | 実測できない場合の扱い。**未実測を PASS としない** |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

#### 5.8.1 過剰投資を検出するための最低条件

**候補経路を 1 段しか実測しない評価は、「過剰ではない」ことを示せないため受理しない。** 少なくとも「選定経路」と「より安い候補 1 つ」を同じ評価セットで測る。

候補経路の並び順と選択基準は Skill の `references/search-routing.md` を正本とする。本節で重複定義しない。

検索経路のコストは推定ではなく、実行時に返る計測値から取る。Foundry IQ / Azure AI Search Agentic Retrieval を選んだ場合の取得方法は Skill `agentic-retrieval-contract` の AR-CAP-03 / AR-CAP-04 を参照する。

#### 5.8.2 指標の選定

provider が提供する Agent 向け評価指標（意図解決、タスク遵守、タスク完了、Tool 呼び出しの正確さ、Tool 選択、Tool 入力の正確さ、Tool 出力の活用、Tool 呼び出しの成否、経路効率など）を使ってもよい（確認日 2026-08-17、<https://learn.microsoft.com/azure/foundry/concepts/built-in-evaluators>、<https://learn.microsoft.com/azure/foundry/concepts/evaluation-evaluators/agent-evaluators>）。

ただし、これらの指標には preview のものが含まれる。§9 に従い、**preview を GA として記載せず**、提供状態と確認日を `Quality metrics` へ伴わせる。provider 提供の指標を使わず自前の判定を使ってもよいが、判定規則を再現可能な形で記録する。

#### 5.8.3 他契約との境界

- `Quality criteria` は AG-CAP-01 の Success criteria を参照する。別の合格基準を新設しない。
- 実測の証跡は AG-CAP-08 の span / 属性から取ることを既定とする。別経路で取る場合は理由を書く。
- **生成 Agent の評価（AG-CAP-10）と、HVE 開発時の Post-DAG Self-Improve は別物である。** 一方の PASS を他方の PASS として流用しない。
- Toolbox / tool search を採用した場合の実測は Skill `foundry-toolbox-contract` の TB-CAP が正本であり、AG-CAP-10 はその結果を参照する。

#### 5.8.4 N/A の扱い

AG-CAP-10 は全Agentで MUST であり、N/A にできない。検索経路を持たない Agent でも、`Evaluation axes` から経路の軸を理由付きで外し、目的達成と Tool 利用の軸は残す。

## 6. フェーズ別責務

| Phase | 責務 | 禁止 |
|---|---|---|
| AAG Step 1 (`Arch-AIAgentDesign-Step1`) | ユーザー目的、成功条件、Mutation Intent、制約、未決事項を抽出 | 根拠のないKPI・閾値の生成 |
| AAG Step 2 (`Arch-AIAgentDesign-Step2`) | Agent境界、data/tool/MCP境界、候補経路を決定 | 全providerの無条件採用 |
| AAG Step 3 (`Arch-AIAgentDesign-Step3`) | AG-CAP-01〜10を実装可能な契約として確定 | 不明項目の黙示補完 |
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
| Agent detail | AG-CAP-01〜10の各ブロック |
| Agent test spec | 対象 Contract ID、テストケースID、期待結果 |
| Agent test code | テスト仕様パスとテストケースID |
| Agent implementation | 対応 Contract ID または設計セクション |
| Deploy evidence | 選択provider、確認事項、公式根拠、実行結果 |
| Self-Improve evidence | criterion、改善前結果、対象 Contract ID、変更ファイル、改善後結果、変更差分または改善不要理由 |

生成Agentの Runtime Goal Loop は、1リクエスト内の目的達成を AG-CAP-01 の evaluator で評価する。HVE Post-DAG Self-Improve は、開発成果物のlint/test/contract gateを改善する。両者は別の状態、上限、証跡を持ち、一方のPASSを他方のPASSとして流用しない。

## 8. 検証レベル

### 8.1 設計gate

- AG-CAP-01〜10がすべて存在する。
- N/Aは理由と根拠を持つ。**ただし AG-CAP-07 / AG-CAP-08 / AG-CAP-10 は N/A にできない（§5.5.3 / §5.6.4 / §5.8.4）**。
- 選択経路とfallbackが矛盾しない。
- REST C/U/Dと直接DB更新が混在しない。
- AG-CAP-01に反復上限を重複記載せず、AG-CAP-02に正本がある。
- AG-CAP-03のDesign status、Runtime probe、Preferred、Fallback、Blockedが揃う。
- AG-CAP-03でFoundry IQ / Azure AI Search Agentic Retrievalを選んだ場合、AR-CAP-01〜05が揃い、Skill `agentic-retrieval-contract` の整合ルールR1〜R12を満たす。
- AG-CAP-04のmutationがREST Function Toolへ一意に対応し、MCPが迂回経路になっていない。
- AG-CAP-07のIdentity kind、Authentication mode、Permission scope、Identity granularity、Accountability、Secret handlingが揃う。
- AG-CAP-08のTelemetry backend、Semantic convention、Required spans、Required attributes、Service identification、Redaction、Cost & retention、Decision sourceが揃う。
- AG-CAP-09のChannels、Plugin manifest、Plugin components、Metadata visibility、Decision sourceが揃い、採用チャネルに応じたMCP exposure / M365 publishがある。
- AG-CAP-10のEvaluation axes、Quality criteria、Quality metrics、Cost & latency evidence、Candidate routes（2段以上）、Route recommendation rule、Decision record、Blocked condition、Decision sourceが揃う。

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
| AAG detailのAG-CAP-01〜10、N/A、境界 | `hve.artifact_validation` のAI Agent設計validator |
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

1. AAG Step 1〜3がAG-CAP-01〜10を生成する。
2. AAGD Step 2.1〜3が契約をテスト・実装・検証する。
3. HVE gateが欠落・理由なしN/A・実装不整合を検出する。
4. 生成AgentのRuntime Goal LoopとHVE開発時Self-Improveを別々に検証する。
5. 既存TDD contract tests、`hve/tests/test_artifact_validation_deploy_gate.py`、`hve/tests/test_workiq.py`、`hve/tests/test_runner.py` のWork IQ QA-only契約がPASSする。
