---
applyTo: ".github/.mcp.json, .github/skills/**"
---
# MCP Server Skills 化 設計メモ

## 現在の MCP Server 構成（`.github/.mcp.json`）

| Server名 | パッケージ | 用途 |
|---|---|---|
| `azure` | `@azure/mcp@latest` | Azure リソース操作（hve でも同一実装を共有） |
| `context7` | `@upstash/context7-mcp@latest` | コンテキスト管理 |

## Skills での MCP Server 実装方針

### GitHub Copilot Skills の制約
- `.github/skills/*/SKILL.md` は **静的な指示書**（Markdown）
- 実行可能なコードを直接実行する仕組みは Skills にはない
- Skills は Agent の「知識」として読み込まれるが、「ツール」として実行されるわけではない

### MCP Server と Skills の役割分担

| 層 | 責務 | 実装場所 |
|---|---|---|
| **知識層** | MCP Server の呼び出しパターン・エラーハンドリング手順 | `.github/skills/mcp-{server-name}/SKILL.md` |
| **実行層** | 実際の MCP Server 呼び出し | `.github/.mcp.json` + `hve`（同一実装共有） |
| **設定層** | Server エンドポイント・認証方式 | `.github/.mcp.json` |

### 推奨: 作成する Skills

| Skill 名 | 内容 |
|---|---|
| `mcp-azure` | Azure MCP Server の呼び出しパターン・利用可能なツール一覧・エラーハンドリング |
| `mcp-context7` | Context7 MCP Server の呼び出しパターン・検索クエリ設計 |

### hve との共有
- `hve` は Python の `GitHub Copilot CLI SDK` として実装中
- `.github/.mcp.json` を共有設定ファイルとして利用
- Skills は Copilot cloud agent / Copilot CLI / Claude Code のいずれからも参照可能
