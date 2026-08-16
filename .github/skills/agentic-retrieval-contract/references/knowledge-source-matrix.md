# Knowledge Source Matrix — AR-CAP-02

Microsoft Learn 確認日: 2026-08-04。対応種別・preview 状態・tier 上限は実行時に再確認する。

## 1. 「複数データソース横断」の実現方法

Knowledge Source は Azure AI Search 上の独立したトップレベルリソースで、Knowledge Base の必須構成要素である。

**1 つの Knowledge Base から複数の Knowledge Source を参照でき、Agentic Retrieval エンジンは 1 リクエストでそれら全てにクエリを発行する。** Knowledge Source ごとにサブクエリが生成され、上位結果が retrieval 応答に返る。

indexed / remote のどちらであっても、取得したコンテンツは**同一のランキングパイプライン**を通る。関連度でスコアリングされ、クエリ横断でマージされ、再ランクされてから応答に返る（統一ランキング）。

したがって「データソースごとに検索 Tool を分けて Agent に何度も呼ばせる」設計は採らない。**1 KB に束ねて 1 リクエストで済ませる**のが本パイプラインの設計意図である。

### 行数の下限（R14）

**AR-CAP-02 は 2 行以上を必須とする。** Knowledge Source が 1 件しか無い Knowledge Base は、ファンアウト先が 1 つしかなく、統一ランキングも単一ソース内で完結する。このとき得られるのはクエリ拡張だけであり、多ソース横断という Agentic Retrieval 固有の利得は発生しない。

1 件で足りる場合は、Agentic Retrieval を採用せず AG-CAP-03 で別経路（対応 source の直接 Read API 等）を選ぶ。逐次増やす予定で初期は 1 件にしたい場合も、未実在の KS を行として埋めてはならない。

### KB を分ける判断

1 つの KB に束ねず分割してよいのは、次のいずれかに根拠がある場合に限る。

- 知識ドメインが異なり、`retrievalInstructions` で誘導しても誤選択が避けられない。
- 権限境界が異なり、同一 KB に置くとアクセス制御を満たせない。
- KS 上限（tier 依存、設計時は 10 を上限として扱う）を超える。
- reasoning effort や output mode を分けたい実運用上の理由がある。

分割した場合は、その根拠を AR-CAP-01 の `Decision source` に記録する。

## 2. Knowledge Source の種別

| Kind | 説明 | indexed / remote |
|---|---|---|
| Search index | 既存インデックスをラップする | indexed |
| Azure blob | Blob コンテナーから indexer パイプラインを生成する | indexed |
| Azure SQL（preview） | Azure SQL のテーブル / ビューから indexer パイプラインを生成する | indexed |
| File（preview） | ファイルを Azure AI Search へ直接アップロードする | indexed |
| OneLake | lakehouse から indexer パイプラインを生成する | indexed |
| Indexed SharePoint（preview） | SharePoint サイトから indexer パイプラインを生成する | indexed |
| Remote SharePoint（preview） | SharePoint からクエリ時に取得する | remote |
| Fabric Data Agent（preview） | Fabric data agent から回答と埋め込みリソースを取得する | remote |
| Fabric Ontology（preview） | Fabric ontology からエンティティ・関係ベースの回答を取得する | remote |
| MCP server（preview） | 外部 MCP Server から live な tool 由来の結果を取得する | remote |
| Work IQ（preview） | Work IQ から組織インテリジェンスを取得する | remote |
| Web | Microsoft Bing からリアルタイムのグラウンディングデータを取得する | remote |

**preview 表記と対応可否は変化する。実行時に公式一覧で再確認し、`Design status` と `Checked at` に反映する。**

### indexed と remote の違い

- **indexed**: クエリ時より前にコンテンツを索引へ取り込む。取り込み経路は 3 つ（既存インデックスの利用 / ファイル直接アップロード / indexer パイプライン自動生成）。クエリは検索サービス上でローカルに実行される（keyword / vector / hybrid）。
- **remote**: コンテンツを Azure AI Search へ取り込まない。クエリ時に各プラットフォームのネイティブ API 経由で取得する。到達経路はプラットフォーム次第で、公開インターネット経由（Bing 等）とテナント内（SharePoint / Fabric 等）がある。

「Azure 外だから」という理由だけで Push API へ固定しない。要件（鮮度・コンプライアンス・コスト）に照らして最小の経路を選ぶ。

## 3. AR-CAP-02 の表形式

Markdown 表で記載する。1 行 = 1 Knowledge Source。

