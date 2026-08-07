# MCP Exposure & Evidence — AR-CAP-04 / AR-CAP-05

Microsoft Learn 確認日: 2026-08-04。API version・ロール名・preview 制約は実行時に再確認する。

## 1. AR-CAP-04 `Evidence & Observability`

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Source references` | ✅ | `enabled` / `disabled` + 理由。`disabled` なら引用をどう担保するかを書く |
| `Activity log` | ✅ | `enabled` / `disabled` + 理由 |
| `Citation fields` | ✅ | 応答へ残す項目。最低限 source 種別 / source 識別子 / path または URL / 取得日時 |
| `Blocked condition` | ✅ | 引用または query evidence を提供できない場合の停止条件 |
| `Secret handling` | ✅ | ログ・成果物へ残さない項目（token / credential / 本文 / raw URL 等） |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

### 応答の構成

Knowledge Base の retrieve 応答では、**マージ済みコンテンツは常に返る**。一方 **source references と実行 activity log は任意**であり、明示的に有効化して初めて引用と観測性が得られる。

「引用を出す」要件がある場合、`Source references` を `enabled` にせずに設計を完了してはならない。

### activity log の使いどころ

`medium` の反復検索では、activity log に「より網羅的な回答のために生成されたクエリ」が現れる。サブクエリ本数と反復発生の実測は activity log から取る。AR-CAP-03 の `Measurement method` はこれを指してよい。

### 証跡に残してよい / 残してはならないもの

| 区分 | 内容 |
|---|---|
| 残してよい | provider 名、Tool 名、HTTP status、件数、correlation ID、citation の不可逆ハッシュ、取得日時 |
| 残してはならない | secret 値、access token、consent URL、query 本文、response 本文、userinfo / query / fragment を含む raw URL |

## 2. AR-CAP-05 `MCP Exposure`

`- ラベル: 値` の定型キー行で記載する。

| ラベル | 必須 | 値の条件 |
|---|---|---|
| `Status` | ✅ | `selected` または `N/A`。`N/A` のときは `Reason` / `Decision source` / `Recheck condition` を併記 |
| `Consumer` | ✅ | KB の MCP を使う側（Foundry Agent Service / 他の MCP ホスト / 自前クライアント） |
| `Project connection` | 条件付き | Foundry 経由の場合は接続名と作成方針 |
| `Connection category` | 条件付き | Foundry 経由の場合は接続カテゴリ |
| `Auth type` | ✅ | 認証方式。key ベースを選ぶ場合は理由 |
| `Tool allowlist` | ✅ | 許可する MCP tool。Foundry Agent Service では `knowledge_base_retrieve` のみ |
| `Approval mode` | ✅ | tool 呼び出しの承認要否 |
| `Per-user authorization` | ✅ | `required` / `not-required` + 伝播方式。伝播できない場合の扱いを書く |
| `Design status` | ✅ | `supported` / `preview` / `limited-access` / `unavailable` / `unknown` |
| `Checked at` | ✅ | `YYYY-MM-DD` |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

## 3. Foundry Agent Service への接続

Knowledge Base は MCP エンドポイントを公開する。Microsoft Foundry プロジェクトからは、プロジェクトのマネージド ID でそのエンドポイントを対象とする接続を作成し、Agent の MCP tool として使う。

### 接続の要点

- 接続カテゴリは `RemoteTool`、認証タイプは `ProjectManagedIdentity`。この 2 つは Microsoft Foundry のプロジェクト接続に固有である。
- MCP エンドポイントは検索サービスの Knowledge Base 配下のパスとして構成される。**API version を含むため、値は実行時に公式手順から取得する。**
- MCP tool 定義では、サーバーラベル、サーバー URL、承認要否、`allowed_tools`、プロジェクト接続 ID を指定する。

### Tool allowlist

> Azure AI Search の Knowledge Base は Agent 統合向けに `knowledge_base_retrieve` MCP tool を公開する。**これが Foundry Agent Service で現在サポートされている唯一の tool である。**

したがって Foundry Agent Service 接続では `knowledge_base_retrieve` 以外を allowlist へ追加しない。追加した場合は設計違反として扱う。

### 権限

| 対象 | ロール / 設定 | 用途 |
|---|---|---|
| プロジェクトの親リソース | Foundry User | モデルデプロイへのアクセスと Agent 作成 |
| プロジェクトの親リソース | Foundry Project Manager | MCP 認証用のプロジェクト接続の作成 |
| プロジェクト | システム割り当てマネージド ID | Azure AI Search との相互作用 |
| 検索サービス | Search Index Data Reader | 索引への読み取り専用アクセス（プロジェクトのマネージド ID に割り当てる） |
| 検索サービス | Search Index Data Contributor | Agent が索引へ書き込む場合のみ追加 |

> Foundry の RBAC ロール名は改称されている（旧: Azure AI User / Azure AI Owner / Azure AI Account Owner / Azure AI Project Manager）。ロール ID と権限は改称で変わらない。表示名は環境により旧名が残る場合があるため、**実行時に確認する**。

Agent が索引へ書き込む要件が無い限り、`Search Index Data Contributor` を先回りで割り当てない。

## 4. per-user 権限の制約（重要）

> このプレビューでは、**Foundry Agent Service は MCP tool の per-request ヘッダーをサポートしない**。Agent 定義に設定したヘッダーは全ての呼び出しに適用され、ユーザーやリクエストごとに変えられない。per-user 認可が必要な場合は Azure OpenAI Responses API を使う。

設計上の帰結:

- **per-user 権限が必須の要件で、Foundry Agent Service 経由の MCP を選ぶことはできない。** `Per-user authorization: required` かつ `Consumer: Foundry Agent Service` の組み合わせは blocked とする。
- application 権限（全ユーザー共通の identity）へ置き換えて回避してはならない。権限昇格になる。
- 代替として Azure OpenAI Responses API 経路を選ぶ場合は、その判断を `Decision source` に記録する。

Remote SharePoint Knowledge Source を含む Knowledge Base では、MCP tool 接続に `x-ms-query-source-authorization` ヘッダーを含める必要がある。上記の per-request ヘッダー制約と併せて成立可否を判定する。

## 5. Agent 側の指示（system prompt）

MCP tool として KB を接続する場合、Agent の指示文には少なくとも次を含める。

- Knowledge Base を使って回答すること、自身の知識だけで回答しないこと。
- 回答には必ず注釈（citation）を付けること。
- Knowledge Base に答えが無い場合は、答えを作らずに「分からない」と応答すること。

これは AR-CAP-04 の `Blocked condition` と一致していなければならない。**指示文と契約が食い違う場合は設計違反**として扱う。

指示文の具体的な文面は用途ごとに評価・反復して決める。固定文をそのまま採用しない。
