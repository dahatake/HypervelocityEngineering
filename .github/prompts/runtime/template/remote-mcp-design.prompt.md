

## Remote MCP Server 設計観点

`create-remote-mcp-server` が `true` のため、対象 API を Remote MCP Server として公開するための設計観点を含めてください。

### 設計に含めること

- どの API ユースケースを MCP Tool / Resource / Prompt として公開するか
- MCP Tool の入力スキーマ、出力スキーマ
- REST API と MCP 公開層の責務分離
- MCP 固有の入出力変換を adapter 層に閉じ込める方針
- 認証・認可方針
- エラー応答方針
- ログ・監視方針
- 実行環境非依存のインターフェース定義
- 実装フェーズで SDK / Transport / Cloud Service を選定する前提

### 設計で固定しないこと

- 特定 MCP SDK
- 特定 Transport
- 特定 Cloud Compute
- 特定 Cloud Provider 固有サービス