| 列 | 必須 | 値の条件 |
|---|---|---|
| `KS name` | ✅ | 実際に作成する Knowledge Source 名。**`low` / `medium` では LLM の選択根拠になるため、内容を表す名前にする** |
| `Kind` | ✅ | §2 の Kind |
| `Locality` | ✅ | `indexed` / `remote` |
| `Always query` | ✅ | `true` / `false` + 理由 |
| `Selection description` | 条件付き | `low` / `medium` では必須。indexed KS ではインデックスの `description` に設定する内容 |
| `Ingestion` | ✅ | `indexer` / `push` / `file-upload` / `remote-live` + 選定根拠 |
| `Freshness SLO` | ✅ | 要求鮮度。満たせない場合の代替も書く |
| `Permission boundary` | ✅ | 実行 identity、document-level 権限、テナント境界 |
| `Required for Done` | ✅ | `yes` / `no`。`yes` の KS が失敗したら全体を blocked にする |
| `Design status` | ✅ | `supported` / `preview` / `limited-access` / `unavailable` / `unknown` |
| `Checked at` | ✅ | `YYYY-MM-DD` |
| `Decision source` | ✅ | 判断根拠となるリポジトリ内パスまたは公式資料 |

## 4. 検索対象の制御

### `alwaysQuery`

Knowledge Source 定義側で `alwaysQuery` を `true` にすると、retrieval reasoning effort に関わらず毎回のクエリに含まれる。

> `minimal` では全 Knowledge Source が常に検索されるため、`alwaysQuery` の値は挙動に影響しない。加えて retrieve 要求の `alwaysQueryKnowledgeSource` プロパティも無視される。予算は「全 KS を毎回検索する」前提で積む。

### `retrievalInstructions`

Knowledge Base 定義または retrieve アクションで指定する。**どの Knowledge Source を LLM が選ぶ / 飛ばすかを誘導する。** prompt と同様に、簡潔さ・トーン・書式も指定できる。

`low` / `medium` での KS 選択は次の 3 要因で決まる。

1. Knowledge Source の `name`
2. （indexed KS の場合）インデックスの `description`
3. Knowledge Base 定義または retrieve アクションの `retrievalInstructions`

したがって `Selection description` を空にしたまま `low` / `medium` を選ぶと、LLM は名前だけで判断することになり、KS 選択の精度が落ちる。

## 5. 運用上の制約

- Knowledge Source は Knowledge Base より**先に**作成する。KB は KS を ID で参照するため。
- KS を削除するには、参照している KB を先に更新または削除する。
- KS と KB は**同一の検索サービス上**に存在しなければならない。
- KS 作成には検索サービスに対する `Search Service Contributor` 権限が必要。indexer パイプラインを生成する KS では、索引へロードするために `Search Index Data Contributor` 権限も必要。
- 作成の対応状況（Azure portal / Microsoft Foundry portal / REST API / Azure SDK）は KS 種別ごとに異なる。実行時に確認する。
- **Azure CLI（`az search`）に Knowledge Source の作成コマンドは無い**（Microsoft Learn 確認日: 2026-08-05。
  各 KS の `Usage support` 表に挙がるのは Azure portal / Microsoft Foundry portal / .NET / Python / Java / JavaScript SDK / REST API のみ）。
  デプロイスクリプトは **REST（`PUT {search-url}/knowledgesources/{name}?api-version=<preview>`）または SDK** を使うこと。
  他の Azure リソースと同じ感覚で `az` コマンドを探すと存在せず、Agent が停止または捏造する。
- preview 機能は **preview API version でのみ利用できる**（確認時点: `2026-05-01-preview`）。
  GA の api-version を使うと preview 種別の KS は作成できない。api-version は固定値として書かず、実行時に確認する。

### Work IQ KS のクエリ時制約（実行時に効く）

- 応答に **40〜60 秒以上**かかることがある。retrieve 要求の `maxRuntimeInSeconds` を **120 以上**にしないとタイムアウトする。
- OBO トークンフロー。エンドユーザーのアクセストークンを `x-ms-query-source-authorization` ヘッダーで渡す。
  トークンの audience は `https://search.azure.com/.default`。検索サービス自体の認証はこれとは別に必要。
- preview では Work IQ 側が**取得だけでなく操作を行う機能**を使う可能性がある。信頼できる利用者・アプリに限定する。


## 6. 権限とデータ境界

- ACL 付きの indexed コンテンツでは、インデックスに権限メタデータフィールドを含め、クエリ時に `x-ms-query-source-authorization` ヘッダーでユーザートークンを渡してユーザー ID に基づく結果フィルタリングを行う。
- Remote SharePoint KS では同ヘッダーがユーザー ID を伝え、SharePoint 側がクエリ時に文書権限を適用する（コンテンツは索引化されない）。
- blob / indexed OneLake / indexed SharePoint では、Microsoft Purview の秘密度ラベルを取り込める。取り込み後は retrieve 応答に現れ、クエリ時の文書レベルアクセス制御に使われる。チャンク索引を使う場合は skillset の index projection でチャンク行にもラベルをマップしないと、ラベル付き文書のチャンク参照が返らない。
- 権限を確認できない、またはデータ境界違反の可能性がある場合は、取得を実行せず blocked にする。
