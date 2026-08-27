

## Remote MCP Server 実装

この Step では、API を通常の REST API として実装・デプロイするだけでなく、Remote MCP Server としても公開できるようにしてください。

### 基本方針

- REST API のビジネスロジックと MCP Server 公開層を疎結合にしてください。
- REST API の既存 contract を壊さないでください。
- MCP Server は API のユースケースを Tool / Resource / Prompt として公開してください。
- MCP 固有の入出力変換は adapter 層に閉じ込めてください。
- MCP SDK、Transport、Compute、追加 Cloud Service は実装対象の環境に応じて選定してください。

### 実装時の検討事項

- 対象 API のうち、どの操作を MCP Tool として公開するか
- MCP Tool の input schema / output schema
- 認証・認可方式
- CORS / network boundary / public endpoint の扱い
- ローカル実行と Cloud 実行の差分
- ログ、監視、エラーハンドリング
- CI/CD でのデプロイと smoke test
- 関連ドキュメントへの接続方法記載

### Azure 上で実装する場合の考慮事項

Azure に REST API がホスティングされる場合は、選択された Compute 環境に合わせて最適な MCP 実装方式を選定してください。

例:

- Azure Functions の場合:
  - HTTP Trigger を使った MCP endpoint
  - 必要に応じて Azure Functions に適した MCP SDK または HTTP adapter を利用
- Azure App Service の場合:
  - Web アプリケーション内に MCP endpoint を追加
  - 既存 REST route と MCP route を分離
- Azure Container Apps の場合:
  - MCP Server を sidecar または同一 service 内 endpoint として構成
  - ingress / scaling / revision 管理を考慮
- API Management を利用する場合:
  - REST API と MCP endpoint の公開経路を整理
  - 認証、rate limit、logging policy を検討

### 完了条件

- REST API としての通常利用が可能である
- Remote MCP Server として接続可能である
- MCP Tool / Resource / Prompt の定義が実装されている
- REST API と MCP adapter が疎結合である
- 認証・認可・ログ・エラーハンドリングが整理されている
- 関連ドキュメントに MCP endpoint、利用方法、設定方法が記載されている