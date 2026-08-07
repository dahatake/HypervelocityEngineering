# AI Agent 検索ルーティング仕様

## 1. 目的

AG-CAP-03 `Knowledge & Structured Data Routing` の決定手順を定義する。Agentは、データ種別、利用可能性、ユーザー権限、データ境界を確認し、設計で選択されたRead-only経路だけを使用する。

本仕様はprovider共通の抽象化層や自動provider registryを要求しない。各Agent詳細設計に、必要な経路の選択結果だけを記録する。

## 2. ルーティング出力

Agent詳細設計は、使用する経路ごとに次の1行を記録する。

| 項目 | 必須値 |
|---|---|
| Request class | `public-web` / `microsoft-365` / `fabric-business-data` / `enterprise-unstructured` / `structured-numeric` / `operational-api-read` |
| Data source | 実在するsource名または`TBD`。IDやURLを推測しない |
| Required for Done | このsourceがGoal ContractのDoneに必須なら`yes`、補助なら`no` |
| Preferred route | 選択したprovider / Tool / API |
| Design status | `supported` / `preview` / `limited-access` / `unavailable` / `unknown` |
| Checked at | 公式情報を確認した日、`YYYY-MM-DD` |
| Runtime probe | 認証、接続、権限、healthの確認項目 |
| Fallback route | 利用不可時の承認済み経路。なければ`none` |
| Blocked condition | 回答を生成せずHandoffする条件 |
| Permission boundary | signed-in user、managed identity、service identity等の根拠ある境界 |
| Citation requirement | URL、文書参照、query evidence等の必須証跡 |
| Decision source | 要件・設計書・ユーザー決定・公式資料のパス/URL |

`none`またはN/Aには理由が必要である。

## 3. 判定順序

1. ユーザー要求をRequest classへ分類する。
2. 取得対象がRead-onlyであることを確認する。永続変更はAG-CAP-04へ委譲する。
3. データ所在地とユーザー権限を確認する。
4. 下表からPreferred routeを1つ選ぶ。
5. Design statusとRuntime probeを記録する。
6. Preferredが使えない場合のFallbackを1つだけ記録する。
7. PreferredもFallbackも使えない場合はBlocked conditionを適用する。
8. 結果に経路固有の引用またはquery evidenceを付ける。

複数データ種別が必要な問い合わせは、種別ごとに行を分ける。単一の曖昧な「全検索」Toolへ統合しない。

### 行を分けた結果 Tool が増える場合

本ルールは検索品質のために統合を禁止するため、データ種別が増えるほど Tool 数は増える。
Tool 総数が 10〜15 を超える見込みなら、**統合ではなく公開方式で解く**。
`foundry-toolbox-contract`（TB-CAP-01〜05）で Toolbox / tool search の採否を決めること。

**同じ経路が複数行に現れても Tool としては 1 つ**である（TB-CAP-01 の総数を数えるときに二重計上しない）。

## 4. 検索ルーティング決定表

| Request class | 判定条件 | Preferred route | Fallback | Permission / data boundary | Evidence |
|---|---|---|---|---|---|
| `public-web` | 公開Webの最新ページ、ニュース、画像、動画が必要 | Web IQ（利用承認済みの場合） | Microsoft Foundry Web Search | Web IQ / Web Searchの利用条件と組織ポリシーを確認。Web groundingはAzure compliance boundary外へのデータフロー条件を確認 | 取得URL、タイトル、取得日時 |
| `microsoft-365` | メール、会議、Teams、SharePoint、OneDrive等のM365コンテキスト | Work IQ | `none`。未承認時はblocked | signed-in userのM365権限、Entra consent、tenant policy | M365 source種別、日時、パス/場所。本文の過剰保存は禁止 |
| `fabric-business-data` | Fabric ontology、data agent、Power BI semantic modelの業務概念・分析 | Fabric IQ | 適合する場合のみ`structured-numeric`のSELECT-only SQL | signed-in user、Fabric delegated permission、workspace governance | Fabric item種別、query、返却時刻、利用したbusiness concept |
| `enterprise-unstructured` | 組織文書・知識ベースへの複雑な質問 | Foundry IQ / Azure AI Search Agentic Retrieval knowledge base | 対応sourceの直接Read API、または承認済みRemote MCP | Search/Foundry identity、document-level permission、sourceのcompliance boundary | source references、activity log（利用可能な場合）、取得日時 |
| `structured-numeric` | 数値・集計・時系列を構造化storeから取得し、Fabric IQを使えない | SELECT-only SQL Tool | `none`。安全条件を満たせなければblocked | read-only identity、table/view allowlist、row/time limit | parameterized query、対象source、実行時刻、行数。secretと機微値は除外 |
| `operational-api-read` | 検索ではなく既存業務APIから単一状態・entityを読む | 既存REST GET Function Tool | 設計済みRead-only MCP Toolがある場合だけ使用可 | API RBAC、tenant/user scope | method/path、status、correlation ID |

