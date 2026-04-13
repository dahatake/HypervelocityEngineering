---
name: mcp-server-design
description: >
  MCP Server の設計指針を提供する。Skills と MCP Server の関係性、
  MCP Server の責務分離、API 設計パターンを定義する。
  USE FOR: MCP Server design, skills and MCP relationship,
  MCP API design pattern, server configuration, .github/.mcp.json.
  DO NOT USE FOR: MCP Server implementation, deployment,
  skill content creation, testing.
  WHEN: MCP Server を設計する、Skills と MCP Server の関係を整理する、
  MCP Server の API 設計パターンを参照する。
metadata:
  origin: user
  version: "1.0.0"
---

# mcp-server-design

## 目的

MCP Server の設計指針と、Skills との役割分担を定義する。

## Non-goals（このスキルの範囲外）

- **MCP Server の実装コーディング** — 開発 Agent が担当
- **MCP Server のデプロイ** — デプロイ Agent が担当
- **Skill コンテンツの作成** — 各ドメイン Skill が担当

## ガイド一覧（references/）

| ファイル | 内容 |
|---------|------|
| `references/mcp-server-skills-design.md` | MCP Server と Skills の詳細な責務分離・API設計パターン・エラーハンドリング |

## 概要

### MCP Server と Skills の役割分担

| 層 | 責務 | 実装場所 |
|---|---|---|
| **知識層** | MCP Server の呼び出しパターン・エラーハンドリング手順 | `.github/skills/mcp-{server-name}/SKILL.md` |
| **実行層** | 実際の MCP Server 呼び出し | `.github/.mcp.json` |
| **設定層** | Server エンドポイント・認証方式 | `.github/.mcp.json` |

### 現在の MCP Server 構成

| Server名 | パッケージ | 用途 |
|---|---|---|
| `azure` | `@azure/mcp@latest` | Azure リソース操作 |
| `context7` | `@upstash/context7-mcp@latest` | コンテキスト管理 |

## Related Skills

| Skill | 関係 | 説明 |
|-------|------|------|
| `agent-common-preamble` | 参照元 | MCP Server 利用パターンの共通参照 |
| `task-questionnaire` | 先行 | MCP Server 設計前のコンテキスト収集 |

## 入出力例

※ 以下は説明用の架空例です。

### 例1: 新しい MCP Server の追加設計ケース

**入力**: データベース操作用の MCP Server（`db-mcp`）を追加したい。Skill から呼び出せるようにしたい。

**出力**:
- 設計方針: `db-mcp` は「実行層」として `.github/.mcp.json` に追加
- `.github/.mcp.json` への追記内容（設定例）:
  ```json
  {
    "servers": {
      "db": {
        "type": "stdio",
        "command": "npx",
        "args": ["db-mcp-server@latest"]
      }
    }
  }
  ```
- Skill 定義: `知識層` として `.github/skills/mcp-db/SKILL.md` を作成し、呼び出しパターン・エラーハンドリングを記述

### 例2: 既存 MCP Server の呼び出しパターン設計ケース

**入力**: `azure` MCP Server を使って Azure リソース一覧を取得するパターンを設計したい。

**出力**:
- 呼び出し元: `.github/skills/azure-platform/azure-resource-lookup/SKILL.md` が担当
- 呼び出しツール: `mcp_azure_mcp_group_list`（リソースグループ一覧）。リソース一覧の取得は `azure-resource-lookup` 側で実在する Azure CLI / Resource Graph 用ツール（例: `extension_cli_generate`）に委譲する
- エラーハンドリング: 認証エラー時は `azure-rbac` Skill を参照してロール確認を促す