## 5. Azure AI Search / Foundry IQ

### 使用条件

- 複雑な質問をsubqueryへ分解し、複数Knowledge Sourceを検索・rerankする必要がある。
- Knowledge Baseと少なくとも1つのKnowledge Sourceを設計できる。
- source referencesまたは同等の根拠を応答へ渡せる。

### AR-CAP契約の必須化

`enterprise-unstructured` のPreferred routeとしてFoundry IQ / Azure AI Search Agentic Retrievalを選んだ場合、Agent詳細設計にSkill `agentic-retrieval-contract` のAR-CAP-01〜05を**必須で含める**。

| 本節の記述 | 正本となるAR-CAP |
|---|---|
| どのKnowledge Sourceを束ねるか、取り込み方式、鮮度、権限境界 | AR-CAP-02 `Knowledge Source Matrix` |
| どの程度LLM処理を行うか（subquery本数・cost・latencyのトレードオフ） | AR-CAP-01 `Knowledge Base Contract` / AR-CAP-03 `Retrieval Budget` |
| source referencesとactivity logを有効化するか | AR-CAP-04 `Evidence & Observability` |
| Knowledge BaseのMCPをどこへ公開し、どのToolを許可するか | AR-CAP-05 `MCP Exposure` |

本AG-CAP-03はroute選択とCitation requirementの正本であり、Foundry IQの**構成値**を重複記載しない。

### データソースの接続

1. Azure AI Searchの現行Knowledge Sourceでsource種別がサポートされているか、実行時にMicrosoft Learnで確認する。
2. Indexed sourceは既存index、file upload、対応indexer、またはPush APIから、要件に合う最小経路を選ぶ。
3. live retrievalが必要でnative remote sourceに対応する場合はremote sourceを選ぶ。
4. native対応がなく、source所有者が安全なTool APIを提供できる場合だけRemote MCPを選ぶ。
5. 「任意データソース対応」を理由に、不要なcopy pipelineや汎用connector frameworkを作らない。

Remote MCPを選ぶ場合は、少なくとも次を設計・テストする。

- OAuth、managed identity等の認証方式とread-only permission。
- rate limit、timeout、最大response size。
- 429 / 5xx / timeoutのエラー分類と有限retry。
- sourceからAgentまでのdata boundary。
- citationに必要なsource identifier、path/URL、取得日時の返却可否。

### MCP接続

Knowledge BaseのMCP endpointをAgentから使う場合はAG-CAP-05にも記録する。これはRead-only retrievalの接続であり、AG-CAP-04のREST mutationを置き換えない。

複数Knowledge Sourceを検索する場合、rerank後も各evidence itemにsource class、source identifier、pathまたはURL、取得日時を保持する。値が提供されない項目を推測で補わない。

許可するToolのallowlistとper-user権限の伝播可否はAR-CAP-05を正本とする。

## 6. Web IQ / Web Search

- Web IQは2026-07-10確認時点でlimited access。利用承認をruntime probeで確認する。
- 利用承認済みの場合だけWeb IQをPreferredにする。
- 未承認またはTool未公開の場合、設計で承認されていればMicrosoft Foundry Web Searchへfallbackする。
- fallbackは自動的に別の未承認Web providerへ切り替えない。
- public webへ送信するqueryに機密情報、個人情報、内部URLを含めない。
- citationが取得できない場合は、Web由来の事実として回答しない。

## 7. Work IQ

- Microsoft 365範囲の検索はWork IQを使用する。
- HVE自身のQA-only Work IQ経路と、生成Agentが実行時に使用するWork IQ Toolを区別する。
- 生成Agentではsigned-in userの権限を超えるsourceを取得しない。
- consent、Tool公開、tenant policy、接続をruntime probeで確認する。
- 未承認時にWeb Searchや一般LLM知識でM365情報を補完しない。blockedとしてHandoffする。

## 8. Fabric IQ

- Microsoft Fabricが利用可能で、ontology / data agent / semantic modelが要求に適合する場合はFabric IQをPreferredにする。
- Fabric IQの利用可否はlicense、item公開状態、region、permission、connectionをruntime probeで確認する。
- Fabric IQが使えず、元sourceがread-only SQLで安全に取得できる場合だけSELECT-only SQLへfallbackする。
- Fabricのsemantic modelを、推測したtable/schemaのSQLへ黙示変換しない。

## 9. SELECT-only SQL

構造化数値のfallbackとしてSQLを使う場合、次をすべてMUSTとする。

- 単一のSELECT文だけを許可する。
- INSERT / UPDATE / DELETE / MERGE / DDL / stored procedure実行を拒否する。
- table / view / columnのallowlistを設計から取得する。
- 値をparameterizeし、文字列連結でqueryへ埋め込まない。
- read-only identityを使用する。
- row limitとtimeoutを設定する。
- query実行前に構文と許可対象を検査する。
- queryと行数を監査証跡へ残すが、secret・token・過剰な機微値は記録しない。
- 検査不能、schema不明、権限不明の場合は実行せずblockedにする。

## 10. 非Azureデータソース

- Azure外であることだけを理由にPush APIへ固定しない。
- Azure AI Searchが対応するindexed / remote Knowledge Sourceを実行時に確認する。
- sourceのnative APIまたはRemote MCPを使う場合、read-only scope、認証、rate limit、data boundary、citationを定義する。
- source全量をAzureへ複製する設計は、鮮度・compliance・コスト要件に根拠がある場合だけ採用する。

## 11. FallbackとBlocked

### Fallback

- 目的とデータ境界が等価な承認済み経路だけを使う。
- fallback後もcitationと権限を弱めない。
- fallback発生を監査ログへ記録する。
- 同じ失敗経路を無制限に再試行しない。

### 複数sourceの部分失敗

- route行ごとに独立してPreferred→Fallback→Blockedを評価する。
- `Required for Done: yes` のsourceがBlockedなら、Goal ContractのDoneを満たさない。
- `Required for Done: no` のsourceだけがBlockedなら、取得できたsourceの結果と欠落sourceを明示してPartial successにできる。
- 取得できなかったsourceのcitationや内容を他sourceから補完しない。
- すべてのrequired sourceがBlockedなら全体をBlockedとしてHandoffする。

### Blocked

次の場合は取得を中止する。

- 認証・consent・権限を確認できない。
- PreferredとFallbackの両方が利用不可。
- citationまたはquery evidenceを提供できない。
- SQL安全条件を満たせない。
- data boundary違反の可能性がある。

Blocked時は、不足条件、試した経路、再開条件を返し、結果を創作しない。

## 12. 公式根拠

確認日: 2026-07-10

| タイトル | URL | 本仕様で確認した事項 |
|---|---|---|
| Agentic retrieval in Azure AI Search | https://learn.microsoft.com/azure/search/agentic-retrieval-overview | Knowledge Base、Knowledge Source、query planning、parallel retrieval、reranking、references |
| What is a knowledge source? | https://learn.microsoft.com/azure/search/agentic-knowledge-source-overview | indexed / remote source、Web、Work IQ、Fabric、MCP等の現行source種別 |
| Data import in Azure AI Search | https://learn.microsoft.com/azure/search/search-what-is-data-import | PushとIndexerの2基本経路 |
| Work IQ MCP overview | https://learn.microsoft.com/microsoft-365/copilot/extensibility/work-iq/mcp/overview | M365 Tool、Entra認証、path単位の権限 |
| Connect agents to Microsoft Fabric with Fabric IQ | https://learn.microsoft.com/azure/foundry/agents/how-to/tools/fabric-iq | Fabric item、delegated permission、runtime接続 |
| Web grounding tools overview | https://learn.microsoft.com/azure/foundry/agents/how-to/tools/web-overview | Foundry Web Search、citation、data boundary、fallback候補 |
| Microsoft Web IQ | https://aka.ms/WebIQ | public web groundingとlimited access状態 |

API version、SKU、model、regionは本仕様で固定しない。実装・デプロイ時に公式情報を再確認する。
